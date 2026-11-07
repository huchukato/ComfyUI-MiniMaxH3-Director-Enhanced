"""BUG-042: the Google AI Studio provider builds a doubled /v1 path for every call.

The AI Loader offers "Google AI Studio". Pick it, press Load models, and the panel
asks a URL that does not exist; press Analyze on any Context card and the chat call
fails the same way. Gemini can never work, and the error text quotes an address that
looks right, so nothing points at the doubled segment.

Every provider's registry entry stores the OpenAI-compatible BASE, which is by
definition the address the OpenAI client is configured with; the SDK then appends
"/chat/completions" and "/models" to it. So for every provider the endpoints NG has
to reach are

    base + "/chat/completions"        base + "/models"

which is what Google documents for its OpenAI-compatible layer
(ai.google.dev/gemini-api/docs/openai: base_url
"https://generativelanguage.googleapis.com/v1beta/openai/", list models
"https://generativelanguage.googleapis.com/v1beta/openai/models"), and what OpenAI,
OpenRouter and Claude each publish.

The two builders only know how to strip a trailing "/v1":

    legacy.chat_completions_url:  root = base[:-3] if base.endswith("/v1") else base
    models._address:              root = base[:-3] if base.endswith("/v1") else base

That covers every entry whose base ends in "/v1" and every bare host, and misses the
one whose base already carries a full OpenAI-compatibility path, "…/v1beta/openai".
Result, from the product's own functions:

    models  https://generativelanguage.googleapis.com/v1beta/openai/v1/models
    chat    https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions

The test asserts the invariant over the whole registry, so it holds for the seven
providers that already work and fails for the one that does not.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
providers = module("ng.core.providers")
models = module("ng.adapters.models")
legacy = module("minimax_media")


def chat_url(entry):
    if entry.generate_path == providers.OLLAMA_GENERATE:
        return entry.base_url + entry.generate_path
    return legacy.chat_completions_url(entry.base_url)


def models_url(entry):
    return models._address(entry.base_url, entry.models_path)


class OpenAiCompatibleBase(unittest.TestCase):
    def test_bug_042_every_provider_chat_url_is_its_base_plus_chat_completions(self):
        for key in sorted(providers.PROVIDERS):
            entry = providers.get(key)
            if entry.generate_path == providers.OLLAMA_GENERATE:
                continue      # Ollama speaks /api/generate, checked separately below
            if not entry.base_url:
                continue      # "custom" has no address of its own; the user types one
            self.assertEqual(chat_url(entry), entry.base_url + "/chat/completions",
                             "%s: the chat endpoint is not the provider's documented one "
                             "(base %s)" % (key, entry.base_url))

    def test_bug_042_every_provider_models_url_is_its_base_plus_models(self):
        for key in sorted(providers.PROVIDERS):
            entry = providers.get(key)
            if entry.generate_path == providers.OLLAMA_GENERATE:
                continue        # Ollama's own API (/api/tags), see test_control_ollama_keeps_its_own_api_paths
            if not entry.base_url:
                continue      # "custom" has no address of its own
            self.assertEqual(models_url(entry), entry.base_url + "/models",
                             "%s: the model list is not asked from the provider's documented "
                             "endpoint (base %s)" % (key, entry.base_url))

    def test_control_ollama_keeps_its_own_api_paths(self):
        entry = providers.get("ollama")
        self.assertEqual(chat_url(entry), "http://127.0.0.1:11434/api/generate")
        self.assertEqual(models_url(entry), "http://127.0.0.1:11434/api/tags")

    def test_control_the_providers_with_a_plain_v1_base_are_already_right(self):
        # The green control for the same rule on the entries the builder was written for.
        for key, expected in (("openai", "https://api.openai.com/v1/chat/completions"),
                              ("anthropic", "https://api.anthropic.com/v1/chat/completions"),
                              ("openrouter", "https://openrouter.ai/api/v1/chat/completions")):
            entry = providers.get(key)
            self.assertEqual(chat_url(entry), expected, key)

    def test_control_a_typed_address_with_or_without_v1_keeps_working(self):
        # The behaviour the helper exists for, unchanged: /v1 is never doubled.
        self.assertEqual(legacy.chat_completions_url("http://127.0.0.1:1234"),
                         "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(legacy.chat_completions_url("http://127.0.0.1:1234/v1"),
                         "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(models._address("http://127.0.0.1:1234", "/v1/models"),
                         "http://127.0.0.1:1234/v1/models")
        self.assertEqual(models._address("http://127.0.0.1:1234/v1", "/v1/models"),
                         "http://127.0.0.1:1234/v1/models")


if __name__ == "__main__":
    unittest.main()