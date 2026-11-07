"""Write out one render part's prompt with the connected HTTP provider (Ollama, OpenAI-compatible, ...)."""
import asyncio

from ... import minimax_media as legacy
from ..core.analysis import ProviderConfig
from ..core.builder import read_quick
from ..core.context_build import card_id
from ..core.fields import need_dict, read_list, read_number
from ..core.part_prompt import SYSTEM, write_tokens
from ..core.part_writer import brief, finish, write_prompt
from . import probe
from .analysis import endpoint, images, wire
from .builder import sees


def _shown(facts, contexts):
    """The part's pictures that could be loaded, and their JPEGs in the same order."""
    files = {card_id(entry): entry["widgets"].get("image") for entry in contexts if entry.get("media") == "image"}
    shown, data = [], []
    for label, context_id in facts["pictures"]:
        try:
            data.extend(images("image", files.get(context_id) or ""))
        except (ValueError, OSError):
            continue
        shown.append((label, context_id))
    return shown, data


async def write(payload, *, api_key=None):
    need_dict(payload, "request")
    config = ProviderConfig.from_dict(payload["provider"])
    director = need_dict(payload["director"], "director")
    contexts = read_list(payload, "contexts", "request")
    facts = brief(director, contexts, int(read_number(payload, "part", "request", minimum=0)), probe.duration_seconds,
                  read_quick(payload))
    shown, data = (await asyncio.to_thread(_shown, facts, contexts)) if sees(config) else ([], [])
    facts["shown"] = shown
    key = legacy.resolve_api_key({"api_key_env": config.api_key_env}) if api_key is None else api_key
    try:
        entry, url, model = endpoint(config)
        answer = await legacy.vlm_generate(data, write_prompt(facts), config.provider, url, model, api_key=key, auth=entry.auth,
                                           system_prompt=SYSTEM, **{**wire(config), "max_tokens": write_tokens(config.max_tokens)})
        return finish(answer, facts)
    except (ValueError, legacy.VLMError) as error:
        raise ValueError(str(error).replace(key, "[redacted]") if key else str(error)) from None
