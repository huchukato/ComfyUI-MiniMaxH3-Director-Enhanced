"""AI: write the storyboard's texts, over the connected HTTP provider (Ollama, OpenAI-compatible, ...). A provider that sees
pictures is shown the image cards, so the shots describe the characters as they look."""
import asyncio

from ... import minimax_media as legacy
from ..core.analysis import ProviderConfig
from ..core.builder import pictures
from ..core.fields import need_dict, read_list
from ..core.storyboard import read_board
from ..core.storyboard_texts import SYSTEM, parse_texts, texts_prompt, texts_tokens
from .analysis import endpoint, wire
from .builder import picture_data, sees


def shown_names(contexts, count):
    return [entry["widgets"].get("name") or "Picture" for entry, _, _ in pictures(contexts)[:count]]


async def texts(payload, *, api_key=None):
    need_dict(payload, "request")
    config = ProviderConfig.from_dict(payload["provider"])
    board = read_board(payload.get("board") or "")
    contexts = read_list(payload, "contexts", "request")
    shown, _ = (await asyncio.to_thread(picture_data, contexts)) if sees(config) else ([], [])
    prompt = texts_prompt(board, contexts)
    if shown:
        prompt += "\nThe attached pictures show, in order: %s." % ", ".join(shown_names(contexts, len(shown)))
    key = legacy.resolve_api_key({"api_key_env": config.api_key_env}) if api_key is None else api_key
    try:
        entry, url, model = endpoint(config)
        answer = await legacy.vlm_generate(shown, prompt, config.provider, url, model, api_key=key, auth=entry.auth,
                                           system_prompt=SYSTEM, **{**wire(config), "max_tokens": texts_tokens(config.max_tokens)})
        return parse_texts(answer, board, contexts)
    except (ValueError, legacy.VLMError) as error:
        raise ValueError(str(error).replace(key, "[redacted]") if key else str(error)) from None
