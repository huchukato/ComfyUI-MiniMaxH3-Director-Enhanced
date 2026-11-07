"""BUG-037: a reference picture beyond H3's nine-image cap is dropped without a word.

Reached by the user like this: connect ten NGContextImage cards with usage
"Reference" to the NGContextConnector, select one shot in the Studio and drop (or
click onto) each of the ten Content cards. The Studio assigns every one of them -
nothing warns while it happens and nothing caps it - and the plan then sends only
nine to the model.

minimax_plan.py trims the picture list at MAX_REF_IMAGES with a bare `break`
(lines 1288-1293) and records no `ref_warnings` entry, while the video cap right
below does record one ("H3 takes at most %d reference %s clips; '%s' was
dropped.", minimax_plan.py:1544). Its own comment above that loop states the rule:
"Both per-type caps used to trim in silence, which is the one thing a reference
limit is not allowed to do - every other one names what it dropped."

NG does surface those warnings (ng/core/compile.py:_issues reads result["ref_warnings"]),
so the dropped picture is invisible to the user: the Studio shows no note, the
reference budget reads "Images 9/9" and the tenth picture simply never reaches
the model.

The test calls the real plan_project() and compares the picture cap with the
video cap, so it fails until the picture cap names what it dropped too.
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


def picture(index, usage="reference"):
    return context_mod.ContextItem(id="ctx_p%d" % index, name="P%d" % index, media="image",
                                   source="p%d.png" % index, content=("character",), usage=(usage,))


def motion(index):
    return context_mod.ContextItem(id="ctx_v%d" % index, name="V%d" % index, media="video",
                                   source="v%d.mp4" % index, content=("motion",), usage=("motion",))


def shot_document(identities):
    return json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": [
        {"schema_version": 1, "id": "s1", "start": 0, "end": 10, "text": "",
         "media": [{"schema_version": 1, "context_id": identity, "role": "context"}
                   for identity in identities],
         "spoken": [], "locked_fields": [], "draft": None}],
        "audio": [], "audio_lanes": []})


def plan(items, identities):
    context = context_mod.DirectorContext(idea="", project_seconds=10.0,
                                          shots_text=shot_document(identities), items=tuple(items))
    return project_mod.plan_project(context, 0, chunks_mod.ContinuityPlan("video_audio"))


def warnings(project):
    return [issue.text for issue in project.issues]


class PictureCapReported(unittest.TestCase):
    def test_bug_037_dropping_a_reference_picture_must_be_reported(self):
        items = [picture(n) for n in range(10)]
        project = plan(items, ["ctx_p%d" % n for n in range(10)])
        compiled = project.compiled[0]

        sent = [ref.ctx_id for ref in compiled.refs if ref.kind == "picture"]
        dropped = ["ctx_p%d" % n for n in range(10) if "ctx_p%d" % n not in sent]
        self.assertEqual(len(sent), 9, "H3 takes nine reference pictures; one is dropped")
        self.assertTrue(dropped, "this case must actually drop a picture")

        text = " ".join(warnings(project))
        for identity in dropped:
            name = dict((item.id, item.name) for item in items)[identity]
            self.assertIn(
                name, text,
                "the dropped reference picture %s (%s) is not named in any plan warning: %r"
                % (identity, name, warnings(project)))

    def test_control_the_video_cap_reports_its_dropped_clip(self):
        # The green control for the same rule on the media type that already obeys it.
        items = [motion(n) for n in range(4)]
        project = plan(items, ["ctx_v%d" % n for n in range(4)])
        text = " ".join(warnings(project))
        self.assertIn("V3", text, "the video cap already names what it dropped")
        self.assertIn("was dropped", text)

    def test_control_nine_pictures_are_all_sent_and_need_no_warning(self):
        items = [picture(n) for n in range(9)]
        project = plan(items, ["ctx_p%d" % n for n in range(9)])
        sent = [ref.ctx_id for ref in project.compiled[0].refs if ref.kind == "picture"]
        self.assertEqual(len(sent), 9, "nine reference pictures fit and are all sent")
        self.assertNotIn("dropped", " ".join(warnings(project)),
                         "nothing was dropped, so nothing may claim something was")


if __name__ == "__main__":
    unittest.main()