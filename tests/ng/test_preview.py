import json
import unittest

from _pack import module

build = module("ng.core.context_build")
preview = module("ng.core.preview")

ALICE = {"media": "image", "widgets": {"image": "alice.png [input]", "name": "Alice", "description": "a woman", "content": "character",
                                       "usage": "reference", "preserve": "high"}}
VOICE = {"media": "audio", "widgets": {"audio": "alice.wav", "name": "Alice voice", "content": "voice", "usage": "voice", "speaker": "Alice"}}


class Build(unittest.TestCase):
    def test_image_item(self):
        item = build.item_from_widgets("image", ALICE["widgets"])
        self.assertEqual((item.id, item.source, item.content, item.usage), ("image_alice", "alice.png", ("character",), ("reference",)))

    def test_file_stem_names_an_unnamed_item(self):
        item = build.item_from_widgets("image", {"image": "refs/old castle.png"})
        self.assertEqual((item.name, item.id, item.content, item.usage), ("old castle", "image_old_castle", (), ()))

    def test_text_item_and_length(self):
        text = build.item_from_widgets("text", {"text": "Keep the camera slow.", "usage": "style"})
        self.assertEqual((text.media, text.source, text.name), ("text", "Keep the camera slow.", "Keep the camera slow."))
        self.assertEqual(build.item_from_widgets("audio", {"audio": "a.wav"}, length_s=7.5).length_s, 7.5)


class Preview(unittest.TestCase):
    def test_idea_only(self):
        out = preview.plan_preview({"director": {"idea": "A dog runs.", "project_seconds": 30}})
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["chunks"]), 3)
        self.assertEqual(out["mode"], "t2va")
        self.assertIn("A dog runs.", out["chunks"][0]["prompt"])
        json.dumps(out)                                   # the whole answer must be plain JSON

    def test_with_contexts_and_a_probe(self):
        seen = []
        out = preview.plan_preview({"director": {"shots": "0-8: @Alice says: hi", "project_seconds": 8}, "contexts": [ALICE, VOICE]},
                                   probe=lambda source: seen.append(source) or 6.0)
        self.assertEqual(seen, ["alice.wav"])
        self.assertEqual(out["mode"], "ref2va")
        self.assertEqual([r["kind"] for r in out["chunks"][0]["refs"]], ["picture", "audio"])
        self.assertIn("(S1)", out["chunks"][0]["prompt"])

    def test_corrections_come_back_as_issues(self):
        out = preview.plan_preview({"director": {"idea": "x", "project_seconds": 8, "width": 500, "height": 700}})
        self.assertIn("canvas_snapped", [i["code"] for i in out["issues"]])

    def test_inspector_context_contains_the_compilers_normalized_values(self):
        context = module("ng.core.context")
        project = module("ng.core.project")
        out = preview.plan_preview({"director": {"idea": "x", "project_seconds": 8, "width": 500, "height": 700}, "contexts": []})
        restored = context.DirectorContext.from_dict(out["director_context"])
        rebuilt = project.plan_project(restored, 10, preview.ContinuityPlan())
        self.assertEqual(rebuilt.context.to_dict(), out["director_context"])
        self.assertEqual(rebuilt.compiled[0].prompt, out["chunks"][0]["prompt"])

    def test_bad_input_is_an_error_not_a_crash(self):
        for director in ({"project_seconds": "abc"}, {"mode": "sideways"}, {"project_seconds": 0}, {"continuity": "magic"}):
            out = preview.plan_preview({"director": director})
            self.assertFalse(out["ok"], director)
            self.assertTrue(out["error"])
        self.assertFalse(preview.plan_preview({"contexts": [{"media": "gif", "widgets": {}}]})["ok"])

    def test_malformed_requests_and_nonfinite_numbers_are_errors(self):
        for payload in (None, [], {"director": []}, {"director": "bad"}, {"contexts": [None]},
                        {"contexts": [{"media": "image", "widgets": []}]}, {"contexts": "bad"},
                        {"director": {"project_seconds": float("nan")}}, {"director": {"width": float("inf")}}):
            with self.subTest(payload=payload):
                self.assertFalse(preview.plan_preview(payload)["ok"])


if __name__ == "__main__":
    unittest.main()
