import json
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch
from _pack import module, comfy_available, stub_prompt_server


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class Routes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stub_prompt_server()
        self.context = module("ng.nodes.context_routes")
        self.analysis = module("ng.nodes.analysis_routes")
        self.directory = tempfile.TemporaryDirectory()
        self.root = patch.object(self.context, "preset_root", return_value=self.directory.name)
        self.root.start()

    async def asyncTearDown(self):
        self.root.stop()
        self.directory.cleanup()

    async def test_malformed_requests_return_actionable_json(self):
        for payload in (None, [], {"media": "unknown", "widgets": {}, "name": "x"}):
            request = types.SimpleNamespace(json=AsyncMock(return_value=payload))
            for route in (self.context.write_preset, self.analysis.analyze_context):
                with self.subTest(route=route.__name__, payload=payload):
                    response = await route(request)
                    self.assertEqual(response.status, 400)
                    self.assertFalse(json.loads(response.text)["ok"])

    async def test_analyze_all_route_reports_a_bad_request_as_json(self):
        # The batch route has to answer with the same ok/error shape, otherwise the panel shows a raw exception.
        for payload in (None, [], {"contexts": [], "provider": {"provider": "magic"}}):
            request = types.SimpleNamespace(json=AsyncMock(return_value=payload))
            response = await self.analysis.analyze_every_context(request)
            self.assertEqual(response.status, 400)
            self.assertFalse(json.loads(response.text)["ok"])

    async def test_analyze_all_route_returns_results_and_skipped(self):
        payload = {"provider": {"schema_version": 1, "provider": "custom", "base_url": "", "model": ""},
                   "mode": "manual", "contexts": [{"media": "image", "widgets": {"image": "a.png"}}]}
        response = await self.analysis.analyze_every_context(types.SimpleNamespace(json=AsyncMock(return_value=payload)))
        body = json.loads(response.text)
        self.assertTrue(body["ok"])
        self.assertEqual(body["results"], [])
        self.assertIn("Manual", body["skipped"][0])

    async def test_preset_roundtrip_and_media_mismatch(self):
        payload = {"name": "Camera", "media": "text", "widgets": {"name": "Camera", "text": "Slow camera.", "context_id": "ctx-roundtrip"}}
        response = await self.context.write_preset(types.SimpleNamespace(json=AsyncMock(return_value=payload)))
        self.assertEqual(response.status, 200)
        request = types.SimpleNamespace(query={"name": "Camera", "media": "text"})
        response = await self.context.read_preset(request)
        self.assertEqual(json.loads(response.text)["widgets"]["context_id"], "ctx-roundtrip")
        request.query["media"] = "audio"
        self.assertEqual((await self.context.read_preset(request)).status, 400)

    async def test_media_path_failure_returns_json(self):
        for source in ("../outside.png", 42):
            response = await self.context.media_preview(types.SimpleNamespace(query={"media": "image", "source": source}))
            self.assertEqual(response.status, 400)
            self.assertFalse(json.loads(response.text)["ok"])
