"""Shot anchors must become actual native guide rows, not project-boundary promises."""
import json
import unittest
from unittest.mock import patch
from _pack import comfy_available, module, stub_prompt_server
from test_shot_scope_contract import plan, shot

ctx, opts = module("ng.core.context"), module("ng.core.context_options")
chunks, project = module("ng.core.chunks"), module("ng.core.project")
HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    stub_prompt_server()
    builder, media = module("ng.adapters.chunk_builder"), module("ng.adapters.media")
    native = module("minimax_core").core()
    from test_chunk_builder import empty_latent


def image(identity, **changes):
    return ctx.ContextItem(identity, identity, "image", identity + ".png", **changes)


class ShotGuides(unittest.TestCase):
    def test_interior_first_last_and_continue_use_real_shot_boundaries(self):
        video = ctx.ContextItem("v", "Video", "video", "v.mp4", length_s=10,
                                options=opts.ContextOptions(start_s=1, end_s=6))
        records = [shot("late", 6, 7.5, [("a", "first_frame"), ("b", "last_frame")])]
        result = plan(records, (image("a"), image("b")), 12, 5, chunks.ContinuityPlan())
        found = [(chunk, ref) for chunk, compiled in zip(result.plan.chunks, result.compiled) for ref in compiled.refs]
        self.assertEqual([(r.kind, r.ctx_id, r.start_f) for c, r in found], [("keyframe", "a", 59), ("keyframe", "b", 94)])
        self.assertNotIn("shot_boundary_role", {i.code for i in result.issues})
        result = plan([shot("late", 6, 8, [("v", "continue")])], (video,), 12, 5, chunks.ContinuityPlan())
        found = [(chunk, ref) for chunk, compiled in zip(result.plan.chunks, result.compiled) for ref in compiled.refs]
        self.assertEqual([(r.kind, r.start_f, r.trim_start_f, r.length_f) for c, r in found], [("continue_video", 0, 105, 39)])

    def test_a_keyframe_bound_to_a_shot_guides_its_start_unless_the_card_names_a_time(self):
        records = [shot("k", 4, 6, [("a", "keyframe")])]
        result = plan(records, (image("a", usage=("keyframe",)),), 10, 10)
        self.assertEqual([(r.kind, r.ctx_id, r.start_f) for r in result.compiled[0].refs], [("keyframe", "a", 96)], "placed in the Studio = the shot's start")
        timed = image("a", usage=("keyframe",), options=opts.ContextOptions(anchor_s=7))
        result = plan(records, (timed,), 10, 10)
        self.assertEqual([r.start_f for r in result.compiled[0].refs], [168], "an older card's own time still wins")

    def test_repeated_first_frame_binding_produces_two_distinct_guides(self):
        records = [shot("one", 1, 3, [("a", "first_frame")]), shot("two", 7, 9, [("a", "first_frame")])]
        result = plan(records, (image("a"),), 10, 10)
        self.assertEqual([(r.kind, r.ctx_id, r.start_f) for r in result.compiled[0].refs],
                         [("keyframe", "a", 24), ("keyframe", "a", 168)])

    def test_independent_shots_do_not_get_a_false_single_anchor_warning(self):
        records = [shot("one", 1, 3, [("a", "first_frame")]), shot("two", 7, 9, [("b", "first_frame")])]
        result = plan(records, (image("a"), image("b")), 10, 10)
        self.assertNotIn("anchor_multiple", {i.code for i in result.issues})
        self.assertEqual([r.start_f for r in result.compiled[0].refs], [24, 168])

    def test_normalized_overlap_and_end_clipping_control_anchor_time(self):
        records = [shot("one", 0, 4, []), shot("late", 3, 20, [("a", "first_frame"), ("b", "last_frame")])]
        result = plan(records, (image("a"), image("b")), 10, 10)
        # the clipped last shot ends with the video, which ends on H3's grid (243 frames): its picture is the real last frame
        self.assertEqual([(r.kind, r.start_f) for r in result.compiled[0].refs], [("keyframe", 96), ("last_frame", 242)])
        self.assertTrue({"shot_overlap", "shot_clipped"} <= {i.code for i in result.issues})

    def test_ref2va_subjects_survive_a_bound_opening_guide(self):
        records = [shot("one", 0, 8, [("a", "first_frame")])]
        result = plan(records, (image("a"), image("subject", usage=("reference",))), 8, 10)
        compiled = result.compiled[0]
        self.assertEqual(compiled.mode, "ref2va")
        # Bound as a global First frame card is (BUG-091): numbered picture plus the first-frame slot; the Subject stays Picture 1.
        self.assertEqual([(r.kind, r.ctx_id) for r in compiled.refs], [("picture", "subject"), ("picture", "a"), ("first_frame", "a")])
        self.assertEqual(dict(compiled.prompt_labels)["<Picture 1>"], "subject")
        # MiniMax ref-en 2.2: "<Picture 2> is the first frame of [Shot 1]" (it said "a composition anchor at 0s" until 2026-10-12)
        self.assertIn("<Picture 2> is the first frame of [Shot 1].", compiled.prompt)

    def test_binding_order_resolves_same_frame_conflicts_and_names_both_contexts(self):
        result = plan([shot("one", 3, 8, [("b", "first_frame"), ("a", "first_frame")])], (image("a"), image("b")), 8, 10)
        self.assertEqual([(r.kind, r.ctx_id, r.start_f) for r in result.compiled[0].refs], [("keyframe", "b", 72)])
        issue = next(i for i in result.issues if i.code == "anchor_multiple")
        self.assertIn("b", issue.text); self.assertIn("a", issue.text)

    def test_carry_heads_do_not_repeat_an_earlier_shot_boundary(self):
        result = plan([shot("one", 1, 8, [("a", "first_frame"), ("b", "last_frame")])],
                      (image("a"), image("b")), 12, 5, chunks.ContinuityPlan())
        found = [(chunk, ref) for chunk, compiled in zip(result.plan.chunks, result.compiled) for ref in compiled.refs]
        self.assertEqual(len(found), 2)
        self.assertEqual([(c.story_start_f - c.head_frames + r.start_f, r.ctx_id) for c, r in found], [(24, "a"), (191, "b")])
        self.assertTrue(all(r.start_f >= c.head_frames for c, r in found))

    def test_a_speaker_only_context_does_not_leak_a_guide_into_later_chunks(self):
        first = shot("one", 0, 3, [])
        first["spoken"] = [{"schema_version": 1, "speaker_id": "a", "text": "Hello."}]
        result = plan([first, shot("two", 6, 8, [])], (image("a", usage=("first_frame",)),),
                      12, 5, chunks.ContinuityPlan())
        self.assertFalse(result.compiled[1].refs)
        self.assertFalse(result.compiled[2].refs)

    def test_global_frame_slot_wins_a_conflict_with_a_bound_edge(self):
        records = [shot("one", 0, 8, [("bound", "first_frame")])]
        result = plan(records, (image("bound"), image("global", usage=("first_frame",))), 8, 10)
        self.assertEqual([(r.kind, r.ctx_id) for r in result.compiled[0].refs], [("first_frame", "global")])
        issue = next(i for i in result.issues if i.code == "anchor_multiple")
        self.assertIn("global", issue.text); self.assertIn("bound", issue.text)

    def test_fl2va_shot_opening_on_its_first_frame_starts_an_unpinned_part(self):
        # User plan (2026-10-11): three shots, each opening on its own picture. Inside a pinned part H3 took the picture as
        # the end of the running take and cut one frame later; a part of its own puts it on the trained frame 0.
        records = [shot("one", 0, 20, [("a", "first_frame")]), shot("two", 20, 40, [("b", "first_frame")]),
                   shot("three", 40, 60, [("c", "first_frame")])]
        pictures = tuple(image(k, usage=("first_frame",)) for k in "abc")
        result = plan(records, pictures, 60, 6.67, chunks.ContinuityPlan())
        parts = result.plan.chunks
        opening = [c for c in parts if not c.head_frames]
        self.assertEqual(len(opening), 3)
        self.assertTrue(all(c.head_frames == 22 for c in parts if c not in opening), "inside a shot the parts continue")
        starts = [s.start_f for s in module("ng.core.shots").parse_shots(result.context.shots_text, 1440)[0]]
        self.assertEqual([c.story_start_f for c in opening], starts, "each shot starts where its part starts")
        for chunk in opening:
            compiled = result.compiled[chunk.index]
            self.assertEqual(compiled.mode, "fl2va")
            self.assertIn(("first_frame", 0), [(r.kind, r.start_f) for r in compiled.refs])
        self.assertTrue(all(abs(start - 480 * k) <= 8 for k, start in enumerate(starts)))
        self.assertIn("opening_moved", {i.code for i in result.issues})
        self.assertNotIn("late_change", {i.code for i in result.issues})

    def test_fl2va_shots_anchored_on_both_ends_two_parts_each(self):
        # User plan: six shots of two parts, picture k opens shot k and closes shot k-1. The opening picture is a First frame on
        # its shot (until 2026-10-12 a Reference card on the shot fell back to First frame; now it stays a reference).
        names = "abcdefg"
        records = [shot("s%d" % k, 10 * k, 10 * k + 10, [(names[k], "first_frame"), (names[k + 1], "last_frame")]) for k in range(6)]
        document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": records})
        result = project.plan_project(ctx.DirectorContext(shots_text=document, items=tuple(image(n) for n in names),
                                                          project_seconds=60, mode="fl2va"), 5, chunks.ContinuityPlan())
        parts = result.plan.chunks
        self.assertEqual(len(parts), 12)
        for part, compiled in zip(parts, result.compiled):
            expected = [("first_frame", names[part.index // 2], 0)] if part.index % 2 == 0 else \
                       [("last_frame", names[part.index // 2 + 1], part.sampled_frames - 1)]
            self.assertEqual([(r.kind, r.ctx_id, r.start_f) for r in compiled.refs], expected)
            self.assertEqual(part.head_frames, 0 if part.index % 2 == 0 else 22)
        self.assertNotIn("reference_disabled", {i.code for i in result.issues})

    def fl2va_keyframe(self, at_s, seconds=20, end=20):
        record = shot("one", 0, end, [("a", "first_frame"), ("k", "keyframe"), ("z", "last_frame")])
        record["media"][1]["at_s"] = at_s
        document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": [record]})
        return project.plan_project(ctx.DirectorContext(shots_text=document, items=(image("a"), image("k"), image("z")),
                                                         project_seconds=seconds, mode="fl2va"), 12, chunks.ContinuityPlan())

    def test_fl2va_keyframe_inside_a_shot_ends_a_pinned_part_on_its_last_frame(self):
        # Measured 2026-10-11: H3 hits a picture inside a part but cuts one frame later; the last frame is a trained slot.
        result = self.fl2va_keyframe(10.0)
        parts = result.plan.chunks
        self.assertEqual([p.head_frames for p in parts], [0, 22], "the part after the keyframe keeps its pin: the shot runs on")
        kinds = [[(r.kind, r.ctx_id, r.start_f) for r in compiled.refs] for compiled in result.compiled]
        self.assertEqual(kinds[0], [("first_frame", "a", 0), ("last_frame", "k", parts[0].sampled_frames - 1)])
        self.assertEqual(kinds[1], [("last_frame", "z", parts[1].sampled_frames - 1)])
        shown = parts[0].story_end_f - 1
        self.assertLessEqual(abs(shown - 240), 8, "the keyframe moves at most half a grid step")
        self.assertIn("keyframe_moved", {i.code for i in result.issues})

    def test_fl2va_reference_card_on_no_shot_does_not_replace_the_first_shots_picture(self):
        # Real test 2026-10-11: a Reference card left on no shot became the global First frame and opened the video
        # instead of shot 1's own picture.
        record = shot("one", 0, 20, [("a", "first_frame"), ("z", "last_frame")])
        document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": [record]})
        result = project.plan_project(ctx.DirectorContext(shots_text=document, items=(image("a"), image("loose"), image("z")),
                                                          project_seconds=20, mode="fl2va"), 12, chunks.ContinuityPlan())
        first = [r.ctx_id for c in result.compiled for r in c.refs if r.kind == "first_frame"]
        self.assertEqual(first, ["a"])

    def test_a_storyboard_plans_its_shots_and_is_no_frame(self):
        # MiniMax ref-en 2.2: "<Picture 3> is a storyboard reference for [Shot 1] and [Shot 2], defining their viewpoint,
        # subject placement, and shot order." Before 2026-10-12 it became a keyframe guide at each shot's start.
        records = [shot("one", 0, 5, [("sb", "storyboard")]), shot("two", 5, 10, [("sb", "storyboard")])]
        items = (image("hero", usage=("reference",)), image("sb", usage=("storyboard",)))
        compiled = plan(records, items, 10, 10).compiled[0]
        self.assertEqual([(r.kind, r.ctx_id) for r in compiled.refs], [("picture", "hero"), ("picture", "sb")])
        self.assertIn("<Picture 2> is a storyboard reference for [Shot 1] and [Shot 2], defining their viewpoint, "
                      "subject placement, and shot order.", compiled.prompt)
        document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": records})
        fl = project.plan_project(ctx.DirectorContext(shots_text=document, items=items, project_seconds=10, mode="fl2va"),
                                  10, chunks.ContinuityPlan())
        self.assertIn("storyboard_unused", {i.code for i in fl.issues})
        self.assertNotIn("sb", {r.ctx_id for c in fl.compiled for r in c.refs})

    def test_fl2va_reference_on_a_shot_stays_a_reference_next_to_the_frames(self):
        # The user's choice 2026-10-12: a Reference picture never becomes the First frame; it reaches H3 as a reference picture
        # after the frame pictures (real tests: face, staff, back emblem and leg armour kept).
        records = [shot("one", 0, 8, [("start", "first_frame"), ("hero", "context")])]
        document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": records})
        result = project.plan_project(ctx.DirectorContext(shots_text=document, items=(image("start"), image("hero", usage=("reference",))),
                                                          project_seconds=8, mode="fl2va"), 10, chunks.ContinuityPlan())
        compiled = result.compiled[0]
        self.assertEqual(compiled.mode, "fl2va")
        self.assertEqual(sorted((r.kind, r.ctx_id) for r in compiled.refs), [("first_frame", "start"), ("picture", "hero")])
        labels = dict(compiled.prompt_labels)
        self.assertEqual((labels["<Picture 1>"], labels["<Picture 2>"]), ("start", "hero"))
        head = compiled.prompt.split("\n\n")[0]
        self.assertTrue(head.startswith("For the target video"), head)
        self.assertIn("The appearance of hero (face, hair, outfit and props) comes from <Picture 2>, a reference picture that is "
                      "not a frame of the video.", head)
        self.assertFalse({"reference_disabled", "reference_as_first_frame"} & {i.code for i in result.issues})
        alone = project.plan_project(ctx.DirectorContext(shots_text=json.dumps({"format": "h3-director-shots", "schema_version": 1,
                                                                                 "shots": [shot("one", 0, 8, [("hero", "context")])]}),
                                                         items=(image("hero", usage=("reference",)),), project_seconds=8, mode="fl2va"),
                                     10, chunks.ContinuityPlan()).compiled[0]
        self.assertEqual([r.kind for r in alone.refs], ["picture"], "no First frame falls back from a reference any more")

    def test_a_render_part_names_the_storyboard_panels_of_its_shots(self):
        # Each part numbers its shots from [Shot 1]; the storyboard picture shows all panels. Without the panel numbers every
        # part of the user's 30 s storyboard pointed at panels 1 and 2 (compiled 2026-10-12).
        records = [shot("p%d" % n, (n - 1) * 7.5, n * 7.5, [("sb", "storyboard")]) for n in range(1, 5)]
        items = (image("hero", usage=("reference",)), image("sb", usage=("storyboard",)))
        compiled = plan(records, items, 30, 10).compiled
        lines = [next(l for l in c.prompt.splitlines() if l.startswith("<Picture 2> is a storyboard")) for c in compiled]
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].endswith("[Shot 1] is its panel 1 and [Shot 2] is its panel 2."), lines[0])
        self.assertTrue(lines[1].endswith("[Shot 1] is its panel 2 and [Shot 2] is its panel 3."), lines[1])
        self.assertTrue(lines[2].endswith("[Shot 1] is its panel 3 and [Shot 2] is its panel 4."), lines[2])
        three = [shot("p%d" % n, (n - 1) * 3, n * 3, [("sb", "storyboard")]) for n in range(1, 4)]
        prompt = plan(three, items, 9, 10).compiled[0].prompt
        self.assertIn("for [Shot 1], [Shot 2] and [Shot 3], defining their viewpoint", prompt)
        self.assertNotIn("its panel", prompt, "a part with the whole storyboard needs no panel numbers")

    def test_a_keyframe_at_the_part_length_gives_two_parts_not_three(self):
        record = shot("one", 0, 20, [("a", "first_frame"), ("k", "keyframe"), ("z", "last_frame")])
        record["media"][1]["at_s"] = 10.0
        document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": [record]})
        result = project.plan_project(ctx.DirectorContext(shots_text=document, items=(image("a"), image("k"), image("z")),
                                                          project_seconds=20, mode="fl2va"), 10, chunks.ContinuityPlan())
        self.assertEqual(len(result.plan.chunks), 2, "243 frames for a 240 frame target is one part, not two")

    def test_a_keyframe_on_the_grid_is_not_moved(self):
        result = self.fl2va_keyframe(242 / 24.0)        # a first part of 17*14+5 = 243 frames ends on frame 242
        self.assertEqual(result.plan.chunks[0].story_end_f, 243)
        self.assertNotIn("keyframe_moved", {i.code for i in result.issues})
        record = json.loads(result.context.shots_text)["shots"][0]
        self.assertAlmostEqual(record["media"][1]["at_s"], 242 / 24.0)

    def test_a_keyframe_too_close_to_the_shot_end_stays_inside_the_part(self):
        result = self.fl2va_keyframe(18.5)
        self.assertIn("keyframe_too_close", {i.code for i in result.issues})
        self.assertNotIn(("last_frame", "k"), {(r.kind, r.ctx_id) for c in result.compiled for r in c.refs})

    def test_a_keyframe_time_survives_the_document_round_trip(self):
        binding = module("ng.core.shot_document").MediaBinding
        self.assertEqual(binding.from_dict({"schema_version": 1, "context_id": "k", "role": "keyframe", "at_s": 4.5}).to_dict()["at_s"], 4.5)
        self.assertNotIn("at_s", binding.from_dict({"schema_version": 1, "context_id": "k"}).to_dict(), "old documents stay as they were")

    def test_ref2va_keeps_a_shot_first_frame_inside_the_running_part(self):
        records = [shot("one", 0, 20, []), shot("two", 20, 40, [("b", "first_frame")])]
        result = plan(records, (image("b", usage=("first_frame",)), image("s")), 40, 6.67, chunks.ContinuityPlan())
        self.assertEqual(sum(not c.head_frames for c in result.plan.chunks), 1)

    def test_repeat_continue_keeps_a_subsecond_source_window_and_saved_offsets(self):
        video = ctx.ContextItem("v", "Video", "video", "v.mp4", length_s=4,
                                options=opts.ContextOptions(start_s=2, end_s=2 + 1/24))
        records = [shot("one", 1, 3, [("v", "continue")]), shot("two", 7, 9, [("v", "continue")])]
        result = plan(records, (video,), 10, 10)
        refs = [r for compiled in result.compiled for r in compiled.of_kind("continue_video")]
        self.assertEqual([(r.start_f, r.trim_start_f, r.length_f) for r in refs], [(0, 48, 1), (0, 48, 1)])
        for compiled in result.compiled:
            self.assertEqual(module("ng.core.compile").CompiledChunk.from_dict(compiled.to_dict()), compiled)


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class NativeGuideRows(unittest.TestCase):
    def test_native_guide_at_first_delivered_frame_survives_the_pinned_head(self):
        class Encoder:
            def tokenize(self, prompt, **kwargs): return "tokens"
            def encode_from_tokens_scheduled(self, tokens): return [[torch.zeros(1, 1, 8), {}]]
        class VAE:
            def encode(self, images): return torch.full((1, 24, 1, 4, 4), float(images.mean()))
        records = [shot("one", 0, 107/24, []), shot("two", 107/24, 12, [("a", "first_frame")])]
        result = plan(records, (image("a"),), 12, 5, chunks.ContinuityPlan())
        result = project.plan_project(ctx.DirectorContext.from_dict({**result.context.to_dict(), "width": 64, "height": 64}),
                                      5, chunks.ContinuityPlan())
        previous = empty_latent(result.plan.chunks[0].sampled_frames)
        with patch.object(media, "load_picture", return_value=torch.full((1, 64, 64, 3), .5)):
            built = builder.build_chunk(project.jobs(result)[1], Encoder(), VAE(), previous=previous, mm=native)
        guides = built.positive[0][1]["minimax_keyframes"]
        self.assertEqual(sum(row["resolved_frame_index"] == 22 for row in guides), 1)
        self.assertEqual(sum("latent" in row for row in guides), 8)
        self.assertTrue(any("audio_latent" in row for row in guides))
        self.assertEqual(built.dropped_anchors, ())

    def test_actual_native_continue_and_image_guides_keep_exact_local_frame_indices(self):
        class Encoder:
            def tokenize(self, prompt, **kwargs): return "tokens"
            def encode_from_tokens_scheduled(self, tokens): return [[torch.zeros(1, 1, 8), {}]]
        class VAE:
            def encode(self, images): return torch.full((1, 24, native.video_latent_t(images.shape[0]), 4, 4), float(images.mean()))
        video = ctx.ContextItem("v", "Video", "video", "v.mp4", length_s=3)
        records = [shot("one", 6, 8, [("v", "continue"), ("b", "last_frame")])]
        result = plan(records, (video, image("b")), 12, 5, chunks.ContinuityPlan())
        result = project.plan_project(ctx.DirectorContext.from_dict({**result.context.to_dict(), "width": 64, "height": 64}),
                                      5, chunks.ContinuityPlan())
        previous = empty_latent(result.plan.chunks[0].sampled_frames)
        frames = torch.full((39,64,64,3),.6)
        job = next(job for job in project.jobs(result) if job.chunk.continuation_id)
        with patch.object(media, "load_picture", return_value=torch.full((1, 64, 64, 3), .8)), \
             patch.object(module("ng.adapters.video_end"), "tail_frames", return_value=frames) as tail:
            built = builder.build_chunk(job, Encoder(), VAE(), previous=previous, mm=native)
        tail.assert_called_once_with("v.mp4", 0, 3,39)
        guides = built.positive[0][1]["minimax_keyframes"]
        expected = [ref.start_f for ref in job.compiled.refs if ref.kind=="keyframe"]+[0]
        self.assertEqual([row["resolved_frame_index"] for row in guides], expected)
        self.assertAlmostEqual(float(guides[0]["latent"].mean()), .8, delta=1/255)
        self.assertAlmostEqual(float(guides[1]["latent"].mean()), .6, delta=1/255)
        self.assertEqual(built.dropped_anchors, ())
        self.assertEqual(built.trim_frames,39)
        self.assertTrue(torch.all(built.latent['noise_mask'].unbind()[0][:,:,:12]==0))


if __name__ == "__main__":
    unittest.main()
