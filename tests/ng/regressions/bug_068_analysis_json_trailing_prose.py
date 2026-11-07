"""BUG-068: Context Card AI Analysis fails on complete JSON accompanied by conversational prose.

Where:
- ng/core/analysis.py:201-211 (parse_suggestion)
- ng/adapters/analysis.py:129 (called in analyze)
- ng/nodes/analysis_routes.py:38, 48 (/ng/analyze, /ng/analyze_all)
- js/ng/h3c_parts.js (Context Card '✦ Analyze' button / suggestion display)

Real workflow steps:
1. Connect an AI provider in the H3 AI Loader (e.g. Ollama with Qwen/Llama, LM Studio, Gemini,
   OpenRouter, Claude, or OpenAI) and connect it to a Context Card (e.g. NGContextImage, NGContextVideo,
   NGContextAudio, or NGContextText).
2. On the context card, click '✦ Analyze' (or click 'Analyze All' in the AI Loader).
3. The AI model analyzes the media or text and returns a completely valid, full JSON object according
   to the requested schema (description, content, usage, why), but appends polite closing conversational
   prose (e.g. '...}\n\nHope this helps!'), or outputs markdown fences with commentary
   ('```json\n{...}\n```\nHere is your analysis.'), or includes leading conversational text before the code fence.

What happens (Ist):
1. Unlike auto_direct and builder (which use ai_json.read_object from BUG-061), parse_suggestion in analysis.py
   uses raw json.loads(text).
2. When trailing prose is present, json.loads() fails with JSONDecodeError ('Extra data').
   When trailing prose follows a markdown fence, lines[-1].strip() == "```" evaluates to False,
   leaving the opening fence unstripped, so json.loads() fails with JSONDecodeError ('Expecting value').
   When leading prose precedes the fence, text.startswith("```") is False, failing similarly.
3. The catch block in parse_suggestion misdiagnoses the error:
       raise ValueError("The provider's answer was not readable JSON (%s). It may have run out of "
                        "Max tokens before answering; try more tokens or another model." % error.msg)
4. The user sees this in the suggestion box and is told that the model may have run out of Max tokens.
   The user increases Max tokens on the AI Loader (e.g. 512 -> 1024 -> 2048 -> 4096), but the exact
   same failure persists on every run because the JSON was already complete and token limits were never exceeded.

What should happen (Soll):
1. parse_suggestion must robustly extract the valid JSON object even when surrounded or followed
   by conversational prose or markdown notes.
2. The error diagnosing "Max tokens" must only occur when the AI's output was genuinely cut off mid-payload.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module  # noqa: E402

analysis = module("ng.core.analysis")


def valid_suggestion(media="image"):
    return {
        "description": "A steampunk-style female warrior with mechanical gauntlets and goggles.",
        "content": "character",
        "usage": "reference",
        "why": "The armor and mechanical details establish character identity across shots."
    }


class AnalysisJSONTrailingProse(unittest.TestCase):
    def test_control_clean_raw_json_parses_normally(self):
        """Control: clean raw JSON parses without error."""
        raw = json.dumps(valid_suggestion("image"))
        suggestion = analysis.parse_suggestion(raw, media="image")
        self.assertEqual(suggestion.content, "character")
        self.assertEqual(suggestion.usage, "reference")
        self.assertTrue(suggestion.description.startswith("A steampunk-style"))

    def test_control_clean_fenced_json_parses_normally(self):
        """Control: clean markdown-fenced JSON parses without error."""
        fenced = "```json\n" + json.dumps(valid_suggestion("image")) + "\n```"
        suggestion = analysis.parse_suggestion(fenced, media="image")
        self.assertEqual(suggestion.content, "character")
        self.assertEqual(suggestion.usage, "reference")

    def test_control_genuinely_truncated_json_still_reports_unreadable(self):
        """Control: genuinely truncated JSON (cut off mid-payload) still triggers unreadable JSON error."""
        whole = json.dumps(valid_suggestion("image"))
        cut = whole[:30]
        with self.assertRaisesRegex(ValueError, "not readable JSON"):
            analysis.parse_suggestion(cut, media="image")

    def test_control_completely_invalid_text_reports_unreadable(self):
        """Control: completely non-JSON output reports that the provider answer was not readable JSON."""
        with self.assertRaisesRegex(ValueError, "not readable JSON"):
            analysis.parse_suggestion("I cannot analyze this image.", media="image")

    # --- BUG-068 Regressions: Trailing prose / commentary must not fail analysis ---

    def test_bug_068_parse_suggestion_with_trailing_prose_must_not_fail(self):
        """BUG-068: Complete JSON followed by conversational closing prose must parse the suggestion

        instead of raising 'The provider's answer was not readable JSON (Extra data). It may have run out of Max tokens...'.
        """
        raw = json.dumps(valid_suggestion("image"))
        payload = raw + "\n\nHope this helps with your scene! Let me know if you need more details."
        suggestion = analysis.parse_suggestion(payload, media="image")
        self.assertEqual(suggestion.content, "character",
                         "parse_suggestion must extract valid JSON despite trailing conversational prose")
        self.assertEqual(suggestion.usage, "reference")

    def test_bug_068_parse_suggestion_fenced_with_trailing_prose_must_not_fail(self):
        """BUG-068: Fenced JSON followed by conversational closing prose must parse the suggestion

        instead of failing on the unstripped closing fence or trailing commentary.
        """
        raw = json.dumps(valid_suggestion("image"))
        payload = "```json\n" + raw + "\n```\nHere is your context card analysis. Enjoy creating!"
        suggestion = analysis.parse_suggestion(payload, media="image")
        self.assertEqual(suggestion.content, "character",
                         "parse_suggestion must parse fenced JSON even when accompanied by trailing prose")

    def test_bug_068_parse_suggestion_with_leading_prose_must_not_fail(self):
        """BUG-068: Fenced JSON preceded by introductory conversational prose must parse the suggestion

        instead of failing because text.startswith('```') is False.
        """
        raw = json.dumps(valid_suggestion("image"))
        payload = "Here is the analysis of the character image:\n```json\n" + raw + "\n```"
        suggestion = analysis.parse_suggestion(payload, media="image")
        self.assertEqual(suggestion.content, "character",
                         "parse_suggestion must extract JSON when preceded by introductory commentary")


if __name__ == "__main__":
    unittest.main()
