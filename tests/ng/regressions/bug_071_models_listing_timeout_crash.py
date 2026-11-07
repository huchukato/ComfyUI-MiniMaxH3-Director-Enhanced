"""BUG-071: models.listing and /ng/models route crash on TimeoutError instead of returning empty list with reason.

Where:
- ng/adapters/models.py:63-84 (listing)
- ng/nodes/context_routes.py:32-53 (list_models)
- js/ng/ng_ai_panel.js:305-315 (loadModelsButton / /ng/models fetch)

User workflow:
1. Connect an AI provider in the H3 AI Loader (e.g. Ollama, llama.cpp, LM Studio, or an OpenAI-compatible / cloud provider).
2. The server at base_url is slow, hanging, overloaded, or firewalled (e.g. dropping SYN packets without RST).
3. The user clicks "Refresh models" in the AI configuration panel.
4. The client makes a POST request to /ng/models.
5. After the configured timeout (15s default), aiohttp/asyncio raises TimeoutError (builtins.TimeoutError / asyncio.TimeoutError).

What happens (Ist):
1. models.listing claims in its docstring:
   "The model names this address currently serves. Never raises: an unreachable provider is an empty
   list plus a reason, because a panel with no list must still let the user type a name."
2. However, models.listing only catches `aiohttp.ClientError` and `(ValueError, TypeError)`.
   In Python 3.11+, TimeoutError inherits from OSError and Exception, NOT from aiohttp.ClientError!
3. Therefore, TimeoutError escapes models.listing completely unhandled.
4. The route handler `list_models` in context_routes.py only catches `(ValueError, KeyError, TypeError)`.
   It does not catch TimeoutError or OSError either.
5. The unhandled TimeoutError escapes to the aiohttp server, producing an unhandled exception traceback
   in ComfyUI's server console and returning HTTP 500 (Internal Server Error) to the frontend, instead
   of returning a graceful {"ok": false, "models": [], "reason": "..."} response explaining the timeout.

What should happen (Soll):
1. models.listing must catch TimeoutError / asyncio.TimeoutError (or OSError/ClientTimeout) and return
   `([], "Could not reach %s (request timed out). Check the address and whether the server is running." % url)`.
2. The route `/ng/models` must safely handle timeouts and return an informative response rather than crashing.
"""
import asyncio
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

TESTS_NG = pathlib.Path(__file__).resolve().parent.parent
REPO = TESTS_NG.parent.parent
sys.path.insert(0, str(TESTS_NG))
sys.path.insert(0, str(REPO.parent.parent))
saved_argv = sys.argv
sys.argv = [sys.argv[0], "--cpu"]
from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()
models = module("ng.adapters.models")
context_routes = module("ng.nodes.context_routes")
sys.argv = saved_argv


class ModelsListingTimeoutCrash(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        manager = types.SimpleNamespace(get_request_user_filepath=lambda r, p: self.tmp_dir.name)
        self.manager_patch = patch.object(context_routes.PromptServer.instance, "user_manager", manager, create=True)
        self.manager_patch.start()

    def tearDown(self):
        self.manager_patch.stop()
        self.tmp_dir.cleanup()

    # --- Green Controls ---

    def test_control_successful_listing_returns_model_names_and_empty_reason(self):
        """Control: successful HTTP 200 response returns parsed model list and empty reason."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2:3b"}]})

        class MockGetContext:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                pass

        with patch("aiohttp.ClientSession.get", return_value=MockGetContext()):
            names, reason = asyncio.run(models.listing("ollama", "http://127.0.0.1:11434"))
            self.assertEqual(names, ["llama3.2:3b", "qwen2.5:7b"])
            self.assertEqual(reason, "")

    def test_control_http_error_response_returns_empty_list_and_status_reason(self):
        """Control: HTTP 404 response returns empty list and HTTP status reason."""
        mock_response = MagicMock()
        mock_response.status = 404

        class MockGetContext:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                pass

        with patch("aiohttp.ClientSession.get", return_value=MockGetContext()):
            names, reason = asyncio.run(models.listing("ollama", "http://127.0.0.1:11434"))
            self.assertEqual(names, [])
            self.assertIn("The provider answered HTTP 404", reason)

    def test_control_client_connection_error_returns_empty_list_and_connection_reason(self):
        """Control: aiohttp.ClientConnectionError returns empty list and unreachable message."""
        import aiohttp

        with patch("aiohttp.ClientSession.get", side_effect=aiohttp.ClientConnectionError("Connection refused")):
            names, reason = asyncio.run(models.listing("ollama", "http://127.0.0.1:11434"))
            self.assertEqual(names, [])
            self.assertIn("Could not reach", reason)

    # --- BUG-071 Red Regression Tests ---

    def test_bug_071_models_listing_timeout_must_not_raise_and_return_empty_list_with_reason(self):
        """BUG-071: models.listing must catch TimeoutError and return ([], reason) instead of raising unhandled exception.

        Docstring promises: 'Never raises: an unreachable provider is an empty list plus a reason'.
        """
        with patch("aiohttp.ClientSession.get", side_effect=asyncio.TimeoutError("Connection timed out")):
            try:
                names, reason = asyncio.run(models.listing("ollama", "http://127.0.0.1:11434", timeout=5))
            except TimeoutError as exc:
                self.fail(f"BUG-071: models.listing failed to catch {type(exc).__name__}: {exc}. "
                          "Unreachable provider on timeout must return an empty list and a reason string.")

            self.assertEqual(names, [], "Models list must be empty on timeout")
            self.assertTrue(len(reason) > 0, "A reason string must explain the timeout to the user")
            self.assertTrue("timed out" in reason.lower() or "reach" in reason.lower(),
                            f"Reason must mention timeout or unreachable server, got: {reason!r}")

    def test_bug_071_list_models_route_on_timeout_must_not_crash_with_unhandled_exception(self):
        """BUG-071: The /ng/models route (list_models) must safely handle timeouts without crashing.

        When models.listing times out, list_models must not allow TimeoutError to bubble up to the
        aiohttp server as an unhandled 500 error.
        """
        request = MagicMock()
        request.json = AsyncMock(return_value={"provider": "ollama", "base_url": "http://127.0.0.1:11434"})

        with patch("aiohttp.ClientSession.get", side_effect=asyncio.TimeoutError("Connection timed out")):
            try:
                response = asyncio.run(context_routes.list_models(request))
            except TimeoutError as exc:
                self.fail(f"BUG-071: /ng/models route crashed with unhandled {type(exc).__name__}: {exc}. "
                          "The route must catch timeout and return a response object.")

            self.assertIsNotNone(response, "Route must return a valid web.Response")
            # In aiohttp web.json_response, status defaults to 200 with ok: False or 400 with reason
            self.assertIn(response.status, (200, 400), f"Expected status 200 or 400, got {response.status}")


if __name__ == "__main__":
    unittest.main()
