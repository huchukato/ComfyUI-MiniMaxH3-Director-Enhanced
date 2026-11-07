"""BUG-032: media_labels und prompt_labels duerfen bei fehlendem oder verwaistem Video-ctx_id
nicht mit AttributeError ('NoneType' object has no attribute 'options') abstuerzen.

In ng/core/media_labels.py:14:
    if context.item(ref.ctx_id).options.video_audio == "reference":
stuerzt ab, wenn context.item(ref.ctx_id) None zurueckgibt (z. B. wenn eine Video-Referenz
aus einem Timeline-Segment stammt, dessen ID nicht mehr in context.items existiert, oder
bei leerem ctx_id).

Kein Fix, nur rote Regressionstests.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import module  # noqa: E402

context_mod = module("ng.core.context")
media_labels_mod = module("ng.core.media_labels")
media_ref_mod = module("ng.core.media_ref")
legacy_bridge_mod = module("ng.core.legacy_bridge")


class MediaLabelsCrash(unittest.TestCase):
    def test_bug_032a_missing_video_context_id_in_media_labels_must_not_crash(self):
        """media_labels darf bei unbekanntem oder leerem Video-ctx_id nicht mit
        AttributeError: 'NoneType' object has no attribute 'options' abstuerzen.
        """
        ctx = context_mod.DirectorContext()
        ref = media_ref_mod.MediaRef("video", "missing_ctx_id", "clip.mp4")
        try:
            labels = media_labels_mod.media_labels(ctx, [ref])
            self.assertIsInstance(labels, tuple)
            self.assertEqual(labels[0][0], "<Video 1>")
        except AttributeError as err:
            self.fail("media_labels crashed with AttributeError: %s" % err)

    def test_bug_032b_empty_video_context_id_in_prompt_labels_must_not_crash(self):
        """prompt_labels darf bei Video-Referenzen ohne gueltiges context_id
        nicht ueber media_labels mit AttributeError abstuerzen.
        """
        ctx = context_mod.DirectorContext()
        mapping = legacy_bridge_mod.Mapping([], {})
        result = {
            "mode": "ref2va",
            "subject_of_slot": {},
            "ref_image_slots": [],
            "ref_video_segs": [],
            "ref_audio_segs": [],
            "lock_audio_segs": [],
        }
        ref = media_ref_mod.MediaRef("video", "", "motion.mp4")
        try:
            labels = media_labels_mod.prompt_labels(result, mapping, ctx, [ref])
            self.assertIsInstance(labels, tuple)
            self.assertTrue(any(label == "<Video 1>" for label, _ in labels))
        except AttributeError as err:
            self.fail("prompt_labels crashed with AttributeError: %s" % err)


if __name__ == "__main__":
    unittest.main()
