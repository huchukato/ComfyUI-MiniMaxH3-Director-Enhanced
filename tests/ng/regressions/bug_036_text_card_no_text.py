"""BUG-036: `no_text` fires although a Text Context card supplies the chunk's text.

Reached by the user exactly like this: an NGContextText card connected to the
NGContextConnector, its note filled in, and the Director's own Prompt box and
every shot text left empty. That is the workflow shipped as
"NG Director Studio - text project.json" and the shape the Studio produces when a
user drags a Text card onto a shot instead of typing shot text.

The note reaches the model: it is written into the compiled prompt as
integrated_multimodal_description by the legacy compiler (ng/core/legacy_bridge.py),
because a text Context item is part of the scoped context for that chunk
(ng/core/shot_bindings.py selects it).

compile._issues() decides "there is no text" from `prompt_override`, `context.idea`
and the chunk's own shot text/spoken lines only. It never looks at the text Context
items the compiler just used, so the plan shows a warning that contradicts the very
prompt the drawer shows right above it.

The test calls the real plan_project() and asserts the two things a user sees:
the note is in the prompt, and no_text is not among the issues.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

context_mod = module("ng.core.context")
project_mod = module("ng.core.project")
chunks_mod = module("ng.core.chunks")

NOTE = "A mage sings quietly in a dark hall."


def shot_document(bound_ids):
    """The shots widget the Studio saves: one shot, no text, the named Contexts bound."""
    return json.dumps({
        "format": "h3-director-shots", "schema_version": 1,
        "shots": [{"schema_version": 1, "id": "shot_1", "start": 0, "end": 10, "text": "",
                   "media": [{"schema_version": 1, "context_id": identity, "role": "context"}
                             for identity in bound_ids],
                   "spoken": [], "locked_fields": [], "draft": None}],
        "audio": [], "audio_lanes": []})


def note_item(identity="ctx_note"):
    return context_mod.ContextItem(id=identity, name="Note", media="text", source=NOTE,
                                   content=("shot",), usage=("style",))


def plan(items, shots_text):
    context = context_mod.DirectorContext(idea="", shots_text=shots_text, project_seconds=10.0,
                                          items=tuple(items))
    return project_mod.plan_project(context, 0, chunks_mod.ContinuityPlan("video_audio"))


def codes(project):
    return [issue.code for issue in project.issues]


class TextCardNoTextWarning(unittest.TestCase):
    def test_bug_036_a_bound_text_card_still_gets_the_no_text_warning(self):
        project = plan([note_item()], shot_document(["ctx_note"]))
        compiled = project.compiled[0]

        # What the Studio's prompt drawer shows: the note is really in the prompt.
        self.assertIn(NOTE, compiled.prompt,
                      "the Text card's note must reach the compiled prompt")

        # What the Studio's issues panel shows right above it.
        self.assertNotIn(
            "no_text", codes(project),
            "no_text claims the prompt 'falls back to a bare placeholder', but the "
            "bound Text card's note is in it: %r" % compiled.prompt)

    def test_bug_036_an_unbound_text_card_still_gets_the_no_text_warning(self):
        # Same card, not bound to the shot: it keeps its whole-project scope and the
        # compiler still writes it into the prompt, so the warning is just as wrong.
        project = plan([note_item()], shot_document([]))
        self.assertIn(NOTE, project.compiled[0].prompt)
        self.assertNotIn("no_text", codes(project),
                         "an unbound Text card still supplies the chunk text")

    def test_control_no_text_is_still_reported_when_really_there_is_none(self):
        # The Normalfall the warning exists for: no note, no idea, no shot text.
        project = plan([], shot_document([]))
        self.assertNotIn(NOTE, project.compiled[0].prompt)
        self.assertIn("no_text", codes(project),
                      "with no text anywhere the warning is correct and must stay")

    def test_control_a_shot_text_still_counts_as_text(self):
        shots = json.dumps({
            "format": "h3-director-shots", "schema_version": 1,
            "shots": [{"schema_version": 1, "id": "shot_1", "start": 0, "end": 10,
                       "text": "A mage sings.", "media": [], "spoken": [],
                       "locked_fields": [], "draft": None}],
            "audio": [], "audio_lanes": []})
        self.assertNotIn("no_text", codes(plan([], shots)))


if __name__ == "__main__":
    unittest.main()