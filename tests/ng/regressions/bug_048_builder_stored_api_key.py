"""BUG-048: builder.plan and part_writer.write ignore API keys stored in api_keys.json.

When a user configures an API provider (OpenRouter, Claude, OpenAI, Gemini, etc.) in the
H3 AI Loader and saves their key via the "Save" button, it is stored in api_keys.json in
the user directory.

When clicking:
- "Make H3 prompt" (which calls builder.plan via /ng/build_plan)
- "Write with AI" for a render part (which calls part_writer.write via /ng/write_part)

Both adapters call:
    key = legacy.resolve_api_key({"api_key_env": config.api_key_env})
which only inspects os.environ and knows nothing about api_keys.json.
Since api_key_env is empty by default when a key is saved directly, key resolves to "",
and every cloud request fails with HTTP 401 Unauthorized.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
keys = module("ng.adapters.keys")
builder = module("ng.adapters.builder")
part_writer = module("ng.adapters.part_writer")
legacy = module("minimax_media")
routes = module("ng.nodes.analysis_routes")


def route_key(root, payload):
    """The key the /ng/build_plan and /ng/write_part routes hand to builder.plan / part_writer.write: the adapters get
    it from the route (stored key first, then the env var), they do not read the user folder themselves."""
    with patch.object(routes, "key_root", return_value=root):
        return routes._api_key(object(), payload)


class BuilderStoredApiKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        keys.write(self.root, "openrouter", "sk-or-v1-stored-secret-key-12345678")

    def tearDown(self):
        self.tmp.cleanup()

    def test_bug_048_builder_plan_uses_stored_api_key(self):
        captured_key = None

        async def fake_vlm_generate(*args, **kwargs):
            nonlocal captured_key
            captured_key = kwargs.get("api_key")
            return json.dumps({
                "look": "Cinematic",
                "shots": [{"start_s": 0, "end_s": 5, "action": "A woman walks.", "lines": [], "uses": []}],
                "soundscape": "Wind.",
                "music": "None.",
            })

        payload = {
            "provider": {
                "schema_version": 2,
                "provider": "openrouter",
                "model": "google/gemini-2.0-flash",
                "api_key_env": "",
                "max_tokens": 2048,
            },
            "director": {
                "idea": "A woman walks through the station.",
                "project_seconds": 5.0,
                "shots": "",
            },
            "contexts": [],
        }

        with patch.object(legacy, "vlm_generate", side_effect=fake_vlm_generate):
            asyncio.run(builder.plan(payload, api_key=route_key(self.root, payload)))

        self.assertEqual(
            captured_key,
            "sk-or-v1-stored-secret-key-12345678",
            "builder.plan must resolve and use the API key stored in the user folder",
        )

    def test_bug_048_part_writer_uses_stored_api_key(self):
        captured_key = None

        async def fake_vlm_generate(*args, **kwargs):
            nonlocal captured_key
            captured_key = kwargs.get("api_key")
            return (
                "description: [Shot 1] At 00:00.000 A woman walks through the station with steady pace. "
                "The morning sun reflects brightly off the metallic train carriages and polished floor. "
                "[Shot 2] At 00:03.000 She approaches the platform counter and checks the schedule board."
            )

        shots_doc = {
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [
                {"id": "s1", "name": "Shot 1", "start": 0, "end": 3, "text": "She walks.", "action": "She walks.", "media": [], "spoken": []},
                {"id": "s2", "name": "Shot 2", "start": 3, "end": 6, "text": "She stops.", "action": "She stops.", "media": [], "spoken": []},
            ],
            "audio": [],
            "audio_lanes": [],
        }

        payload = {
            "provider": {
                "schema_version": 2,
                "provider": "openrouter",
                "model": "google/gemini-2.0-flash",
                "api_key_env": "",
                "max_tokens": 2048,
            },
            "director": {
                "idea": "A woman at the station.",
                "project_seconds": 6.0,
                "shots": json.dumps(shots_doc),
            },
            "contexts": [],
            "part": 0,
        }

        with patch.object(legacy, "vlm_generate", side_effect=fake_vlm_generate):
            asyncio.run(part_writer.write(payload, api_key=route_key(self.root, payload)))

        self.assertEqual(
            captured_key,
            "sk-or-v1-stored-secret-key-12345678",
            "part_writer.write must resolve and use the API key stored in the user folder",
        )

    def test_control_env_var_works_when_specified(self):
        captured_key = None

        async def fake_vlm_generate(*args, **kwargs):
            nonlocal captured_key
            captured_key = kwargs.get("api_key")
            return json.dumps({
                "look": "Cinematic",
                "shots": [{"start_s": 0, "end_s": 5, "action": "A woman walks.", "lines": [], "uses": []}],
                "soundscape": "Wind.",
                "music": "None.",
            })

        payload = {
            "provider": {
                "schema_version": 2,
                "provider": "openrouter",
                "model": "google/gemini-2.0-flash",
                "api_key_env": "CUSTOM_ENV_TEST_KEY",
                "max_tokens": 2048,
            },
            "director": {
                "idea": "A woman walks through the station.",
                "project_seconds": 5.0,
                "shots": "",
            },
            "contexts": [],
        }

        with patch.dict(os.environ, {"CUSTOM_ENV_TEST_KEY": "sk-env-test-99999"}):
            with patch.object(legacy, "vlm_generate", side_effect=fake_vlm_generate):
                asyncio.run(builder.plan(payload))

        self.assertEqual(captured_key, "sk-env-test-99999")


if __name__ == "__main__":
    unittest.main()
