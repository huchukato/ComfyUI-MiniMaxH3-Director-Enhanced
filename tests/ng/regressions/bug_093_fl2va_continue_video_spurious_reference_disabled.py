"""Regression test for BUG-093:
Video card with usage ('continue',) in fl2va mode falsely triggers Issue('reference_disabled')
in ng/core/context_checks.py:31-35 despite continue video being an active frame guide
compiled into compiled.refs and executed via MiniMaxH3AddGuide.

Context:
In ng/core/context_checks.py:31-35:
    reference = (item.media == "image" and "reference" in item.effective_usage) or item.media == "video" or (
        item.media == "audio" and bool(set(item.effective_usage) & {"voice", "copy", "music_style", "rhythm", "sound_reference"}))
    if context.mode == "fl2va" and reference:
        issues.append(Issue("reference_disabled", "Is omitted by explicit fl2va mode; choose auto or ref2va to use it.", item.name))

USAGES_BY_MEDIA['video'] has 4 roles: ("motion", "camera", "continue", "structure").
- 'motion', 'camera', 'structure' are multi-view reference video roles that require Ref2VA
  (compiled via _motion_segments in legacy_bridge.py:199-214).
- 'continue' is a frame guide role: its end frame is extracted and added to the chunk
  as a starting frame guide via MiniMaxH3AddGuide (scene_guides.py:18).

In FL2VA mode, frame guides are the primary conditioning mechanism (using MiniMaxH3ImageToVideo
and MiniMaxH3AddGuide). The continue video is NOT omitted:
1. plan_guides compiles it as MediaRef("continue_video", ...) in compiled.refs.
2. chunk_builder.py runs _frame_conditioning and then applies continue_video via scene_guides.apply_guides.
3. In legacy_bridge.py:50, has_references(context) correctly checks:
   if (item.media == "video" and set(usage) & {"motion", "camera", "structure"}): return True
   and does NOT treat 'continue' as a reference.

However, context_checks.py:31 checks unconditionally `or item.media == "video"` without
checking for reference roles, treating 'continue' as an omitted reference. It falsely warns:
"Is omitted by explicit fl2va mode; choose auto or ref2va to use it."
This misleads the user to switch to ref2va, which disables ImageToVideo frame conditioning.
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

# Add test directory so _pack helper is accessible
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_NG_TESTS_DIR = os.path.dirname(_CURRENT_DIR)
if _NG_TESTS_DIR not in sys.path:
    sys.path.insert(0, _NG_TESTS_DIR)

import _pack
_pack.stub_prompt_server()

ctx = _pack.module("ng.core.context")
checks = _pack.module("ng.core.context_checks")
project = _pack.module("ng.core.project")
chunks = _pack.module("ng.core.chunks")
scene_guides = _pack.module("ng.adapters.scene_guides")
compile_mod = _pack.module("ng.core.compile")


class TestBug093Fl2vaContinueVideoSpuriousReferenceDisabled(unittest.TestCase):

    # =========================================================================
    # GREEN CONTROL TESTS: Legitimate references in FL2VA mode ARE disabled
    # =========================================================================

    def test_control_1_motion_video_in_fl2va_emits_reference_disabled(self):
        """Control 1: Video with usage=('motion',) is a reference and cannot be used in fl2va;
        must emit reference_disabled."""
        v = ctx.ContextItem("v_motion", "MotionClip", "video", "motion.mp4", usage=("motion",))
        c = ctx.DirectorContext(items=(v,), mode="fl2va")
        issues = checks.check_context(c)
        codes = [i.code for i in issues]
        self.assertIn("reference_disabled", codes,
                      "Motion video is a reference and must emit reference_disabled in fl2va mode")
        issue = [i for i in issues if i.code == "reference_disabled"][0]
        self.assertEqual(issue.ref, "MotionClip")

    def test_control_2_camera_and_structure_video_in_fl2va_emit_reference_disabled(self):
        """Control 2: Video with usage=('camera',) or ('structure',) are references and
        must emit reference_disabled in fl2va mode."""
        v_cam = ctx.ContextItem("v_cam", "CamClip", "video", "cam.mp4", usage=("camera",))
        v_struct = ctx.ContextItem("v_struct", "StructClip", "video", "struct.mp4", usage=("structure",))
        c = ctx.DirectorContext(items=(v_cam, v_struct), mode="fl2va")
        issues = checks.check_context(c)
        refs_with_issue = [i.ref for i in issues if i.code == "reference_disabled"]
        self.assertIn("CamClip", refs_with_issue)
        self.assertIn("StructClip", refs_with_issue)

    def test_control_3_reference_image_and_voice_audio_in_fl2va_emit_reference_disabled(self):
        """Control 3: audio with usage=('voice',) is a reference and must emit reference_disabled in fl2va mode. An image with
        usage=('reference',) is used in fl2va since 2026-10-12 (ng.core.fl2va_refs) and must not."""
        img = ctx.ContextItem("img_ref", "Alice", "image", "alice.png", usage=("reference",))
        aud = ctx.ContextItem("aud_voice", "AliceVoice", "audio", "voice.wav", usage=("voice",))
        c = ctx.DirectorContext(items=(img, aud), mode="fl2va")
        issues = checks.check_context(c)
        refs_with_issue = [i.ref for i in issues if i.code == "reference_disabled"]
        self.assertNotIn("Alice", refs_with_issue)
        self.assertIn("AliceVoice", refs_with_issue)

    def test_control_4_continue_video_in_ref2va_does_not_emit_reference_disabled(self):
        """Control 4: In ref2va mode, reference_disabled is not emitted."""
        v = ctx.ContextItem("v_cont", "Prequel", "video", "prequel.mp4", usage=("continue",))
        c = ctx.DirectorContext(items=(v,), mode="ref2va")
        issues = checks.check_context(c)
        codes = [i.code for i in issues]
        self.assertNotIn("reference_disabled", codes)

    # =========================================================================
    # RED DEFECT TESTS: continue video in FL2VA mode is a FRAME GUIDE, NOT an
    # omitted reference. It must not trigger reference_disabled.
    # =========================================================================

    def test_defect_1_continue_video_in_fl2va_must_not_emit_reference_disabled_in_check_context(self):
        """Defect 1: check_context must not flag continue video as an omitted reference in fl2va."""
        v = ctx.ContextItem("v_cont", "Prequel", "video", "prequel.mp4", usage=("continue",))
        c = ctx.DirectorContext(items=(v,), mode="fl2va")
        issues = checks.check_context(c)
        disabled_issues = [i for i in issues if i.code == "reference_disabled"]
        self.assertEqual(len(disabled_issues), 0,
                         "BUG-093: Video card with usage=('continue',) is a frame guide, not a reference; "
                         "it must not emit Issue('reference_disabled') in fl2va mode")

    def test_defect_2_unstructured_plan_project_with_continue_video_in_fl2va_must_not_emit_reference_disabled(self):
        """Defect 2: plan_project on an unstructured project with continue video and first_frame
        image in explicit fl2va mode compiles continue_video but must not emit reference_disabled."""
        v = ctx.ContextItem("v_cont", "Prequel", "video", "prequel.mp4", usage=("continue",))
        img = ctx.ContextItem("i_start", "Opening", "image", "open.png", usage=("first_frame",))
        c = ctx.DirectorContext(idea="Continuing previous scene", project_seconds=5.0,
                                items=(v, img), mode="fl2va")
        res = project.plan_project(c, 5.0, chunks.ContinuityPlan("none"))

        # The continue video IS compiled into the chunk guides
        compiled_kinds = [r.kind for r in res.compiled[0].refs]
        self.assertIn("continue_video", compiled_kinds,
                      "continue_video must be planned in compiled.refs")

        # But project.issues must NOT claim the card is disabled/omitted
        disabled = [i for i in res.issues if i.code == "reference_disabled" and i.ref == "Prequel"]
        self.assertEqual(len(disabled), 0,
                         "BUG-093: project.issues must not contain spurious reference_disabled for active continue video")

    def test_defect_3_structured_shot_bound_continue_video_in_fl2va_must_not_emit_reference_disabled(self):
        """Defect 3: In a project with structured shots where Shot 1 binds the video card as
        role='continue' in fl2va mode, the card must not be flagged as reference_disabled in
        compiled.issues or project.issues."""
        v = ctx.ContextItem("v_cont", "Prequel", "video", "prequel.mp4", usage=("continue",))
        shots_text = json.dumps({
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [
                {
                    "id": "s1",
                    "start": 0.0,
                    "end": 5.0,
                    "text": "The camera pushes forward continuing from the prequel ending.",
                    "media": [{"context_id": "v_cont", "role": "continue", "schema_version": 1}]
                }
            ]
        })
        c = ctx.DirectorContext(idea="Prequel continuation", project_seconds=5.0,
                                shots_text=shots_text, items=(v,), mode="fl2va")
        res = project.plan_project(c, 5.0, chunks.ContinuityPlan("none"))

        # Verify compiled.refs has continue_video
        compiled_refs = [(r.kind, r.ctx_id) for r in res.compiled[0].refs]
        self.assertIn(("continue_video", "v_cont"), compiled_refs)

        # Neither compiled.issues nor project.issues may have reference_disabled
        compiled_disabled = [i for i in res.compiled[0].issues if i.code == "reference_disabled" and i.ref == "Prequel"]
        project_disabled = [i for i in res.issues if i.code == "reference_disabled" and i.ref == "Prequel"]
        self.assertEqual(len(compiled_disabled), 0,
                         "BUG-093: compiled[0].issues must not contain reference_disabled for shot-bound continue video")
        self.assertEqual(len(project_disabled), 0,
                         "BUG-093: res.issues must not contain reference_disabled for shot-bound continue video")

    def test_defect_4_continue_video_is_applied_to_add_guide_proving_it_is_not_omitted(self):
        """Defect 4: In fl2va mode, continue_video in compiled.refs is actively passed to
        MiniMaxH3AddGuide.execute by scene_guides.apply_guides, proving that the issue text
        'Is omitted by explicit fl2va mode' is entirely false and contradicts pipeline execution."""
        import torch
        import types

        # Create a job with compiled continue_video ref
        ref = compile_mod.MediaRef("continue_video", "v_cont", "prequel.mp4", start_f=0, length_f=24, trim_start_f=0)
        # mode and refs as a compiled chunk has them (the first mock lacked both and failed before the call)
        # since 6baa992 the guide loads the card's video and sound through continuation_media, with the card from the project
        card = ctx.ContextItem("v_cont", "Prequel", "video", "prequel.mp4", usage=("continue",))
        job = types.SimpleNamespace(compiled=types.SimpleNamespace(mode="fl2va", refs=(ref,),
                                                                   of_kind=lambda k: (ref,) if k == "continue_video" else ()),
                                    project=types.SimpleNamespace(context=ctx.DirectorContext(items=(card,), mode="fl2va")))

        # Mock MiniMax core and media loader
        mm = MagicMock()
        mm.MiniMaxH3AddGuide.execute.return_value = ("guided_positive",)

        orig_load = scene_guides.continuation_media.load
        try:
            scene_guides.continuation_media.load = MagicMock(return_value=(torch.zeros(10, 3, 64, 64), None))
            positive = "base_positive"
            latent = {"samples": torch.zeros(1, 4, 16, 16)}
            vae = MagicMock()

            out = scene_guides.apply_guides(mm, job, positive, latent, vae)
            self.assertEqual(out, "guided_positive")
            self.assertTrue(mm.MiniMaxH3AddGuide.execute.called,
                            "MiniMaxH3AddGuide.execute must be called for continue_video")
        finally:
            scene_guides.continuation_media.load = orig_load

        # Now verify that context_checks falsely claims this same card is omitted:
        v = ctx.ContextItem("v_cont", "Prequel", "video", "prequel.mp4", usage=("continue",))
        c = ctx.DirectorContext(items=(v,), mode="fl2va")
        issues = checks.check_context(c)
        # This assert WILL FAIL on current code: it expects 0 reference_disabled issues, but gets 1
        disabled_texts = [i.text for i in issues if i.code == "reference_disabled" and i.ref == "Prequel"]
        self.assertEqual(len(disabled_texts), 0,
                         "BUG-093: context_checks falsely emits '%s' for a card that is actively conditioned via MiniMaxH3AddGuide"
                         % (disabled_texts[0] if disabled_texts else ""))


if __name__ == "__main__":
    unittest.main()
