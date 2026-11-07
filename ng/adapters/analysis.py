"""Reuse legacy text/vision transport. Audio uses the compatible input_audio message only when declared."""
import asyncio

import aiohttp
from PIL import Image

from ... import minimax_media as legacy
from ..core import providers
from ..core.analysis import ProviderConfig, analysis_prompt, parse_suggestion
from ..core.fields import need_dict
from ..core.context_build import widget_text
from ..core.system_prompts import framed, for_node
from . import preview_media


def endpoint(config):
    """Where this provider actually lives, and which model to ask for.

    The registry owns the address. `_PROVIDER_DEFAULTS` only ever listed Ollama, LM Studio and
    "custom", so indexing it with a provider id from the registry raised KeyError for OpenAI,
    Claude, Gemini, OpenRouter and llama.cpp - every provider the panel now offers.

    Both are checked here rather than left to aiohttp. A remote provider with no address and no
    model would otherwise become a connection error against an empty string, which names neither the
    missing setting nor the card that needed it.
    """
    entry = providers.get(config.provider)
    defaults = legacy._PROVIDER_DEFAULTS.get(config.provider) or {}
    url = legacy.normalize_base_url(config.base_url, entry.base_url or defaults.get("url", ""))
    model = config.model or entry.sample_model or defaults.get("model", "")
    # `custom` is the only provider with neither, so it is the only one where this can fire. Checked
    # on the provider rather than on an empty url, because a local provider always has an address.
    if entry.id == "custom" and not url:
        raise ValueError("Custom URL is not a usable address. Enter the provider's address.")
    return entry, url, model


async def audio_generate(config, prompt, source, key):
    if config.provider == "ollama":
        raise ValueError("This Ollama transport has no audio input; choose an input_audio-compatible provider or describe the sound manually.")
    wav = await asyncio.to_thread(preview_media.audio_wav, source)
    entry, url, model = endpoint(config)
    if not url or not model:
        raise ValueError("Set the provider's address and audio-capable model name.")
    # The same role text and the same schema framing the other media send. Audio had neither until
    # now, which made this the one card whose answer the parser could not rely on - and an audio
    # card is exactly where a "who is speaking" guess matters most.
    messages = [{"role": "system", "content": framed(for_node("context", "audio"))},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "input_audio", "input_audio": {"data": wav, "format": "wav"}}]}]
    payload = {"model": config.model, "stream": False, "max_tokens": config.max_tokens, "messages": messages}
    timeout = aiohttp.ClientTimeout(total=config.timeout_seconds)
    async with aiohttp.ClientSession(headers=legacy.registry_auth_headers(entry.auth, key)) as session:
        async with session.post(legacy.chat_completions_url(url), json=payload, timeout=timeout) as response:
            if response.status in (401, 403):
                raise ValueError("The provider refused authentication; set api_key_env to a variable available to ComfyUI.")
            if response.status != 200:
                raise ValueError("Audio analysis failed (HTTP %d); check whether the model supports input_audio." % response.status)
            body = await response.json()
    try:
        return legacy.strip_thinking(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise ValueError("The audio provider returned an unexpected response.")


def images(media, source):
    if media == "video":
        return preview_media.video_images(source)
    with Image.open(preview_media.require_path(source)) as image:
        return [preview_media.jpeg(image)]


def _capability_error(config, media):
    """Why this provider cannot read this medium, in the user's words, or None when it can.

    The registry knows what a provider accepts; the old two checkboxes only recorded what the user
    believed, and the request then punished them for being wrong. One registry check replaces both:
    the question has one answer per provider, and that answer is a measured fact.

    `custom` is the honest exception. It is "I type the address myself", so nothing is known about
    what sits behind it - refusing a custom provider outright would break the only way to reach a
    server we do not ship. It therefore keeps the stored flags, which for that provider are the
    only evidence available.

    Both messages name the way out, not just the fault. "This provider cannot read audio" leaves the
    user with nothing to do; naming the Text card that needs no provider at all does not.
    """
    entry = providers.get(config.provider)
    if entry.id != "custom":
        if not entry.supports_media(media):
            return providers.UNSUPPORTED_HINT.get(media, "This provider cannot read %s." % media)
        return None
    if media in ("image", "video") and not config.vision:
        return ("Vision is off on the H3 AI Loader, so the AI is not shown this picture. Switch Vision on if the model "
                "reads images, or write the description yourself.")
    if media == "audio" and not config.audio:
        return ("Audio is off on the H3 AI Loader, so the AI is not given this sound. Switch Audio on only for a model "
                "that accepts audio (input_audio), or write the description yourself.")
    return None


async def analyze(payload, *, api_key=None):
    need_dict(payload, "request")
    config = ProviderConfig.from_dict(payload["provider"])
    media, widgets = payload["media"], payload["widgets"]
    need_dict(widgets, "context.widgets")
    if media not in ("image", "video", "audio", "text"):
        raise ValueError("Choose an image, video, audio or text context.")
    refused = _capability_error(config, media)
    if refused:
        raise ValueError(refused)
    prompt = analysis_prompt(media, widgets.get("content", ""), payload.get("offer"))
    key = legacy.resolve_api_key({"api_key_env": config.api_key_env}) if api_key is None else api_key
    try:
        if media == "audio":
            answer = await audio_generate(config, prompt, widgets.get("audio", ""), key)
        else:
            image_list = await asyncio.to_thread(images, media, widgets.get(media, "")) if media in ("image", "video") else []
            if media == "text":
                prompt += "\n\nContext text:\n" + widget_text(widgets, "text")
            entry, url, model = endpoint(config)
            answer = await legacy.vlm_generate(
                image_list, prompt, config.provider, url, model, api_key=key, auth=entry.auth,
                # The role and the schema framing come from one place, and the framing is appended
                # after the role. Sending the role but not the framing is how an answer arrives as
                # prose that parse_suggestion cannot read.
                system_prompt=framed(for_node("context", media)),
                **wire(config))
        return parse_suggestion(answer, payload.get("media", "text")).to_dict()
    except (ValueError, legacy.VLMError) as error:
        raise ValueError(str(error).replace(key, "[redacted]") if key else str(error)) from None


def wire(config):
    """The settings that actually go out, named the way `vlm_generate` names them.

    Built from the config rather than spelled out here, because the sampling matrix in the registry
    is what decides which of these a provider accepts at all. A field Ollama would reject is
    therefore never handed to a transport that would send it.
    """
    values = providers.provider_payload(config.provider, {
        "max_tokens": config.max_tokens, "timeout_seconds": config.timeout_seconds,
        "keep_alive": config.keep_alive, "seed": config.seed, "fixed_seed": config.fixed_seed,
        "temperature": config.temperature, "top_p": config.top_p, "top_k": config.top_k,
        "min_p": config.min_p, "frequency_penalty": config.frequency_penalty,
        "presence_penalty": config.presence_penalty})
    # provider_payload() nests the sampling knobs under "options" for Ollama, because that is the wire format; it
    # travels to vlm_generate whole as `sampling`. Only max_tokens, keep_alive and timeout used to be handed on, so
    # Temperature, Top P/K, Min P, the penalties and a fixed Seed never left ComfyUI. timeout_seconds belongs to the
    # HTTP client and is passed on its own, or the request would fall back to the library default.
    flat = {name: values[name] for name in ("max_tokens", "keep_alive") if name in values}
    return {"max_tokens": flat.get("max_tokens", config.max_tokens),
            "keep_alive": flat.get("keep_alive", 0),
            "timeout": config.timeout_seconds,
            "sampling": values}
