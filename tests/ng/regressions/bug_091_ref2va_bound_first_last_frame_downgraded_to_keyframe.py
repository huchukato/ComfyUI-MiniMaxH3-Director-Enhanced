"""BUG-091: Ref2VA mode with shot-bound first_frame or last_frame image cards in guide_timing._bound_ref.

In ng/core/guide_timing.py:57-61:
    kind = "keyframe"
    if mode != "ref2va" and ((role == "first_frame" and local == 0) or
                            (role == "last_frame" and local == chunk.sampled_frames - 1)):
        kind = role
    return MediaRef(kind, item.id, item.source, local, 1)

When a project is in References mode (Ref2VA) and the user structures shots in the Studio UI by
binding a First Frame card to Shot 0 (local_start_f == 0) or a Last Frame card to the final shot
(local_end_f == chunk.sampled_frames), the condition `mode != "ref2va"` unconditionally prevents
`kind = role` from executing.

As a result:
1. `plan_guides` forces `ref.kind = "keyframe"`.
2. `legacy_bridge._anchor_segments` checks only `ref.kind == "first_frame"` and `ref.kind == "last_frame"`;
   it ignores `keyframe` refs, returning an empty list.
3. `legacy_bridge.build_timeline` never passes timeline anchor segments to `plan.plan_timeline`.
4. Downstream in `compile_chunk`:
   - No `<Picture N>` token is generated for the first/last frame card.
   - The compiled prompt omits `<Picture N> is a composition anchor at 0s` and
     `<Picture N> is the last frame of the target video`.
   - The generation summary is downgraded from `[keyframe completion + reference generation]`
     to plain `[reference generation]`.
   - Retention analysis for the composition anchor / last frame is completely missing.
5. In `media_labels.resolve_guide_mentions`:
   - Any mention of the frame card (e.g. `@Castle` or `@Sunset`) cannot resolve to `<Picture N>`.
   - It is degraded to the plain prose phrase `"the guide image"`.
   - A spurious issue `guide_mention_prose` is emitted ("has frame conditioning but no numbered
     reference token; its named mention uses prose").
6. The native H3 sampler never receives the first/last frame image.

In contrast:
- `docs/NG.md:237` guarantees: "First / last frame open or end the video, or the shot the picture
  is dropped on in the Studio."
- Unbound first/last frame cards in Ref2VA work properly via `_global_guides`.
- Shot-bound first/last frame cards in FL2VA work properly because `mode != "ref2va"` is True.
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


def make_shots_json(shots_list):
    return json.dumps({
        "format": "h3-director-shots",
        "schema_version": 1,
        "shots": shots_list,
    })


class TestBug091Ref2VABoundFirstLastFrame(unittest.TestCase):
    """Test suite for BUG-091: Ref2VA shot-bound first and last frame degradation to keyframe."""

    def test_control_1_fl2va_shot_bound_first_and_last_frame_retains_edge_kinds(self):
        """Control: In FL2VA mode, shot-bound first_frame (at local 0) and last_frame (at local end)

        correctly retain kind='first_frame' and kind='last_frame'.
        """
        card_ff = context_mod.ContextItem("img_ff", "Opening", "image", "opening.png", usage=("first_frame",))
        card_lf = context_mod.ContextItem("img_lf", "Ending", "image", "ending.png", usage=("last_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 2.5, "text": "Opening scene.",
             "media": [{"schema_version": 1, "context_id": "img_ff", "role": "first_frame"}]},
            {"id": "s2", "start": 2.5, "end": 5.0, "text": "Ending scene.",
             "media": [{"schema_version": 1, "context_id": "img_lf", "role": "last_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_ff, card_lf), shots_text=shots_doc, project_seconds=5.0)
        chunk = chunks_mod.Chunk(
            index=0, story_start_f=0, delivered_frames=120, head_frames=0, is_last=True,
            shots=(
                chunks_mod.ChunkShot(0, 0, 60, "Opening scene.", False, False, "s1",
                                     media=(doc_mod.MediaBinding("img_ff", "first_frame"),)),
                chunks_mod.ChunkShot(1, 60, 120, "Ending scene.", False, False, "s2",
                                     media=(doc_mod.MediaBinding("img_lf", "last_frame"),)),
            )
        )
        guides, issues = guides_mod.plan_guides(ctx, chunk, "fl2va")
        kinds_by_id = {g.ctx_id: g.kind for g in guides}
        self.assertEqual(kinds_by_id.get("img_ff"), "first_frame",
                         "In FL2VA, shot-bound first_frame at local 0 must be 'first_frame'")
        self.assertEqual(kinds_by_id.get("img_lf"), "last_frame",
                         "In FL2VA, shot-bound last_frame at chunk end must be 'last_frame'")

    def test_control_2_ref2va_unbound_first_and_last_frame_compiles_composition_anchor_and_last_frame(self):
        """Control: In Ref2VA mode with unbound cards, _global_guides emits first_frame and last_frame,

        and compile_chunk generates composition anchor at 0s, last frame token, and keyframe completion.
        """
        card_hero = context_mod.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",))
        card_ff = context_mod.ContextItem("castle", "Castle", "image", "castle.png", usage=("first_frame",))
        card_lf = context_mod.ContextItem("sunset", "Sunset", "image", "sunset.png", usage=("last_frame",))
        ctx = context_mod.DirectorContext(items=(card_hero, card_ff, card_lf), shots_text="", project_seconds=5.0)
        chunk = chunks_mod.Chunk(
            index=0, story_start_f=0, delivered_frames=120, head_frames=0, is_last=True,
            shots=(chunks_mod.ChunkShot(0, 0, 120, "Hero travels.", False, False, "s1"),)
        )
        compiled = compile_mod.compile_chunk(ctx, chunk, chunks_mod.ContinuityPlan("none"))
        guide_kinds = {r.ctx_id: r.kind for r in compiled.refs if r.kind in ("first_frame", "last_frame")}
        self.assertEqual(guide_kinds.get("castle"), "first_frame")
        self.assertEqual(guide_kinds.get("sunset"), "last_frame")
        self.assertIn("is the first frame of [Shot 1].", compiled.prompt)
        self.assertIn("is the last frame of [Shot 1].", compiled.prompt)
        self.assertIn("summary: [keyframe completion + reference generation]", compiled.prompt)

    def test_control_3_ref2va_intermediate_shot_bound_frame_correctly_downgrades_to_keyframe(self):
        """Control: In Ref2VA mode, binding an image to an intermediate shot (not frame 0 or chunk end)

        must correctly produce kind='keyframe'.
        """
        card_hero = context_mod.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",))
        card_mid = context_mod.ContextItem("tower", "Tower", "image", "tower.png", usage=("first_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 2.0, "text": "Intro."},
            {"id": "s2", "start": 2.0, "end": 5.0, "text": "Arrive at Tower.",
             "media": [{"schema_version": 1, "context_id": "tower", "role": "first_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_hero, card_mid), shots_text=shots_doc, project_seconds=5.0)
        chunk = chunks_mod.Chunk(
            index=0, story_start_f=0, delivered_frames=120, head_frames=0, is_last=True,
            shots=(
                chunks_mod.ChunkShot(0, 0, 48, "Intro.", False, False, "s1"),
                chunks_mod.ChunkShot(1, 48, 120, "Arrive at Tower.", False, False, "s2",
                                     media=(doc_mod.MediaBinding("tower", "first_frame"),)),
            )
        )
        guides, _ = guides_mod.plan_guides(ctx, chunk, "ref2va")
        kinds_by_id = {g.ctx_id: g.kind for g in guides}
        self.assertEqual(kinds_by_id.get("tower"), "keyframe",
                         "Intermediate shot guide (frame 48 > 0) must be a keyframe")

    def test_defect_1_ref2va_shot_bound_first_frame_at_zero_must_be_first_frame_kind(self):
        """Defect 1: In Ref2VA mode, plan_guides with a first_frame card bound to Shot 0 (start 0s)

        must produce MediaRef with kind='first_frame', but currently forces kind='keyframe'.
        """
        card_hero = context_mod.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",))
        card_ff = context_mod.ContextItem("castle", "Castle", "image", "castle.png", usage=("first_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 5.0, "text": "Hero arrives at Castle.",
             "media": [{"schema_version": 1, "context_id": "castle", "role": "first_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_hero, card_ff), shots_text=shots_doc, project_seconds=5.0)
        chunk = chunks_mod.Chunk(
            index=0, story_start_f=0, delivered_frames=120, head_frames=0, is_last=True,
            shots=(chunks_mod.ChunkShot(0, 0, 120, "Hero arrives at Castle.", False, False, "s1",
                                         media=(doc_mod.MediaBinding("castle", "first_frame"),)),)
        )
        guides, _ = guides_mod.plan_guides(ctx, chunk, "ref2va")
        kinds_by_id = {g.ctx_id: g.kind for g in guides}
        self.assertEqual(kinds_by_id.get("castle"), "first_frame",
                         "BUG-091: In Ref2VA mode, shot-bound first_frame at local frame 0 must produce "
                         "kind='first_frame', not be downgraded to 'keyframe'")

    def test_defect_2_ref2va_shot_bound_first_frame_must_compile_composition_anchor(self):
        """Defect 2: In Ref2VA mode, compile_chunk with a first_frame card bound to Shot 0

        must generate '<Picture N> is a composition anchor at 0s' and 'keyframe completion' in prompt.
        Currently, the anchor is omitted and summary is downgraded to '[reference generation]'.
        """
        card_hero = context_mod.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",))
        card_ff = context_mod.ContextItem("castle", "Castle", "image", "castle.png", usage=("first_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 5.0, "text": "Hero arrives at the gate.",
             "media": [{"schema_version": 1, "context_id": "castle", "role": "first_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_hero, card_ff), shots_text=shots_doc, project_seconds=5.0)
        chunk = chunks_mod.Chunk(
            index=0, story_start_f=0, delivered_frames=120, head_frames=0, is_last=True,
            shots=(chunks_mod.ChunkShot(0, 0, 120, "Hero arrives at the gate.", False, False, "s1",
                                         media=(doc_mod.MediaBinding("castle", "first_frame"),)),)
        )
        compiled = compile_mod.compile_chunk(ctx, chunk, chunks_mod.ContinuityPlan("none"))
        self.assertIn("is the first frame of [Shot 1].", compiled.prompt,
                      "BUG-091: Shot-bound first_frame card in Ref2VA must produce '<Picture N> is the first frame of [Shot 1]' (MiniMax ref-en 2.2) in prompt")
        self.assertIn("summary: [keyframe completion + reference generation]", compiled.prompt,
                      "BUG-091: Shot-bound first_frame in Ref2VA must specify keyframe completion in summary")
        self.assertTrue(any(r.kind == "first_frame" and r.ctx_id == "castle" for r in compiled.refs),
                        "BUG-091: compiled.refs must include MediaRef('first_frame', 'castle')")

    def test_defect_3_ref2va_shot_bound_last_frame_must_compile_last_frame_token(self):
        """Defect 3: In Ref2VA mode, compile_chunk with a last_frame card bound to the final shot

        must generate '<Picture N> is the last frame of the target video' in prompt.
        Currently, the last frame anchor is omitted.
        """
        card_hero = context_mod.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",))
        card_lf = context_mod.ContextItem("sunset", "Sunset", "image", "sunset.png", usage=("last_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 5.0, "text": "Hero rides into the distance.",
             "media": [{"schema_version": 1, "context_id": "sunset", "role": "last_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_hero, card_lf), shots_text=shots_doc, project_seconds=5.0)
        chunk = chunks_mod.Chunk(
            index=0, story_start_f=0, delivered_frames=120, head_frames=0, is_last=True,
            shots=(chunks_mod.ChunkShot(0, 0, 120, "Hero rides into the distance.", False, False, "s1",
                                         media=(doc_mod.MediaBinding("sunset", "last_frame"),)),)
        )
        compiled = compile_mod.compile_chunk(ctx, chunk, chunks_mod.ContinuityPlan("none"))
        self.assertIn("is the last frame of [Shot 1].", compiled.prompt,
                      "BUG-091: Shot-bound last_frame card in Ref2VA must produce last frame token in prompt")
        self.assertIn("summary: [keyframe completion + reference generation]", compiled.prompt,
                      "BUG-091: Shot-bound last_frame in Ref2VA must specify keyframe completion in summary")
        self.assertTrue(any(r.kind == "last_frame" and r.ctx_id == "sunset" for r in compiled.refs),
                        "BUG-091: compiled.refs must include MediaRef('last_frame', 'sunset')")

    def test_defect_4_ref2va_shot_bound_frame_mention_must_resolve_to_picture_not_guide_image_prose(self):
        """Defect 4: In Ref2VA mode, shot text mentioning '@Castle' or '@Sunset' bound to Shot 0 / final shot

        must resolve to '<Picture N>' (e.g. 'Castle, shown in <Picture 2>') and must not emit
        spurious Issue('guide_mention_prose') or degrade mention to generic prose 'the guide image'.
        """
        card_hero = context_mod.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",))
        card_ff = context_mod.ContextItem("castle", "Castle", "image", "castle.png", usage=("first_frame",))
        shots_doc = make_shots_json([
            {"id": "s1", "start": 0.0, "end": 5.0, "text": "Hero stands before @Castle.",
             "media": [{"schema_version": 1, "context_id": "castle", "role": "first_frame"}]},
        ])
        ctx = context_mod.DirectorContext(items=(card_hero, card_ff), shots_text=shots_doc, project_seconds=5.0)
        chunk = chunks_mod.Chunk(
            index=0, story_start_f=0, delivered_frames=120, head_frames=0, is_last=True,
            shots=(chunks_mod.ChunkShot(0, 0, 120, "Hero stands before @Castle.", False, False, "s1",
                                         media=(doc_mod.MediaBinding("castle", "first_frame"),)),)
        )
        compiled = compile_mod.compile_chunk(ctx, chunk, chunks_mod.ContinuityPlan("none"))
        # Must not have guide_mention_prose issue
        issue_codes = [i.code for i in compiled.issues]
        self.assertNotIn("guide_mention_prose", issue_codes,
                         "BUG-091: Shot-bound first_frame in Ref2VA must not emit spurious 'guide_mention_prose' issue")
        # Must resolve @Castle to picture reference in detailed_description, not 'the guide image'
        self.assertNotIn("the guide image", compiled.prompt,
                         "BUG-091: Shot-bound first_frame mention must not be degraded to prose 'the guide image'")
        self.assertRegex(compiled.prompt, r"Castle, shown in <Picture \d+>",
                         "BUG-091: Shot-bound first_frame mention '@Castle' must resolve to 'Castle, shown in <Picture N>'")


if __name__ == "__main__":
    unittest.main()
