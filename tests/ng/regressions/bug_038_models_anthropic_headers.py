"""BUG-038: Claude / Anthropic model listing sends Bearer instead of x-api-key, causing HTTP 401.

When a user selects source 'API' and provider 'Claude' in the H3 AI Loader (NGAIProvider)
and clicks 'Load models', the request to /ng/models fails with HTTP 401.
models.py:69 calls legacy._auth_headers(api_key) which formats:
    {"Authorization": "Bearer <key>"}
However, the Anthropic API strictly requires:
    x-api-key: <key>
    anthropic-version: 2023-06-01
and rejects Authorization: Bearer with 401 Unauthorized ('x-api-key header is required').
The correct header builder for registry providers is already implemented in
minimax_media.registry_auth_headers(entry.auth, api_key) (as used in analysis.py:54).
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
models_mod = module("ng.adapters.models")


class MockResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def json(self, content_type=None):
        return self._payload


class MockClientSession:
    """Simulates an upstream provider endpoint checking authentication headers."""
    def __init__(self, headers=None, **kwargs):
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def get(self, url, timeout=None):
        if "api.anthropic.com" in url:
            # Anthropic API requires x-api-key and rejects Authorization: Bearer
            if "x-api-key" not in self.headers:
                return MockResponse(401, {"type": "error", "error": {"type": "authentication_error", "message": "x-api-key header is required"}})
            return MockResponse(200, {"data": [{"id": "claude-3-5-sonnet-20241022"}, {"id": "claude-3-haiku-20240307"}]})
        elif "openrouter.ai" in url:
            if not self.headers.get("Authorization", "").startswith("Bearer "):
                return MockResponse(401, {"error": "Missing Bearer token"})
            return MockResponse(200, {"data": [{"id": "google/gemma-4-26b-a4b-it:free"}]})
        return MockResponse(404, {"error": "Not found"})


class ModelsAuthHeadersTest(unittest.TestCase):
    def test_bug_038_anthropic_model_listing_must_authenticate_with_x_api_key(self):
        """Anthropic must receive x-api-key header, not Authorization: Bearer."""
        with patch.object(models_mod.aiohttp, "ClientSession", MockClientSession):
            names, err = asyncio.run(models_mod.listing("anthropic", "https://api.anthropic.com", api_key="sk-ant-test-key"))
            self.assertEqual(err, "", "Listing models for Anthropic must succeed without HTTP 401 authentication error")
            self.assertEqual(names, ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"])

    def test_control_openrouter_model_listing_uses_bearer(self):
        """OpenRouter authenticates with Authorization: Bearer."""
        with patch.object(models_mod.aiohttp, "ClientSession", MockClientSession):
            names, err = asyncio.run(models_mod.listing("openrouter", "https://openrouter.ai/api/v1", api_key="sk-or-test-key"))
            self.assertEqual(err, "")
            self.assertEqual(names, ["google/gemma-4-26b-a4b-it:free"])


if __name__ == "__main__":
    unittest.main()
