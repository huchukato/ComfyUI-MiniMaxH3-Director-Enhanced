"""Ask a provider which models it serves, so the panel can offer a real list instead of free text.

Two protocols again, because that is all we speak: Ollama answers /api/tags with {"models": [...]},
everything OpenAI-compatible answers /v1/models with {"data": [{"id": ...}]}. A provider whose
reply we cannot read yields an empty list and a reason naming the address, so a wrong base URL
says so instead of looking like a server with nothing installed.
"""
import asyncio

import aiohttp

from ... import minimax_media as legacy
from ..core import providers


def _address(base_url, path):
    """One place that decides where a provider's endpoints are.

    Providers document their base both ways: some with a trailing /v1, some without. Appending to
    the wrong one asks for /v1/v1/models and gets a 404 that says nothing useful (issue #31), so
    the version segment is normalised here rather than at each call site.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("Enter the provider's address first; that is what the models are asked from.")
    if path.startswith("/api/"):
        return base + path
    if base.endswith("/v1beta/openai") and path.startswith("/v1/"):
        return base + path[3:]
    root = base[:-3] if base.endswith("/v1") else base
    return "%s%s" % (root, path)


def _ids(payload):
    """Both reply shapes, plus the common aliases, without inventing names that were not sent.

    A bare string is a name, not a list of names: iterating it would read "not a list" as seven
    models called n, o, t. Everything else that is not a list is treated as unreadable, because a
    guessed list is worse than an empty one the panel can still be typed into.
    """
    if isinstance(payload, str):
        raise ValueError("The provider sent a single model name where a list was expected.")
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        found = payload.get("data") if "data" in payload else payload.get("models")
        if isinstance(found, str):
            raise ValueError("The provider sent a single model name where a list was expected.")
        entries = found if isinstance(found, list) else []
    else:
        return []
    names = []
    for entry in entries:
        if isinstance(entry, str):
            name = entry
        elif isinstance(entry, dict):
            name = entry.get("id") or entry.get("name") or entry.get("model") or ""
        else:
            name = ""
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return sorted(dict.fromkeys(names))


async def listing(provider, base_url, api_key=None, timeout=15):
    """The model names this address currently serves. Never raises: an unreachable provider is an
    empty list plus a reason, because a panel with no list must still let the user type a name."""
    entry = providers.get(provider)
    # An empty base_url means "the address this provider is known at", not "no address". The panel
    # shows the address as a placeholder and only writes it into the widget when it is edited, so
    # sending the widget value alone would refuse the providers that work out of the box.
    url = _address(base_url or entry.base_url, entry.models_path)
    # Claude wants x-api-key and a version header, like the analysis itself; a bearer token got HTTP 401.
    headers = legacy.registry_auth_headers(entry.auth, api_key) or {}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    return [], "The provider answered HTTP %s for %s." % (response.status, url)
                payload = await response.json(content_type=None)
    except asyncio.TimeoutError:
        return [], "Could not reach %s (request timed out). Check the address and whether the server is running." % url
    except aiohttp.ClientError as error:
        return [], "Could not reach %s (%s). Check the address and whether the server is running." % (url, error)
    except (ValueError, TypeError):
        return [], "The provider's answer at %s was not readable." % url
    return _ids(payload), ""
