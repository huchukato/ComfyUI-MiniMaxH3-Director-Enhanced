"""BUG-061: AI response parsing misdiagnoses complete JSON with trailing conversational prose as cut off by Max tokens.

Where:
- ng/core/auto_direct.py:77-80 (parse_direction)
- ng/core/builder.py:348-351 (read_answer)

Real workflow steps:
1. In Director Studio, connect an AI Loader (e.g. Ollama with Qwen/Llama, LM Studio, Gemini, or Claude).
2. Enter an Idea or connect Context cards.
3. Click "Split into shots" (calls /ng/direct -> auto_direct.parse_direction) or
   "Make H3 prompt" (calls /ng/build_plan -> builder.read_answer).
4. The language model generates a completely valid, full JSON response, but includes
   conversational remarks at the end (e.g. '...}\n\nHope this helps with your video!'),
   or outputs markdown fences with conversational prose afterwards ('```json\n{...}\n```\nHere is your plan.').

What happens (Ist):
1. In both functions:
   When trailing prose is appended to valid JSON, json.loads() fails with JSONDecodeError ('Extra data').
   The catch block tests:
       if text.lstrip().startswith("{") and not text.rstrip().endswith("}"):
           raise ValueError("The AI's answer stopped before its JSON was complete. "
                            "Raise Max tokens on the AI Loader and try again.")
   Because text starts with '{' but ends with conversational punctuation/letters (e.g. '!'),
   the heuristic incorrectly diagnoses the response as truncated due to Max tokens!
   The user is instructed: "Raise Max tokens on the AI Loader and try again."
   The user increases Max tokens from 512 to 1024, 2048, 4096, 8192, yet the exact same error
   persists indefinitely because the JSON was already complete and token limits were never exceeded.
2. In auto_direct.parse_direction:
   Code fences with trailing text (e.g. '```json\n{...}\n```\nHere is your plan.') fail because
   lines[-1].startswith("```") evaluates to False on the trailing text, so the closing fence is
   not stripped, causing json.loads to fail and raising an unhelpful error.

What should happen (Soll):
1. The parser must robustly extract the valid JSON object (e.g. via json.JSONDecoder.raw_decode or
   by isolating the outermost matching braces '{' ... '}').
2. The error "Raise Max tokens on the AI Loader and try again" must ONLY be raised when the AI's
   output was ACTUALLY truncated mid-JSON (e.g. an unclosed string or unclosed root dictionary).
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module  # noqa: E402

direction = module("ng.core.auto_direct")
builder = module("ng.core.builder")


def valid_plan():
    return {
        "look": "A cinematic sunlit laboratory with retro-futuristic displays.",
        "shots": [
            {"start_s": 0, "end_s": 4, "action": "Alice enters the lab and inspects the console.",
             "camera": "The camera slowly dollies forward.", "lines": []},
            {"start_s": 4, "end_s": 8, "action": "Alice turns towards the window and observes the sunset.",
             "camera": "The camera pans to follow her gaze.", "lines": []}
        ],
        "soundscape": "Low electronic hum and gentle wind outside.",
        "music": "N/A"
    }


class AIResponseTrailingProse(unittest.TestCase):
    def test_control_clean_raw_json_parses_normally(self):
        """Control: clean raw JSON parses without error in both functions."""
        raw = json.dumps(valid_plan())
        res_dir = direction.parse_direction(raw, 8)
        self.assertIn("shots", res_dir)
        res_bld = builder.read_answer(raw)
        self.assertIn("shots", res_bld)

    def test_control_clean_fenced_json_parses_normally(self):
        """Control: clean markdown-fenced JSON parses without error."""
        fenced = "```json\n" + json.dumps(valid_plan()) + "\n```"
        res_dir = direction.parse_direction(fenced, 8)
        self.assertIn("shots", res_dir)
        res_bld = builder.read_answer(fenced)
        self.assertIn("shots", res_bld)

    def test_control_genuinely_truncated_json_still_raises_max_tokens(self):
        """Control: genuinely truncated JSON (cut off mid-payload) still triggers the Max tokens error."""
        whole = json.dumps(valid_plan())
        cut = whole[:len(whole) // 2]
        with self.assertRaisesRegex(ValueError, "Raise Max tokens"):
            direction.parse_direction(cut, 8)
        with self.assertRaisesRegex(ValueError, "Raise Max tokens"):
            builder.read_answer(cut)

    def test_control_completely_invalid_text_reports_generative_model(self):
        """Control: completely non-JSON output still reports that the AI did not return valid JSON."""
        with self.assertRaisesRegex(ValueError, "generative model"):
            direction.parse_direction("I am unable to direct this scene.", 8)
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            builder.read_answer("I am unable to direct this scene.")

    # --- BUG-061 Regressions: Trailing commentary / prose must not fail or falsely claim Max tokens ---

    def test_bug_061_auto_direct_parse_direction_with_trailing_prose_must_not_fail(self):
        """BUG-061: Complete JSON followed by conversational closing prose must parse the plan

        instead of raising 'The AI's answer stopped before its JSON was complete. Raise Max tokens...'.
        """
        raw = json.dumps(valid_plan())
        payload = raw + "\n\nHope this helps with your video project! Let me know if you need changes."
        result = direction.parse_direction(payload, 8)
        self.assertIn("shots", result,
                      "parse_direction must extract and parse the complete JSON plan despite trailing commentary")

    def test_bug_061_builder_read_answer_with_trailing_prose_must_not_fail(self):
        """BUG-061: builder.read_answer with trailing conversational prose must parse the plan

        instead of raising 'The AI's answer stopped before its JSON was complete. Raise Max tokens...'.
        """
        raw = json.dumps(valid_plan())
        payload = raw + "\n\nHope this helps with your video project! Let me know if you need changes."
        result = builder.read_answer(payload)
        self.assertIn("shots", result,
                      "read_answer must extract and parse the complete JSON plan despite trailing commentary")

    def test_bug_061_auto_direct_fenced_json_with_trailing_prose_must_not_fail(self):
        """BUG-061: Fenced JSON followed by conversational closing prose must parse the plan

        instead of failing on the unstripped closing fence or trailing commentary.
        """
        raw = json.dumps(valid_plan())
        payload = "```json\n" + raw + "\n```\nHere is your 8-second director plan. Enjoy creating!"
        result = direction.parse_direction(payload, 8)
        self.assertIn("shots", result,
                      "parse_direction must parse fenced JSON even when accompanied by trailing prose")


if __name__ == "__main__":
    unittest.main()
