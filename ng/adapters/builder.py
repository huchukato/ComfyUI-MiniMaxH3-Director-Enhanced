"""Make H3 prompt, planning step, over the connected HTTP provider (Ollama, OpenAI-compatible, ...): the model is shown the
pictures of the image cards and answers with the plan; the Studio then writes each render part out with the part writer."""
import asyncio

from ... import minimax_media as legacy
from ..core import providers
from ..core.analysis import ProviderConfig
from ..core.auto_direct import timing_hints
from ..core.builder import SYSTEM, parse_plan, pictures, plan_prompt, plan_tokens, read_quick
from ..core.fields import need_dict, read_list, read_number, read_str
from . import probe
from .analysis import endpoint, images, wire

MAX_PICTURES = 8


def sees(config):
    """Whether this provider is shown pictures: the registry knows it, a custom address has the Vision switch."""
    entry = providers.get(config.provider)
    return entry.supports_media("image") if entry.id != "custom" else config.vision


def picture_data(contexts, limit=MAX_PICTURES):
    """One small JPEG per image card, in the order pictures() lists them, up to the first missing file (which is named):
    the plan says "the first N attached in this order", so a gap would shift every later picture."""
    out = []
    for entry, _, _ in pictures(contexts)[:limit]:
        try:
            out.extend(images("image", entry["widgets"]["image"]))
        except (ValueError, OSError):
            return out, [entry["widgets"].get("name") or entry["widgets"]["image"]]
    return out, []


async def plan(payload, *, api_key=None):
    need_dict(payload, "request")
    config = ProviderConfig.from_dict(payload["provider"])
    director = need_dict(payload["director"], "director")
    seconds = float(read_number(director, "project_seconds", "director", minimum=0.1))
    contexts = read_list(payload, "contexts", "request")
    quick = read_quick(payload)
    parts, sung = timing_hints(director, contexts, probe.duration_seconds)
    shown, _ = (await asyncio.to_thread(picture_data, contexts)) if sees(config) else ([], [])
    prompt = plan_prompt(quick, read_str(director, "idea", "director", ""), seconds, contexts, len(shown), parts, sung)
    key = legacy.resolve_api_key({"api_key_env": config.api_key_env}) if api_key is None else api_key
    try:
        entry, url, model = endpoint(config)
        answer = await legacy.vlm_generate(shown, prompt, config.provider, url, model, api_key=key,
                                           auth=entry.auth, system_prompt=SYSTEM,
                                           **{**wire(config), "max_tokens": plan_tokens(config.max_tokens)})
        result = parse_plan(answer, seconds, contexts, quick, sung)
    except (ValueError, legacy.VLMError) as error:
        raise ValueError(str(error).replace(key, "[redacted]") if key else str(error)) from None
    unseen = [entry["widgets"].get("name") or "Picture" for entry, _, _ in pictures(contexts)[len(shown):]]
    if unseen:
        result["unseen_pictures"] = unseen
    return result
