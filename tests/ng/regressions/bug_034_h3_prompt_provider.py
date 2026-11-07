"""BUG-034: Text card 'Build H3 prompt' crashes with KeyError for cloud AI providers (OpenRouter, OpenAI, Claude, etc.).

When a user selects an API provider such as OpenRouter or OpenAI in the H3 AI Loader and
clicks '✦ Build H3 prompt' on an NGContextText card, the request to /ng/h3prompt
fails with KeyError: 'openrouter' because h3_prompt.py indexes legacy._PROVIDER_DEFAULTS
directly, which only defines 'ollama', 'lmstudio', and 'custom'.
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
h3_prompt_mod = None   # removed module, see REMOVED below
REMOVED = 'The text card\'s "Build H3 prompt" (ng/adapters/h3_prompt.py) was removed; Make H3 prompt in the Studio replaced it.'
legacy = module("minimax_media")

MOCK_PROMPT = "A white-haired mage stands in a dark fantasy library, holding a glowing staff."


class H3PromptCloudProvider(unittest.TestCase):
    @unittest.skip(REMOVED)
    def test_bug_034_build_h3_prompt_must_support_openrouter_without_key_error(self):
        payload = {
            "provider": {"schema_version": 2, "provider": "openrouter", "model": "google/gemma-4-26b-a4b-it:free"},
            "note": "A mage casts a spell in an ancient library.",
            "seconds": 8.0,
            "preset": "global",
        }

        with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as mock_vlm:
            mock_vlm.return_value = MOCK_PROMPT
            try:
                res = asyncio.run(h3_prompt_mod.build(payload))
            except KeyError as err:
                self.fail("h3_prompt.build crashed with KeyError: %s" % err)

            self.assertIn("prompt", res)

    @unittest.skip(REMOVED)
    def test_control_build_h3_prompt_supports_local_ollama_provider(self):
        payload = {
            "provider": {"schema_version": 2, "provider": "ollama", "model": "qwen2.5vl:7b"},
            "note": "A mage casts a spell in an ancient library.",
            "seconds": 8.0,
            "preset": "global",
        }

        with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as mock_vlm:
            mock_vlm.return_value = MOCK_PROMPT
            res = asyncio.run(h3_prompt_mod.build(payload))
            self.assertIn("prompt", res)


if __name__ == "__main__":
    unittest.main()
