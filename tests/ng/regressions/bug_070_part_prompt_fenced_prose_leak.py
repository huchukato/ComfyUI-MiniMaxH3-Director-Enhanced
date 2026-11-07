"""BUG-070: Part-Prompt AI response parser leaks markdown fences / trailing prose and falsely rejects section mentions.

Where:
- ng/core/part_prompt.py:154-165 (_answer_fields), 261-299 (check)
- ng/core/part_writer.py:63-72 (finish -> check)
- ng/adapters/part_writer.py:40-42 (write -> finish)
- js/ng/h3s_prompts.js:34-41 (drawer view displays draft.problems or draft.text)
- js/ng/h3s_studio.js:256-261 (acceptPart)

Real workflow steps:
1. Open Director Studio in ComfyUI and open the drawer 'Prompts per render part'.
2. Click 'Write with AI' (or 'Write all parts with AI') on a render part.
3. An LLM (e.g. Qwen, Gemma, Llama, Claude, Gemini, OpenAI) rewrites the part prompt.
   As is standard for chat/generative LLMs, the model formats its response in a markdown
   code fence and adds conversational commentary:
   - Preamble before the code block: 'Here is the rewritten description for part 1:\n```markdown\n...'
   - Closing fence with polite sign-off: '```\nHope this helps with your scene!'
   - Or notes about what was kept: '```\nNote: I kept overall_soundscape: as planned.'

What happens (Ist):
1. In ng/core/part_prompt.py:156, _answer_fields checks only:
     if text.startswith("```"):
   When preamble precedes the code block, this condition is False, so no fence stripping occurs.
2. ANSWER_RE matches section headers across the text. The final matched section
   (e.g. 'non_diegetic_music' or 'description') captures all remaining text up to len(text),
   including the closing markdown fence '```' and any following conversational text.
3. If the trailing prose mentions any other prompt section keyword (e.g. 'Note: I kept overall_soundscape:'),
   check() triggers the nested section guard (line 284):
     problems.append("it nests another prompt section inside the description")
   and rejects the valid proposal (final is None). The user sees in the Studio:
   "The AI's version was not used: it nests another prompt section inside the description."
4. If no section keyword is present in the sign-off, the closing backticks and conversational text
   leak verbatim into the final prompt:
     non_diegetic_music: Gentle orchestral strings. ``` Hope this helps with your scene!
   which is baked into the video generation prompt sent to MiniMax / KSampler.

What should happen (Soll):
1. Code block fences (``` or ```markdown) and surrounding conversational preamble / sign-offs
   must be stripped cleanly, extracting only the actual prompt fields.
2. The final compiled prompt must contain only clean prompt text without leaked markdown backticks
   or conversational closing prose.
3. Conversational commentary outside the code fence must never trigger false-positive
   nested section rejections.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module  # noqa: E402

part_prompt = module("ng.core.part_prompt")


SAMPLE_COMPILED = (
    "How the reference pictures align with the target video:\n"
    "integrated_multimodal_description: [Shot 1] The camera pushes in on the character in the dim light.\n"
    "overall_soundscape: Forest sounds.\n"
    "non_diegetic_music: Strings."
)

SAMPLE_DESCRIPTION = (
    "[Shot 1] The camera pushes in on the character in the dim light as the autumn leaves "
    "fall around her slowly through the cold mist of the morning forest with high detail "
    "and realistic movement. The soft rays of the morning sun break through the dense canopy, "
    "casting gentle shadows across her weathered leather coat. She stands silently, listening "
    "to the whispering wind as the mist begins to clear."
)


class PartPromptFencedProseLeak(unittest.TestCase):
    def test_bug_070_fenced_part_prompt_does_not_leak_backticks_or_closing_prose(self):
        """RED: Markdown backticks and trailing prose must not leak into final prompt fields."""
        answer = (
            "Here is the rewritten description for part 1:\n"
            "```markdown\n"
            f"description: {SAMPLE_DESCRIPTION}\n"
            "overall_soundscape: Soft forest wind blowing through the pine trees.\n"
            "non_diegetic_music: Gentle orchestral strings.\n"
            "```\n"
            "Hope this helps with your scene!"
        )
        final, problems = part_prompt.check(SAMPLE_COMPILED, answer)
        self.assertEqual(problems, [], f"Valid prompt should not be rejected, got problems: {problems}")
        self.assertIsNotNone(final, "Final prompt must be generated")
        self.assertNotIn("```", final, "Markdown code fence backticks leaked into final prompt")
        self.assertNotIn("Hope this helps", final, "Closing conversational prose leaked into final prompt")
        self.assertNotIn("Here is the rewritten description", final, "Introductory preamble leaked into final prompt")

    def test_bug_070_trailing_commentary_mentioning_section_not_rejected_as_nested(self):
        """RED: Commentary outside the code block mentioning a section name must not trigger rejection."""
        answer = (
            "Here is your prompt:\n"
            "```markdown\n"
            f"description: {SAMPLE_DESCRIPTION}\n"
            "```\n"
            "Note: I did not modify overall_soundscape: or non_diegetic_music: in this pass."
        )
        final, problems = part_prompt.check(SAMPLE_COMPILED, answer)
        self.assertNotIn("it nests another prompt section inside the description", problems,
                         "Commentary outside code fence was falsely parsed as a nested section")
        self.assertEqual(problems, [])
        self.assertIsNotNone(final)
        self.assertNotIn("```", final)
        self.assertNotIn("Note: I did not modify", final)

    def test_bug_070_answer_fields_strips_fences_when_preceded_by_intro_text(self):
        """RED: _answer_fields must strip fences and trailing text even when intro prose is present."""
        answer = (
            "Certainly, here is the requested part prompt:\n"
            "```markdown\n"
            f"description: {SAMPLE_DESCRIPTION}\n"
            "overall_soundscape: Distant thunder and rain.\n"
            "non_diegetic_music: Low cello drone.\n"
            "```\n"
            "Let me know if you would like any revisions!"
        )
        fields = part_prompt._answer_fields(answer)
        music = fields.get("non_diegetic_music", "")
        self.assertNotIn("```", music, "Backticks leaked into non_diegetic_music field")
        self.assertNotIn("Let me know", music, "Trailing conversational text leaked into non_diegetic_music field")
        self.assertEqual(music, "Low cello drone.")

    def test_control_clean_unfenced_prompt_parses_and_checks_normally(self):
        """GREEN Control: Clean prompt without markdown fences or commentary parses and checks cleanly."""
        answer = (
            f"description: {SAMPLE_DESCRIPTION}\n"
            "overall_soundscape: Soft forest wind.\n"
            "non_diegetic_music: Strings."
        )
        final, problems = part_prompt.check(SAMPLE_COMPILED, answer)
        self.assertEqual(problems, [])
        self.assertIsNotNone(final)
        self.assertIn("integrated_multimodal_description:", final)
        self.assertIn("overall_soundscape: Soft forest wind.", final)
        self.assertIn("non_diegetic_music: Strings.", final)

    def test_control_genuinely_malformed_prompt_missing_shot_is_rejected(self):
        """GREEN Control: Genuinely broken answer missing required [Shot 1] marker is rejected."""
        broken_answer = (
            "description: The camera pushes in on the character in the dim light as autumn leaves fall "
            "around her slowly through the cold mist of the morning forest with high detail and realistic "
            "movement. Soft morning sun breaks through the dense canopy casting gentle shadows across her coat.\n"
            "overall_soundscape: Forest sounds.\n"
            "non_diegetic_music: Strings."
        )
        final, problems = part_prompt.check(SAMPLE_COMPILED, broken_answer)
        self.assertIsNone(final)
        self.assertTrue(
            any("shot markers" in p or "does not start with [Shot 1]" in p for p in problems),
            f"Expected shot marker error, got: {problems}"
        )

    def test_control_prompt_shorter_than_min_words_is_rejected(self):
        """GREEN Control: Answer with fewer than 40 words is correctly rejected."""
        short_answer = (
            "description: [Shot 1] The camera pushes in on Alice.\n"
            "overall_soundscape: Forest sounds.\n"
            "non_diegetic_music: Strings."
        )
        final, problems = part_prompt.check(SAMPLE_COMPILED, short_answer)
        self.assertIsNone(final)
        self.assertTrue(any("shorter than" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
