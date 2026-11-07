"""HTTP endpoint behind the Director's live plan panel. Metadata only: nothing is decoded and nothing is rendered."""
from aiohttp import web
from server import PromptServer

from ..adapters import probe
from ..core.preview import plan_preview


@PromptServer.instance.routes.post("/ng/plan")
async def plan_endpoint(request):
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"ok": False, "error": "the request body is not JSON"}, status=400)
    return web.json_response(plan_preview(payload, probe=probe.duration_seconds, image_size=probe.image_size))
