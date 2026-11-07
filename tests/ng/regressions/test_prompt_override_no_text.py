"""BUG-025: prompt_override without idea/shots triggers false 'no_text' warning.

When prompt_override is provided, the compiled chunk prompt uses the override.
However, compile._issues() only checks idea and shots, emitting:
  Issue("no_text", "There is no text for this chunk; the prompt falls back to a bare placeholder.")
even though the prompt never falls back to a placeholder.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

context_mod = module("ng.core.context")
project_mod = module("ng.core.project")
chunks_mod = module("ng.core.chunks")


class PromptOverrideNoTextWarning(unittest.TestCase):
    def test_bug_025_prompt_override_without_idea_or_shots_must_not_warn_no_text(self):
        context = context_mod.DirectorContext(
            idea="",
            shots_text="",
            prompt_override="A hero stands on a cliff at sunset.",
            project_seconds=5.0,
        )
        plan = project_mod.plan_project(context, 0, chunks_mod.ContinuityPlan("none"))
        compiled = plan.compiled[0]

        # The prompt is indeed the override
        self.assertEqual(compiled.prompt, "A hero stands on a cliff at sunset.")

        # It must NOT emit the no_text warning
        no_text_issues = [i for i in compiled.issues if i.code == "no_text"]
        self.assertEqual(
            no_text_issues,
            [],
            "no_text warning emitted even though prompt_override provides text and is used",
        )


if __name__ == "__main__":
    unittest.main()
