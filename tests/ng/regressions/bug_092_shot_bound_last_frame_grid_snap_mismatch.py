"""BUG-092: Shot-bound last_frame image cards in guide_timing._bound_ref calculate frame position
from unadjusted shot.end_f instead of delivered grid frames, causing last frame cards on the final
shot to be silently dropped (when grid snaps shorter) or downgraded to intermediate keyframes (when
grid snaps longer), omitting last_frame from sampler conditioning and prompt alignment across almost
all project lengths.

Technical Root Cause:
In ng/core/guide_timing.py:43-61:
    if item.media == "image" and role in ("first_frame", "last_frame"):
        frame = shot.start_f if role == "first_frame" else shot.end_f - 1
    ...
    if not chunk.story_start_f <= frame < chunk.story_end_f:
        return None
    local = frame - chunk.story_start_f + chunk.head_frames
    ...
    kind = "keyframe"
    if mode != "ref2va" and ((role == "first_frame" and local == 0) or
                            (role == "last_frame" and local == chunk.sampled_frames - 1)):
        kind = role
    return MediaRef(kind, item.id, item.source, local, 1)

1. `shots` are parsed by `shots.parse_shots(context.shots_text, seconds_to_frames(context.project_seconds))`.
   The final shot's `end_f` is strictly set to `round(context.project_seconds * 24)`.
2. MiniMax H3 requires video chunks to reside on its trained `17k + 5` frame grid (`chunks.plan_lengths`).
   Consequently, the actual delivered frames `chunk.delivered_frames` (`chunk.sampled_frames`) differ from
   `seconds_to_frames(context.project_seconds)` in 93% of project lengths (e.g. 5s -> 124 frames vs 120;
   6s -> 141 frames vs 144; 7s -> 175 frames vs 168; 10s -> 243 frames vs 240; 12s -> 294 frames vs 288;
   15s -> 175 frames vs 360).
3. When the grid snaps shorter than requested duration (e.g. 6.0s: 144 requested -> 141 delivered):
   `frame = shot.end_f - 1 = 143`.
   `chunk.story_end_f` is 141.
   Line 52: `frame < chunk.story_end_f` evaluates to `143 < 141`, which is False!
   `_bound_ref` returns `None`.
   The user's Last Frame card is completely and silently dropped:
   - `plan_guides` returns empty refs.
   - `compiled.refs` omits the card completely.
   - Zero issues or warnings are emitted to alert the user.
4. When the grid snaps longer than requested duration (e.g. 10.0s: 240 requested -> 243 delivered):
   `frame = shot.end_f - 1 = 239`.
   `local = 239`.
   `chunk.sampled_frames - 1` is 242.
   Line 59: `local == chunk.sampled_frames - 1` evaluates to `239 == 242`, which is False!
   `kind` is forced to `"keyframe"` instead of `"last_frame"`, and positioned at frame 239 instead of 242.
5. Downstream impacts:
   - In `chunk_builder._frame_conditioning`: `compiled.of_kind("last_frame")` returns empty tuple `()`.
     `MiniMaxH3ImageToVideo` receives `last_frame=None`! The model never conditions on the last frame image.
   - In `minimax_plan.plan_timeline`: `alignment_instruction` detects no `ROLE_LAST` event, so the prompt
     completely omits the last frame declaration (`Picture 2 aligns with...` or `<Picture 1> aligns with...`).
   - In `media_labels.prompt_labels`: No Picture token is assigned to the last frame card.
     Any shot text mentioning `@Ending` cannot resolve, is replaced with generic `"the guide image"`, and emits
     a spurious `Issue("guide_mention_prose")`.
   - In `ref2va`: `_anchor_segments` matches only `ref.kind == "last_frame"`, so no anchor segment is created,
     `<Picture N> is the last frame...` is omitted, and summary drops to `[reference generation]`.

Contrast with Expected Behavior & Specification:
- `docs/NG.md:237`: "First / last frame open or end the video, or the shot the picture is dropped on in the Studio."
- Unbound cards in `_global_guides` properly use `chunk.sampled_frames - 1` and retain `last_frame`.
- Shot-bound `first_frame` cards on Shot 0 properly have `local == 0` and retain `first_frame`.
- When a shot ends at the end of the project, its last frame card must end the video at `chunk.sampled_frames - 1`
  with `kind="last_frame"`, rather than being dropped or downgraded to an intermediate keyframe.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from _pack import module  # noqa: E402

compile_mod = module("ng.core.compile")
context_mod = module("ng.core.context")
chunks_mod = module("ng.core.chunks")
doc_mod = module("ng.core.shot_document")
guides_mod = module("ng.core.guide_timing")
project_mod = module("ng.core.project")


def make_shots_json(shots_list):
    return json.dumps({
        "format": "h3-director-shots",
        "schema_version": 1,
        "shots": shots_list,
    })


class TestBug092ShotBoundLastFrameGridSnapMismatch(unittest.TestCase):
    """Test suite for BUG-092: Shot-bound last_frame grid snap mismatch."""

    def test_control_1_unbound_last_frame_card_snaps_to_last_delivered_frame(self):
        """Control: When a last_frame card is UNBOUND (not assigned to a shot),

        _global_guides automatically positions it at chunk.sampled_frames - 1
        and assigns kind='last_frame', regardless of grid snapping.
        """
        card_lf = context_mod.ContextItem("img_lf", "Sunset", "image", "sunset.png", usage=("last_frame",))
        ctx = context_mod.DirectorContext(items=(card_lf,), project_seconds=6.0, mode="fl2va")
        plan = project_mod.plan_project(ctx, 6.0, chunks_mod.ContinuityPlan("none"))
        chunk0 = plan.plan.chunks[0]

        # 6.0s snaps to 141 delivered/sampled frames
        self.assertEqual(chunk0.delivered_frames, 141)
        self.assertEqual(chunk0.sampled_frames, 141)

        compiled = plan.compiled[0]
        lf_refs = compiled.of_kind("last_frame")
        self.assertEqual(len(lf_refs), 1, "Unbound last_frame card must be compiled as 'last_frame'")
        self.assertEqual(lf_refs[0].ctx_id, "img_lf")
        self.assertEqual(lf_refs[0].start_f, 140, "Unbound last_frame must sit at sampled_frames - 1 (140)")
        self.assertIn("<Picture 1>", compiled.prompt, "Unbound last_frame must compile <Picture 1> in prompt")

    def test_control_2_shot_bound_first_frame_at_zero_snaps_correctly(self):
        """Control: A shot-bound first_frame card on Shot 0 always starts at 0s (frame 0),

        which remains 0 regardless of grid snapping, so kind='first_frame' is preserved.
        """
        card_ff = context_mod.ContextItem("img_ff", "Opening", "image", "opening.png", usage=("first_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 6.0, "text": "Opening scene.",
             "media": [{"schema_version": 1, "context_id": "img_ff", "role": "first_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_ff,), shots_text=shots_doc, project_seconds=6.0, mode="fl2va")
        plan = project_mod.plan_project(ctx, 6.0, chunks_mod.ContinuityPlan("none"))
        compiled = plan.compiled[0]

        ff_refs = compiled.of_kind("first_frame")
        self.assertEqual(len(ff_refs), 1, "Shot-bound first_frame at local 0 must be compiled as 'first_frame'")
        self.assertEqual(ff_refs[0].start_f, 0)
        self.assertIn("<Picture 1> (from [Shot 1]) is fully referenced", compiled.prompt)

    def test_control_3_intermediate_shot_bound_last_frame_correctly_downgrades_to_keyframe(self):
        """Control: When a last_frame card is bound to an INTERMEDIATE shot (e.g. Shot 1 ending

        at 2.5s in a 5.0s video), it correctly functions as an intermediate keyframe guide
        at the end of Shot 1 rather than ending the target video.
        """
        card_mid = context_mod.ContextItem("img_mid", "MidFrame", "image", "mid.png", usage=("last_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 2.5, "text": "First scene.",
             "media": [{"schema_version": 1, "context_id": "img_mid", "role": "last_frame"}]},
            {"id": "s2", "start": 2.5, "end": 5.0, "text": "Second scene."},
        ])
        ctx = context_mod.DirectorContext(items=(card_mid,), shots_text=shots_doc, project_seconds=5.0, mode="fl2va")
        plan = project_mod.plan_project(ctx, 5.0, chunks_mod.ContinuityPlan("none"))
        compiled = plan.compiled[0]

        # Intermediate last_frame should be a keyframe guide at frame 59 (2.5s - 1 frame)
        kf_refs = compiled.of_kind("keyframe")
        self.assertTrue(any(r.ctx_id == "img_mid" and r.start_f == 59 for r in kf_refs),
                        "Intermediate shot-bound last_frame should become keyframe guide at shot boundary")
        self.assertEqual(len(compiled.of_kind("last_frame")), 0,
                         "Intermediate shot-bound last_frame must not be compiled as target video last_frame")

    def test_defect_1_grid_snapped_shorter_must_not_drop_shot_bound_last_frame(self):
        """Defect 1: In a 6.0s project (144 frames requested), H3's grid delivers 141 frames.

        When the user drops a last_frame card onto the final shot (ending at 6.0s = 144 frames),
        shot.end_f - 1 = 143 exceeds chunk.story_end_f = 141.
        _bound_ref returns None, causing the card to be COMPLETELY DROPPED from compiled.refs!

        Expected: The shot-bound last_frame card on the final shot must not be dropped;
        it must be anchored at the final delivered frame of the chunk (frame 140) with kind='last_frame'.
        """
        card_lf = context_mod.ContextItem("img_lf", "Sunset", "image", "sunset.png", usage=("last_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 3.0, "text": "Opening scene."},
            {"id": "s2", "start": 3.0, "end": 6.0, "text": "Ending scene at sunset.",
             "media": [{"schema_version": 1, "context_id": "img_lf", "role": "last_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_lf,), shots_text=shots_doc, project_seconds=6.0, mode="fl2va")
        plan = project_mod.plan_project(ctx, 6.0, chunks_mod.ContinuityPlan("none"))
        compiled = plan.compiled[0]

        # Under the defect: compiled.refs is empty []!
        # With the fix: img_lf must be present with kind='last_frame' at chunk.sampled_frames - 1 (140)
        lf_refs = compiled.of_kind("last_frame")
        self.assertTrue(len(compiled.refs) > 0,
                        "BUG-092: Shot-bound last_frame card on final shot must not be silently dropped when grid snaps shorter")
        self.assertEqual(len(lf_refs), 1,
                         "BUG-092: Shot-bound last_frame card on final shot must have kind='last_frame'")
        self.assertEqual(lf_refs[0].ctx_id, "img_lf")
        self.assertEqual(lf_refs[0].start_f, 140,
                         "BUG-092: Shot-bound last_frame must sit at final delivered frame (140)")

    def test_defect_2_grid_snapped_longer_must_not_downgrade_final_shot_last_frame_to_keyframe(self):
        """Defect 2: In a 10.0s project (240 frames requested), H3's grid delivers 243 frames.

        When the user drops a last_frame card onto the final shot (ending at 10.0s = 240 frames),
        shot.end_f - 1 = 239.
        local == chunk.sampled_frames - 1 evaluates to 239 == 242 (False).
        _bound_ref forces kind='keyframe' at frame 239 instead of kind='last_frame' at frame 242!

        Expected: The shot-bound last_frame card on the final shot must have kind='last_frame'
        and sit at the true end of the video (frame 242), rather than being downgraded to keyframe at frame 239.
        """
        card_lf = context_mod.ContextItem("img_lf", "Sunset", "image", "sunset.png", usage=("last_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 5.0, "text": "Opening scene."},
            {"id": "s2", "start": 5.0, "end": 10.0, "text": "Final scene at sunset.",
             "media": [{"schema_version": 1, "context_id": "img_lf", "role": "last_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_lf,), shots_text=shots_doc, project_seconds=10.0, mode="fl2va")
        plan = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan("none"))
        compiled = plan.compiled[0]

        # Under the defect: compiled.refs is [('keyframe', 'img_lf', 239)] and of_kind('last_frame') is ()
        # With the fix: of_kind('last_frame') must contain img_lf at frame 242
        lf_refs = compiled.of_kind("last_frame")
        self.assertEqual(len(lf_refs), 1,
                         "BUG-092: Final shot-bound last_frame must be compiled as kind='last_frame', not downgraded to keyframe")
        self.assertEqual(lf_refs[0].ctx_id, "img_lf")
        self.assertEqual(lf_refs[0].start_f, 242,
                         "BUG-092: Final shot-bound last_frame must sit at chunk.sampled_frames - 1 (242)")

    def test_defect_3_fl2va_final_shot_bound_last_frame_must_provide_last_frame_conditioning_and_dual_prompt_alignment(self):
        """Defect 3: In a 5.0s project (120 requested, 124 delivered) with both first_frame on Shot 1

        and last_frame on Shot 2 (the final shot), the grid mismatch (119 != 123) prevents
        last_frame from being compiled.
        As a result:
        - compiled.of_kind('last_frame') is empty, leaving MiniMaxH3ImageToVideo with last_frame=None!
        - The compiled prompt generates only single-image alignment "<Picture 1> is fully referenced",
          completely omitting the dual alignment instruction with Picture 2!

        Expected:
        - compiled.of_kind('last_frame') must have the last frame card.
        - prompt must declare the dual alignment instruction referencing Picture 2.
        """
        card_ff = context_mod.ContextItem("img_ff", "Opening", "image", "opening.png", usage=("first_frame",))
        card_lf = context_mod.ContextItem("img_lf", "Ending", "image", "ending.png", usage=("last_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 2.5, "text": "Opening scene.",
             "media": [{"schema_version": 1, "context_id": "img_ff", "role": "first_frame"}]},
            {"id": "s2", "start": 2.5, "end": 5.0, "text": "Ending scene.",
             "media": [{"schema_version": 1, "context_id": "img_lf", "role": "last_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_ff, card_lf), shots_text=shots_doc, project_seconds=5.0, mode="fl2va")
        plan = project_mod.plan_project(ctx, 5.0, chunks_mod.ContinuityPlan("none"))
        compiled = plan.compiled[0]

        # Under the defect: compiled.of_kind('last_frame') is empty ()
        # and prompt is: "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
        lf_refs = compiled.of_kind("last_frame")
        self.assertEqual(len(lf_refs), 1,
                         "BUG-092: compiled.of_kind('last_frame') must contain the last frame card for ImageToVideo sampler input")
        self.assertIn("Picture 2", compiled.prompt,
                      "BUG-092: Compiled prompt must include Picture 2 in the dual alignment instruction")
        self.assertIn("How the reference pictures align with the target video", compiled.prompt,
                      "BUG-092: Compiled prompt must include the dual alignment instruction header")

    def test_defect_4_final_shot_bound_last_frame_mention_must_resolve_to_picture_not_guide_image_prose(self):
        """Defect 4: When shot text mentions @Ending (bound as last_frame to the final shot),

        because the card was not compiled with kind='last_frame', media_labels.prompt_labels
        does not assign it a Picture token.
        resolve_guide_mentions replaces @Ending with generic prose 'the guide image' and emits
        Issue('guide_mention_prose').

        Expected:
        - @Ending must resolve to Picture token notation ('Ending, shown in <Picture 2>' or '<Picture 1>').
        - No Issue('guide_mention_prose') must be emitted for the valid last frame card.
        """
        card_ff = context_mod.ContextItem("img_ff", "Opening", "image", "opening.png", usage=("first_frame",))
        card_lf = context_mod.ContextItem("img_lf", "Ending", "image", "ending.png", usage=("last_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 2.5, "text": "Opening scene with @Opening.",
             "media": [{"schema_version": 1, "context_id": "img_ff", "role": "first_frame"}]},
            {"id": "s2", "start": 2.5, "end": 5.0, "text": "Ending scene with @Ending.",
             "media": [{"schema_version": 1, "context_id": "img_lf", "role": "last_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_ff, card_lf), shots_text=shots_doc, project_seconds=5.0, mode="fl2va")
        plan = project_mod.plan_project(ctx, 5.0, chunks_mod.ContinuityPlan("none"))
        compiled = plan.compiled[0]

        # Under the defect: prompt has "... Ending scene with the guide image." and issue 'guide_mention_prose'
        self.assertNotIn("the guide image", compiled.prompt,
                         "BUG-092: @Ending must not be degraded to generic 'the guide image' prose")
        self.assertIn("Ending, shown in <Picture 2>", compiled.prompt,
                      "BUG-092: @Ending must resolve to '<Picture 2>' token representation")
        prose_issues = [i for i in compiled.issues if i.code == "guide_mention_prose" and i.ref == "Ending"]
        self.assertEqual(len(prose_issues), 0,
                         "BUG-092: Spurious Issue('guide_mention_prose') must not be emitted for valid last frame card")


if __name__ == "__main__":
    unittest.main()
