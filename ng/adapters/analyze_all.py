"""Analyze All runs the same single analysis as a card, so the transport and its errors are identical."""
import asyncio

import aiohttp

from ..core.analysis import ProviderConfig
from ..core.assist import batch_plan
from ..core.fields import need_dict, read_list
from .analysis import analyze


async def analyze_all(payload, *, api_key=None):
    """Returns {results: [{index, ok, suggestion|error}], skipped: [reason]}. One bad card never stops the rest."""
    need_dict(payload, "request")
    config = ProviderConfig.from_dict(payload["provider"])
    contexts = read_list(payload, "contexts", "request")
    targets, skipped = batch_plan(contexts, payload.get("mode", "assist"), True)
    allowed = set(targets)
    results = []
    for index in sorted(allowed):
        entry = need_dict(contexts[index], "contexts[%d]" % index)
        request = {"provider": config.to_dict(), "media": entry.get("media"), "widgets": need_dict(entry.get("widgets"), "contexts[].widgets")}
        try:
            results.append({"index": index, "ok": True, "suggestion": await analyze(request, api_key=api_key)})
        except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
            # An unreachable provider would repeat the same message for every card, so it is reported once.
            results.append({"index": index, "ok": False, "error": str(error)})
    if (len(results) > 1 and all(not entry["ok"] for entry in results)
            and len({entry["error"] for entry in results}) == 1):
        first_error = next(entry["error"] for entry in results if not entry["ok"])
        skipped.append("The same error occurred for every card: %s" % first_error)
    return {"results": results, "skipped": skipped}
