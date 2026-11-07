"""Explicit Auto Direct uses the existing provider transport and returns a proposal."""
from ... import minimax_media as legacy
from ..core.analysis import ProviderConfig
from ..core.auto_direct import direct_tokens, direction_prompt, parse_direction, timing_hints
from ..core.fields import need_dict, read_number, read_list, read_str
from . import probe
from .analysis import endpoint, wire


async def direct(payload, *, api_key=None):
    need_dict(payload, "request")
    config = ProviderConfig.from_dict(payload["provider"])
    director = need_dict(payload["director"], "director")
    seconds = float(read_number(director, "project_seconds", "director", minimum=0.1))
    idea = read_str(director, "idea", "director").strip()
    contexts = read_list(payload, "contexts", "request")
    current = read_str(director, "shots", "director", "")
    parts, sung = timing_hints(director, contexts, probe.duration_seconds)
    prompt = direction_prompt(idea, seconds, contexts, current, (parts, sung))
    key = legacy.resolve_api_key({"api_key_env": config.api_key_env}) if api_key is None else api_key
    try:
        # The provider registry owns address, model and auth; _PROVIDER_DEFAULTS knows only the local three.
        entry, url, model = endpoint(config)
        answer = await legacy.vlm_generate([], prompt, config.provider, url, model, api_key=key, auth=entry.auth,
                                          **{**wire(config), "max_tokens": direct_tokens(config.max_tokens)})
        return parse_direction(answer, seconds, contexts, current, read_str(payload, "keep", "request", ""), sung)
    except (ValueError, legacy.VLMError) as error:
        raise ValueError(str(error).replace(key, "[redacted]") if key else str(error)) from None
