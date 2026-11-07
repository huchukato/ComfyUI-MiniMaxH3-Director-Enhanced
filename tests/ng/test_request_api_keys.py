"""BUG-043/048: real HTTP route -> adapter -> mocked transport, dummy user stores.

No provider network, GPU work, real key reads or workflow key fields. Tests import
the real package via the project's existing harness, and only use temporary keys.
Run with the embedded Python and -B. The store-root contract belongs to the route.
"""
import asyncio
import copy
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "ng"))
sys.path.insert(0, str(REPO.parent.parent))
saved_argv = sys.argv
sys.argv = [sys.argv[0], "--cpu"]
from _pack import module, comfy_available, stub_prompt_server
comfy_available()
stub_prompt_server()
keys = module("ng.adapters.keys")
legacy = module("minimax_media")
context_routes = module("ng.nodes.context_routes")
analysis_routes = module("ng.nodes.analysis_routes")
sys.argv = saved_argv

CONFIG = {"schema_version": 2, "provider": "openrouter", "model": "dummy-model",
          "api_key_env": "", "max_tokens": 2048}
DIRECTOR = {"idea": "Alice walks into a station.", "project_seconds": 5.0, "shots": ""}
CONTEXT = {"media": "text", "widgets": {"name": "Direction", "text": "A woman enters the station."}}
ROUTES = {
    "analyze": (analysis_routes.analyze_context, {"provider": CONFIG, **CONTEXT}),
    "direct": (analysis_routes.direct_scenes, {"provider": CONFIG, "director": DIRECTOR, "contexts": []}),
    "build": (analysis_routes.build_plan, {"provider": CONFIG, "director": DIRECTOR, "contexts": []}),
    "write": (analysis_routes.write_part_prompt, {"provider": CONFIG, "director": DIRECTOR, "contexts": [], "part": 0}),
    "analyze_all": (analysis_routes.analyze_every_context,
                    {"provider": CONFIG, "contexts": [CONTEXT, {**CONTEXT, "widgets": {"name": "Camera", "text": "Slow camera."}}]}),
}


class StoredKeysThroughRoutes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.roots = {user: str(Path(self.directory.name) / user) for user in ("alice", "bob")}
        self.tokens = {"alice": "dummy-alice-credential-0000", "bob": "dummy-bob-credential-0000"}
        for user, root in self.roots.items():
            keys.write(root, "openrouter", self.tokens[user])
        self.credential_calls = []
        self.active_action = ""
        self.raise_transport = False

        def request_root(request, suffix):
            self.assertEqual(suffix, "minimax_h3_ng/api_keys")
            return self.roots[request.user]

        manager = types.SimpleNamespace(get_request_user_filepath=request_root)
        self.manager = patch.object(context_routes.PromptServer.instance, "user_manager", manager, create=True)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.transport = patch.object(legacy, "vlm_generate", side_effect=self.fake_transport)
        self.manager.start()
        self.env.start()
        self.transport.start()

    async def asyncTearDown(self):
        self.transport.stop()
        self.env.stop()
        self.manager.stop()
        self.directory.cleanup()

    async def fake_transport(self, *args, **kwargs):
        token = kwargs.get("api_key")
        self.credential_calls.append(token)
        if self.raise_transport:
            raise legacy.VLMError("Synthetic provider error with " + (token or "no key"))
        if self.active_action in ("analyze", "analyze_all"):
            return '{"usage": "constraint", "why": "Keep the direction."}'
        if self.active_action == "direct":
            return '{"shots": [{"start_s": 0, "end_s": 5, "action": "Alice walks into the station."}]}'
        if self.active_action == "build":
            return json.dumps({"look": "Cinematic", "shots": [{"start_s": 0, "end_s": 5,
                              "action": "A woman walks into the station.", "lines": [], "uses": []}],
                              "soundscape": "Wind.", "music": "None."})
        return ("description: [Shot 1] A woman walks through the station with a steady pace. "
                "The morning sun reflects brightly off the train carriages and polished floor. "
                "Her coat moves slightly as she approaches the counter. The camera follows her "
                "at waist height. She looks toward the schedule board and slows beside the "
                "platform entrance. Warm daylight falls across the waiting area. The scene "
                "retains a natural cinematic appearance with detailed fabric and metal textures.")

    async def invoke(self, action, user="alice", env_name="", payload_extra=None):
        route, template = ROUTES[action]
        payload = copy.deepcopy(template)
        payload["provider"]["api_key_env"] = env_name
        if payload_extra:
            payload.update(payload_extra)
        self.active_action = action
        request = types.SimpleNamespace(json=AsyncMock(return_value=payload), user=user)
        response = await route(request)
        return response, json.loads(response.text)

    async def test_bug_043_and_048_each_current_route_uses_the_request_users_saved_key(self):
        for action in ROUTES:
            with self.subTest(action=action):
                self.credential_calls.clear()
                response, body = await self.invoke(action)
                self.assertEqual(response.status, 200)
                self.assertTrue(body["ok"])
                self.assertTrue(self.credential_calls, "The real adapter must call the transport")
                self.assertTrue(all(value == self.tokens["alice"] for value in self.credential_calls),
                                action + " ignored this request user's stored credential")
                self.assertNotIn(self.tokens["alice"], response.text)

    async def test_bug_request_users_do_not_share_keys_on_any_route(self):
        for action in ROUTES:
            with self.subTest(action=action):
                seen = []
                for user in ("alice", "bob", "alice"):
                    self.credential_calls.clear()
                    await self.invoke(action, user)
                    seen.append(self.credential_calls[0])
                self.assertTrue(seen == [self.tokens["alice"], self.tokens["bob"], self.tokens["alice"]],
                                action + " must preserve request-user isolation")

    async def test_bug_saved_key_wins_over_named_env_on_every_route(self):
        os.environ["DUMMY_NAMED_ENV"] = "dummy-environment-credential"
        for action in ROUTES:
            with self.subTest(action=action):
                self.credential_calls.clear()
                await self.invoke(action, env_name="DUMMY_NAMED_ENV")
                self.assertTrue(all(value == self.tokens["alice"] for value in self.credential_calls),
                                action + " must honor the documented stored-key-first order")

    async def test_control_without_stored_key_named_env_remains_supported(self):
        keys.write(self.roots["alice"], "openrouter", "")
        os.environ["DUMMY_NAMED_ENV"] = "dummy-environment-credential"
        for action in ROUTES:
            with self.subTest(action=action):
                self.credential_calls.clear()
                await self.invoke(action, env_name="DUMMY_NAMED_ENV")
                self.assertTrue(all(value == os.environ["DUMMY_NAMED_ENV"] for value in self.credential_calls),
                                action + " must retain named environment fallback")

    async def test_bug_saved_credential_is_redacted_from_transport_errors(self):
        self.raise_transport = True
        for action in ROUTES:
            with self.subTest(action=action):
                self.credential_calls.clear()
                _, body = await self.invoke(action)
                self.assertTrue(self.credential_calls[0] == self.tokens["alice"],
                                action + " must first resolve the user's stored credential")
                self.assertNotIn(self.tokens["alice"], json.dumps(body))
                self.assertIn("[redacted]", json.dumps(body))

    async def test_control_named_env_credentials_are_redacted(self):
        keys.write(self.roots["alice"], "openrouter", "")
        os.environ["DUMMY_NAMED_ENV"] = "dummy-environment-credential"
        self.raise_transport = True
        for action in ROUTES:
            with self.subTest(action=action):
                _, body = await self.invoke(action, env_name="DUMMY_NAMED_ENV")
                self.assertNotIn(os.environ["DUMMY_NAMED_ENV"], json.dumps(body))
                self.assertIn("[redacted]", json.dumps(body))

    async def test_control_model_route_already_uses_request_users_store(self):
        captured = []

        async def listing(provider, base_url, token):
            captured.append(token)
            return ["dummy-model"], ""

        with patch.object(context_routes.models, "listing", side_effect=listing):
            for user in ("alice", "bob"):
                payload = {"provider": "openrouter", "base_url": "", "key_env": ""}
                response = await context_routes.list_models(types.SimpleNamespace(json=AsyncMock(return_value=payload), user=user))
                self.assertTrue(json.loads(response.text)["ok"])
                self.assertNotIn(self.tokens[user], response.text)
        self.assertTrue(captured == [self.tokens["alice"], self.tokens["bob"]])

    async def test_control_request_payload_cannot_override_server_credential(self):
        keys.write(self.roots["alice"], "openrouter", "")
        response, _ = await self.invoke("direct", payload_extra={"api_key": "dummy-untrusted-request-key"})
        self.assertEqual(response.status, 200)
        self.assertFalse(self.credential_calls[0], "The route must not trust a browser-injected credential")


if __name__ == "__main__":
    unittest.main(verbosity=2)
