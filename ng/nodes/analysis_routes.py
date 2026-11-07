"""Analysis runs only on an explicit context-card request; rendering does not use a provider."""
import asyncio

import aiohttp
from aiohttp import web
from server import PromptServer

from ... import minimax_media as legacy
from ..adapters import keys
from ..adapters.analysis import analyze
from ..adapters.analyze_all import analyze_all
from ..adapters.auto_direct import direct
from ..adapters.builder import plan
from ..adapters.part_writer import write
from ..adapters.storyboard_ai import texts
from ..core.analysis import ProviderConfig
from ..core.fields import need_dict
from .context_routes import key_root


def _answer(data):
    return web.json_response({"ok": True, **data})


def _failure(error):
    return web.json_response({"ok": False, "error": str(error)}, status=400)


# Writing shots with time beats or a part's whole prompt needs more than the AI Loader's default 512 tokens, which suit a
# short card description: qwen3.5:9b stopped mid-JSON on a 10 s shot with two beats (2026-10-18). A higher setting stays.
WRITING_TOKENS = 2048


def _writing(payload):
    provider = payload.get("provider") if isinstance(payload, dict) else None
    if isinstance(provider, dict) and isinstance(provider.get("max_tokens"), int) and provider["max_tokens"] < WRITING_TOKENS:
        payload["provider"] = {**provider, "max_tokens": WRITING_TOKENS}
    return payload


def _api_key(request, payload):
    config = ProviderConfig.from_dict(need_dict(payload, "request")["provider"])
    fallback = legacy.resolve_api_key({"api_key_env": config.api_key_env})
    return keys.resolve(key_root(request), config.provider, fallback) or ""


@PromptServer.instance.routes.post("/ng/analyze")
async def analyze_context(request):
    try:
        payload = await request.json()
        return _answer({"suggestion": await analyze(payload, api_key=_api_key(request, payload))})
    except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
        return _failure(error)


@PromptServer.instance.routes.post("/ng/analyze_all")
async def analyze_every_context(request):
    try:
        payload = await request.json()
        key = None if isinstance(payload, dict) and payload.get("mode") == "manual" else _api_key(request, payload)
        return _answer(await analyze_all(payload, api_key=key))
    except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
        return _failure(error)


@PromptServer.instance.routes.post("/ng/direct")
async def direct_scenes(request):
    try:
        payload = _writing(await request.json())
        return _answer({"suggestion": await direct(payload, api_key=_api_key(request, payload))})
    except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
        return _failure(error)


@PromptServer.instance.routes.post("/ng/write_part")
async def write_part_prompt(request):
    """Prompts per render part: the AI writes one part's prompt out from the compiled one; it is checked before it is shown."""
    try:
        payload = _writing(await request.json())
        return _answer({"suggestion": await write(payload, api_key=_api_key(request, payload))})
    except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
        return _failure(error)


@PromptServer.instance.routes.post("/ng/build_plan")
async def build_plan(request):
    """Make H3 prompt, first step: the whole video planned from the direction, the pictures and the optional request."""
    try:
        payload = _writing(await request.json())
        return _answer({"suggestion": await plan(payload, api_key=_api_key(request, payload))})
    except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
        return _failure(error)


@PromptServer.instance.routes.post("/ng/storyboard_texts")
async def storyboard_texts(request):
    """The H3 Storyboard's AI: titles, captions and shot texts of every panel from what should happen."""
    try:
        payload = _writing(await request.json())
        return _answer({"suggestion": await texts(payload, api_key=_api_key(request, payload))})
    except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
        return _failure(error)
