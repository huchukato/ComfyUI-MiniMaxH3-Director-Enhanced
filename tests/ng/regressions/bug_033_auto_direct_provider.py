"""BUG-033: Auto Direct crashes with KeyError for cloud AI providers (OpenRouter, OpenAI, Claude, etc.).

When a user selects an API provider such as OpenRouter or OpenAI in the H3 AI Loader and
clicks 'Auto Direct' (or 'Split shots') in the Director Studio, the request to /ng/direct
fails with KeyError: 'openrouter' because auto_direct.py indexes legacy._PROVIDER_DEFAULTS
directly, which only defines 'ollama', 'lmstudio', and 'custom'.
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
auto_direct_mod = module("ng.adapters.auto_direct")
legacy = module("minimax_media")

MOCK_RESPONSE = json.dumps({
    "shots": [{"start_s": 0.0, "end_s": 10.0, "action": "A dragon in flight", "camera": "Static", "dialogue": ""}],
    "soundscape": "Wind over peaks",
    "music": "Epic orchestra",
})


class AutoDirectCloudProvider(unittest.TestCase):
    def test_bug_033_auto_direct_must_support_openrouter_without_key_error(self):
        payload = {
            "provider": {"schema_version": 2, "provider": "openrouter", "model": "google/gemma-4-26b-a4b-it:free"},
            "director": {"project_seconds": 10.0, "idea": "A dragon flies over snowy peaks.", "shots": ""},
            "contexts": [],
        }

        # Mock the external network call so no remote API is queried
        with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as mock_vlm:
            mock_vlm.return_value = MOCK_RESPONSE
            try:
                res = asyncio.run(auto_direct_mod.direct(payload))
            except KeyError as err:
                self.fail("auto_direct.direct crashed with KeyError: %s" % err)

            self.assertIn("shots", res)

    def test_control_auto_direct_supports_local_ollama_provider(self):
        payload = {
            "provider": {"schema_version": 2, "provider": "ollama", "model": "qwen2.5vl:7b"},
            "director": {"project_seconds": 10.0, "idea": "A dragon flies over snowy peaks.", "shots": ""},
            "contexts": [],
        }

        with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as mock_vlm:
            mock_vlm.return_value = MOCK_RESPONSE
            res = asyncio.run(auto_direct_mod.direct(payload))
            self.assertIn("shots", res)


if __name__ == "__main__":
    unittest.main()
