"""BUG-043: Stored API key in ComfyUI user folder is ignored by auto_direct, h3_prompt, and analyze.

When a user configures an API provider (e.g. OpenRouter, Claude, OpenAI) in the AI Loader
and saves their API key via the "Save" button, it is saved into api_keys.json in ComfyUI's
user directory. When clicking "Load models", /ng/models resolves the key via keys.resolve()
and succeeds.

However, when executing:
- Auto Direct (Split into shots) -> auto_direct.direct()
- Build H3 prompt (on a Text card) -> h3_prompt.build()
- Analyze (on a Context card) -> analysis.analyze()

All three adapters only call legacy.resolve_api_key({"api_key_env": config.api_key_env}),
which only looks at os.environ and ignores the stored api_keys.json completely.
As a result, api_key is passed as "" to vlm_generate, registry_auth_headers produces None,
and every cloud request fails with HTTP 401 Unauthorized.
"""
import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
keys = module("ng.adapters.keys")
auto_direct = module("ng.adapters.auto_direct")
REMOVED = "The text card's Build H3 prompt (ng/adapters/h3_prompt.py) was removed; Make H3 prompt in the Studio replaced it."
routes = module("ng.nodes.analysis_routes")


def route_key(root, payload):
    """The key the /ng/direct and /ng/analyze routes hand to the adapters: stored key first, then the env var."""
    with patch.object(routes, "key_root", return_value=root):
        return routes._api_key(object(), payload)
analysis = module("ng.adapters.analysis")
legacy = module("minimax_media")


class StoredApiKeyUsed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        # User stores an API key via the AI Loader UI
        keys.write(self.root, "openrouter", "sk-or-v1-stored-secret-key-12345678")

    def tearDown(self):
        self.tmp.cleanup()

    def test_bug_043_auto_direct_uses_stored_api_key(self):
        captured_key = None

        async def fake_vlm_generate(*args, **kwargs):
            nonlocal captured_key
            captured_key = kwargs.get("api_key")
            return '{"shots": [{"start_s": 0, "end_s": 8, "action": "Alice walks."}]}'

        payload = {
            "provider": {
                "schema_version": 2,
                "provider": "openrouter",
                "model": "google/gemini-2.0-flash",
                "api_key_env": "",
                "max_tokens": 2048,
            },
            "director": {
                "idea": "Alice walks into the station.",
                "project_seconds": 8.0,
                "shots": "",
            },
            "contexts": [],
        }

        with patch.object(legacy, "vlm_generate", side_effect=fake_vlm_generate):
            asyncio.run(auto_direct.direct(payload, api_key=route_key(self.root, payload)))

        self.assertEqual(
            captured_key,
            "sk-or-v1-stored-secret-key-12345678",
            "auto_direct must resolve and use the API key stored in the user folder",
        )

    @unittest.skip(REMOVED)
    @unittest.skip(REMOVED)
    def test_bug_043_build_h3_prompt_uses_stored_api_key(self):
        captured_key = None

        async def fake_vlm_generate(*args, **kwargs):
            nonlocal captured_key
            captured_key = kwargs.get("api_key")
            return "Prompt: Alice enters the station."

        payload = {
            "provider": {
                "schema_version": 2,
                "provider": "openrouter",
                "model": "google/gemini-2.0-flash",
                "api_key_env": "",
            },
            "note": "Alice enters the train station.",
            "seconds": 8,
            "preset": "global",
        }

        with patch.object(legacy, "vlm_generate", side_effect=fake_vlm_generate):
            asyncio.run(h3_prompt.build(payload))

        self.assertEqual(
            captured_key,
            "sk-or-v1-stored-secret-key-12345678",
            "build_h3_prompt must resolve and use the API key stored in the user folder",
        )

    def test_control_env_var_fallback_works_when_specified(self):
        """Green control: When an environment variable is explicitly specified in api_key_env,
        it is still honored."""
        captured_key = None

        async def fake_vlm_generate(*args, **kwargs):
            nonlocal captured_key
            captured_key = kwargs.get("api_key")
            return '{"shots": [{"start_s": 0, "end_s": 8, "action": "Alice walks."}]}'

        payload = {
            "provider": {
                "schema_version": 2,
                "provider": "openrouter",
                "model": "google/gemini-2.0-flash",
                "api_key_env": "TEST_EXPLICIT_ENV_KEY",
                "max_tokens": 2048,
            },
            "director": {
                "idea": "Alice walks into the station.",
                "project_seconds": 8.0,
                "shots": "",
            },
            "contexts": [],
        }

        with patch.dict(os.environ, {"TEST_EXPLICIT_ENV_KEY": "sk-env-val-9999"}):
            with patch.object(legacy, "vlm_generate", side_effect=fake_vlm_generate):
                asyncio.run(auto_direct.direct(payload))

        self.assertEqual(captured_key, "sk-env-val-9999")


if __name__ == "__main__":
    unittest.main()
