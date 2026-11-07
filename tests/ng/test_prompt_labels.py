"""The Inspector must use the planner's labels, including paired video soundtracks."""
import unittest
import json
from _pack import module

preview = module("ng.core.preview")
compile_ = module("ng.core.compile")


def card(media, identity, usage, **extra):
    return {"media": media, "widgets": {"context_id": identity, "name": identity, media: "same.file", "usage": usage, **extra}}


class PromptLabels(unittest.TestCase):
    def plan(self, cards):
        return preview.plan_preview({"director": {"idea": "Move.", "project_seconds": 12, "chunk_seconds": 5}, "contexts": cards},
                                    probe=lambda _: 2)

    def test_soundtracks_belong_to_their_video_cards_in_all_chunks(self):
        cards = [card("image", "figure", "reference"), card("video", "silent", "motion"),
                 card("video", "move", "motion", context_options=json.dumps({"schema_version": 1, "video_audio": "reference"})),
                 card("audio", "voice", "voice", speaker="figure")]
        result = self.plan(cards)
        self.assertTrue(result["ok"], result)
        for chunk in result["chunks"]:
            labels = chunk["prompt_labels"]
            self.assertEqual(labels, {"<Picture 1>": "figure", "<Subject 1>": "figure", "<Video 1>": "silent",
                                      "<Video 2>": "move", "<Audio 1>": "move", "<Audio 2>": "voice"})
            self.assertIn("<Audio 1> is the soundtrack of <Video 2>", chunk["prompt"])
            self.assertIn("<Audio 2> is the voice-timbre reference for <Subject 1>", chunk["prompt"])

    def test_dropped_media_and_frame_anchors_do_not_claim_subject_labels(self):
        cards = [card("image", "first", "first_frame"), card("image", "figure", "reference")]
        cards += [card("audio", "voice%d" % n, "sound_reference") for n in range(4)]
        result = self.plan(cards)
        for chunk in result["chunks"]:
            labels = chunk["prompt_labels"]
            self.assertEqual(labels["<Picture 1>"], "figure")
            if chunk["index"] == 0:  # First frame appears only in the first chunk, also as a Ref2VA picture.
                self.assertEqual(labels["<Picture 2>"], "first")
            else:
                self.assertNotIn("first", labels.values())
            self.assertNotIn("<Subject 2>", labels)
            self.assertNotIn("voice3", labels.values())
            self.assertNotIn("<Audio 4>", labels)

    def test_frame_only_mode_has_native_picture_labels_without_subject_labels(self):
        result = self.plan([card("image", "first", "first_frame")])
        self.assertTrue(result["ok"], result)
        for chunk in result["chunks"]:
            self.assertEqual(chunk["prompt_labels"], {"<Picture 1>": "first"} if chunk["index"] == 0 else {})

    def test_optional_display_labels_roundtrip_and_load_old_chunks(self):
        old = compile_.CompiledChunk(0, "t2va", "Move.").to_dict()
        old.pop("prompt_labels", None)
        self.assertEqual(compile_.CompiledChunk.from_dict(old).prompt_labels, ())
        current = {**old, "prompt_labels": {"<Subject 1>": "figure"}}
        restored = compile_.CompiledChunk.from_dict(current)
        self.assertEqual(restored.to_dict(), current)
        for invalid in ([], {"<Subject 1>": 3}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                compile_.CompiledChunk.from_dict({**old, "prompt_labels": invalid})

    def test_subject_numbers_come_from_the_planner_instead_of_picture_numbers(self):
        labels_module = module("ng.core.media_labels")
        ctx = module("ng.core.context")
        bridge = module("ng.core.legacy_bridge")
        # One subject owns two pictures. A timeline-defined subject therefore owns Picture 3, not Picture 2.
        refs = [compile_.MediaRef("picture", "figure", "a.png"), compile_.MediaRef("picture", "figure", "b.png"),
                compile_.MediaRef("picture", "outfit", "a.png")]
        result = {"subject_of_slot": {1: 1}, "ref_image_slots": [{"source": "char"}, {"source": "char"},
                  {"source": "timeline", "subject": 2, "event": {"seg": {"imageFile": "a.png", "ng_item": "outfit"}}}]}
        labels = dict(labels_module.prompt_labels(result, bridge.Mapping(["figure"], {"a.png": "figure"}),
                                                  ctx.DirectorContext(), refs))
        self.assertEqual(labels, {"<Picture 1>": "figure", "<Picture 2>": "figure", "<Picture 3>": "outfit",
                                 "<Subject 1>": "figure", "<Subject 2>": "outfit"})
