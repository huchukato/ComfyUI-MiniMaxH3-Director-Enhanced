"""BUG-042: documented Gemini paths, with existing bare localhost contracts.

The registry mixes bare local hosts and API roots, so base+suffix is not a universal
invariant. Google documents /v1beta/openai/{models,chat/completions}:
https://ai.google.dev/gemini-api/docs/openai
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "ng"))
sys.path.insert(0, str(REPO.parent.parent))
saved_argv = sys.argv
sys.argv = [sys.argv[0], "--cpu"]
from _pack import module, stub_prompt_server
stub_prompt_server()
providers = module("ng.core.providers")
models = module("ng.adapters.models")
legacy = module("minimax_media")
sys.argv = saved_argv


class RegistryURLs(unittest.TestCase):
    def test_bug_042_gemini_chat_uses_documented_openai_compatibility_path(self):
        entry = providers.get("gemini")
        self.assertEqual(legacy.chat_completions_url(entry.base_url),
                         "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")

    def test_bug_042_gemini_listing_uses_documented_openai_compatibility_path(self):
        entry = providers.get("gemini")
        self.assertEqual(models._address(entry.base_url, entry.models_path),
                         "https://generativelanguage.googleapis.com/v1beta/openai/models")

    def test_control_other_registry_providers_keep_existing_protocol(self):
        for provider, chat, listing in (
            ("lmstudio", "http://127.0.0.1:1234/v1/chat/completions", "http://127.0.0.1:1234/v1/models"),
            ("llamacpp", "http://127.0.0.1:8080/v1/chat/completions", "http://127.0.0.1:8080/v1/models"),
            ("openai", "https://api.openai.com/v1/chat/completions", "https://api.openai.com/v1/models"),
            ("anthropic", "https://api.anthropic.com/v1/chat/completions", "https://api.anthropic.com/v1/models"),
            ("openrouter", "https://openrouter.ai/api/v1/chat/completions", "https://openrouter.ai/api/v1/models"),
        ):
            with self.subTest(provider=provider):
                entry = providers.get(provider)
                self.assertEqual(legacy.chat_completions_url(entry.base_url), chat)
                self.assertEqual(models._address(entry.base_url, entry.models_path), listing)

    def test_control_ollama_does_not_acquire_openai_paths(self):
        entry = providers.get("ollama")
        self.assertEqual(entry.base_url + entry.generate_path, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(models._address(entry.base_url, entry.models_path), "http://127.0.0.1:11434/api/tags")

    def test_control_typed_hosts_with_and_without_v1_keep_working(self):
        for base in ("http://127.0.0.1:1234", "http://127.0.0.1:1234/v1"):
            with self.subTest(base=base):
                self.assertEqual(legacy.chat_completions_url(base), "http://127.0.0.1:1234/v1/chat/completions")
                self.assertEqual(models._address(base, "/v1/models"), "http://127.0.0.1:1234/v1/models")

    def test_control_custom_proxy_paths_keep_their_version_segment(self):
        base = "http://host/proxy/v1/openai"
        self.assertEqual(legacy.chat_completions_url(base), base + "/v1/chat/completions")
        self.assertEqual(models._address(base, "/v1/models"), base + "/v1/models")


if __name__ == "__main__":
    unittest.main(verbosity=2)
