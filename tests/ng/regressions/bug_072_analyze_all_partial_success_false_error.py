"""BUG-072: analyze_all falsely claims 'The same error occurred for every card' on partial success.

Where:
- ng/adapters/analyze_all.py:28-30 (analyze_all)
- ng/nodes/analysis_routes.py:43-51 (POST /ng/analyze_all)
- js/ng/ng_assist.js:40-48 (summarizeBatch -> data.skipped)

User workflow:
1. In ComfyUI, connect two or more Context cards (e.g. image cards "Hero" and "Villain") to the
   H3 Context Connector and H3 AI Loader.
2. In the H3 AI Loader, set Mode to 'Assist' or 'Auto' and configure an AI provider.
3. Card 1 succeeds (e.g. valid image analysis returns description), while Card 2 fails
   (e.g. image read error, prompt failure, or provider rate limit on second call).
4. Click 'Analyze All' in the H3 AI Loader (or POST /ng/analyze_all).

What happens (Ist):
In ng/adapters/analyze_all.py:28-30:
    if len({entry["error"] for entry in results if not entry["ok"]}) == 1 and len(results) > 1:
        first_error = next(entry["error"] for entry in results if not entry["ok"])
        skipped.append("The same error occurred for every card: %s" % first_error)

Line 28 only checks if the set of errors AMONG FAILED CARDS has length 1 (`len({...}) == 1`),
and if total results > 1 (`len(results) > 1`).
It fails to verify whether ALL cards actually failed (`all(not entry["ok"] for entry in results)`).
As a result:
- If 1 card succeeds and 1 card fails: the set of errors of failed cards has length 1.
  The condition evaluates to True!
- If 9 cards succeed and 1 card fails (or 8 succeed and 2 fail with the same error):
  the condition evaluates to True!
analyze_all appends:
    "The same error occurred for every card: %s" % first_error
The user is falsely told that "The same error occurred for every card", even though cards succeeded!
This misleads the user into believing the entire batch failed globally.

What should happen (Soll):
The consolidated skip note "The same error occurred for every card: %s" must ONLY be emitted
when EVERY card actually failed with that error, i.e.:
    len([entry for entry in results if not entry["ok"]]) == len(results)
When some cards succeed (partial success), the error belongs solely to the failed cards in `results`
and must NEVER claim in `skipped` that it occurred for every card.
"""
import asyncio
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

TESTS_NG = pathlib.Path(__file__).resolve().parent.parent
REPO = TESTS_NG.parent.parent
sys.path.insert(0, str(TESTS_NG))
sys.path.insert(0, str(REPO.parent.parent))

from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()
analyze_all_adapter = module("ng.adapters.analyze_all")
analysis_routes = module("ng.nodes.analysis_routes")


class AnalyzeAllPartialSuccessFalseError(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        manager = types.SimpleNamespace(get_request_user_filepath=lambda r, p: self.tmp_dir.name)
        self.manager_patch = patch.object(analysis_routes.PromptServer.instance, "user_manager", manager, create=True)
        self.manager_patch.start()
        self.provider_config = {
            "schema_version": 2,
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "qwen2.5vl:7b",
        }

    def tearDown(self):
        self.manager_patch.stop()
        self.tmp_dir.cleanup()

    def _payload(self, cards):
        return {
            "provider": self.provider_config,
            "mode": "assist",
            "contexts": [
                {"media": "image", "widgets": {"name": name, "image": "%s.png" % name.lower()}}
                for name in cards
            ],
        }

    def test_bug_072_analyze_all_partial_success_does_not_claim_same_error_for_every_card(self):
        """RED: When Card 1 succeeds and Card 2 fails, skipped must NOT claim error occurred for every card."""
        payload = self._payload(["Hero", "Villain"])
        with patch.object(
            analyze_all_adapter,
            "analyze",
            side_effect=[
                {"description": "A brave warrior"},
                ValueError("Image file corrupted"),
            ],
        ):
            result = asyncio.run(analyze_all_adapter.analyze_all(payload))

        self.assertEqual([entry["ok"] for entry in result["results"]], [True, False])
        for msg in result["skipped"]:
            self.assertNotIn(
                "same error occurred for every card",
                msg.lower(),
                "False claim: 'same error occurred for every card' was appended to skipped even though Hero succeeded: %r"
                % result["skipped"],
            )

    def test_bug_072_analyze_all_multi_card_partial_success_with_shared_error_does_not_claim_every_card(self):
        """RED: When 1 card succeeds and 2 cards fail with the same error, skipped must not claim error for every card."""
        payload = self._payload(["CardA", "CardB", "CardC"])
        with patch.object(
            analyze_all_adapter,
            "analyze",
            side_effect=[
                {"description": "Successfully analyzed CardA"},
                ValueError("Connection reset by peer"),
                ValueError("Connection reset by peer"),
            ],
        ):
            result = asyncio.run(analyze_all_adapter.analyze_all(payload))

        self.assertEqual([entry["ok"] for entry in result["results"]], [True, False, False])
        for msg in result["skipped"]:
            self.assertNotIn(
                "same error occurred for every card",
                msg.lower(),
                "False claim: 'same error occurred for every card' was appended when CardA succeeded: %r"
                % result["skipped"],
            )

    def test_bug_072_analyze_all_route_does_not_emit_false_same_error_on_partial_success(self):
        """RED: Route POST /ng/analyze_all must not return false every-card error on partial success."""
        payload = self._payload(["Card1", "Card2"])
        with patch.object(
            analyze_all_adapter,
            "analyze",
            side_effect=[
                {"description": "Card 1 ok"},
                ValueError("Timeout reading card 2"),
            ],
        ):
            request = types.SimpleNamespace(
                json=AsyncMock(return_value=payload),
                headers={},
            )
            response = asyncio.run(analysis_routes.analyze_every_context(request))

        import json

        body = json.loads(response.text)
        self.assertTrue(body["ok"])
        self.assertEqual([entry["ok"] for entry in body["results"]], [True, False])
        for msg in body.get("skipped", []):
            self.assertNotIn(
                "same error occurred for every card",
                msg.lower(),
                "Route /ng/analyze_all emitted false 'same error occurred for every card' message: %r"
                % body.get("skipped"),
            )

    # -------------------------------------------------------------------------
    # Green Control Tests (verifying intended behavior is preserved)
    # -------------------------------------------------------------------------

    def test_control_analyze_all_true_uniform_failure_reports_same_error_for_every_card(self):
        """CONTROL (GREEN): When ALL cards fail with the exact same error, reporting it once is expected."""
        payload = self._payload(["Card1", "Card2"])
        with patch.object(
            analyze_all_adapter,
            "analyze",
            side_effect=[
                ValueError("Connection refused"),
                ValueError("Connection refused"),
            ],
        ):
            result = asyncio.run(analyze_all_adapter.analyze_all(payload))

        self.assertEqual([entry["ok"] for entry in result["results"]], [False, False])
        self.assertTrue(
            any("same error occurred for every card" in msg.lower() for msg in result["skipped"]),
            "Expected 'same error occurred for every card' when all cards truly failed with the same error: %r"
            % result["skipped"],
        )

    def test_control_analyze_all_all_cards_succeed_skipped_has_no_same_error(self):
        """CONTROL (GREEN): When all cards succeed, skipped has no same-error message."""
        payload = self._payload(["Card1", "Card2"])
        with patch.object(
            analyze_all_adapter,
            "analyze",
            side_effect=[
                {"description": "Card 1 ok"},
                {"description": "Card 2 ok"},
            ],
        ):
            result = asyncio.run(analyze_all_adapter.analyze_all(payload))

        self.assertEqual([entry["ok"] for entry in result["results"]], [True, True])
        self.assertEqual(result["skipped"], [])

    def test_control_analyze_all_distinct_failures_do_not_report_same_error(self):
        """CONTROL (GREEN): When cards fail with different errors, no same-error message is appended."""
        payload = self._payload(["Card1", "Card2"])
        with patch.object(
            analyze_all_adapter,
            "analyze",
            side_effect=[
                ValueError("File not found"),
                ValueError("Permission denied"),
            ],
        ):
            result = asyncio.run(analyze_all_adapter.analyze_all(payload))

        self.assertEqual([entry["ok"] for entry in result["results"]], [False, False])
        self.assertFalse(
            any("same error occurred for every card" in msg.lower() for msg in result["skipped"]),
            "Distinct errors must not produce a 'same error' message: %r" % result["skipped"],
        )


if __name__ == "__main__":
    unittest.main()
