"""Guide times follow delivered chunk boundaries and native frame conditioning."""
import unittest
from unittest.mock import patch

from _pack import comfy_available, load_full_pack, module

ctx = module("ng.core.context")
opts = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def image(name, role, frame=-1, source="guide.png"):
    return ctx.ContextItem(name, name, "image", source, usage=(role,),
                           options=opts.ContextOptions(anchor_s=frame / 24 if frame >= 0 else -1))


def plan(items=(), mode="video_audio", seconds=12):
    context = ctx.DirectorContext(idea="A doorway opens.", items=tuple(items), project_seconds=seconds,
                                  width=64, height=64, soundscape="Room tone", music="N/A")
    return project.plan_project(context, 5, chunks.ContinuityPlan(mode, 22, 24))


class GuideBoundaries(unittest.TestCase):
    def test_boundary_and_adjacent_frames_belong_to_exactly_one_delivered_chunk(self):
        for mode in ("none", "video", "video_audio"):
            base = plan(mode=mode)
            for boundary in [chunk.story_start_f for chunk in base.plan.chunks[1:]]:
                for frame in (boundary - 1, boundary, boundary + 1):
                    result = plan([image("Door", "keyframe", frame)], mode=mode)
                    found = [(chunk, ref) for chunk, compiled in zip(result.plan.chunks, result.compiled)
                             for ref in compiled.of_kind("keyframe")]
                    self.assertEqual(len(found), 1)
                    chunk, ref = found[0]
                    self.assertTrue(chunk.story_start_f <= frame < chunk.story_end_f)
                    self.assertEqual(ref.start_f, frame - chunk.story_start_f + chunk.head_frames)
                    self.assertGreaterEqual(ref.start_f, chunk.head_frames)

    def test_last_frame_and_snapped_project_padding_remain_valid_guide_times(self):
        total = plan().plan.total_frames
        for frame in (288, total - 1):
            result = plan([image("EndGuide", "keyframe", frame)])     # a storyboard has no time since 2026-10-12
            self.assertEqual(result.compiled[-1].of_kind("keyframe")[0].start_f,
                             frame - result.plan.chunks[-1].story_start_f + 22)
            self.assertNotIn("guide_outside_project", [issue.code for issue in result.issues])

    def test_guide_at_exclusive_end_or_later_names_its_card_and_last_valid_time(self):
        total = plan().plan.total_frames
        for role in ("keyframe",):
            for frame in (total, 480):
                result = plan([image("OutsideDoor", role, frame)])
                self.assertFalse(any(one.of_kind("keyframe") for one in result.compiled))
                warnings = [issue for issue in result.issues if issue.code == "guide_outside_project"]
                self.assertEqual(len(warnings), 1)
                self.assertEqual(warnings[0].ref, "OutsideDoor")
                self.assertIn("%.3f" % ((total - 1) / 24), warnings[0].text)
                self.assertIn("extend", warnings[0].text)
                self.assertEqual(result.context.items[0].options.anchor_s, frame / 24)

    def test_untimed_missing_source_and_reference_only_are_not_outside_time_warnings(self):
        result = plan([image("Untimed", "keyframe"), image("Missing", "keyframe", 480, ""),
                       image("Reference", "reference", 480)])
        self.assertNotIn("guide_outside_project", [issue.code for issue in result.issues])
        self.assertIn("usage_pending", [issue.code for issue in result.issues])
        self.assertIn("source_missing", [issue.code for issue in result.issues])

    @unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
    def test_native_first_last_and_timed_guides_at_identical_offsets_are_all_preserved(self):
        import torch
        load_full_pack()
        media, builder = module("ng.adapters.media"), module("ng.adapters.chunk_builder")
        native = module("minimax_core").core()
        class Encoder:
            def tokenize(self, prompt, **kwargs):
                return "tokens"
            def encode_from_tokens_scheduled(self, tokens):
                return [[torch.zeros(1, 1, 8), {}]]
        class VAE:
            def encode(self, images):
                return torch.full((1, 24, 1, 4, 4), float(images.mean()))
        base = plan(mode="none", seconds=5)
        final = base.plan.total_frames - 1
        items = [image("Start", "first_frame"), image("End", "last_frame"),
                 image("AtStart", "keyframe", 0), image("AtEnd", "keyframe", final)]
        result = plan(items, mode="none", seconds=5)
        markers = {item.id: (index + 1) / 5 for index, item in enumerate(items)}
        with patch.object(media, "load_picture", side_effect=lambda ref: torch.full((1, 64, 64, 3), markers[ref.ctx_id])):
            built = builder.build_chunk(project.jobs(result)[0], Encoder(), VAE(), mm=native)
        frames = built.positive[0][1]["minimax_keyframes"]
        self.assertEqual([frame["resolved_frame_index"] for frame in frames], [0, final, 0, final])
        for frame, item in zip(frames, items):
            self.assertAlmostEqual(float(frame["latent"].mean()), markers[item.id], delta=1 / 255)
        self.assertEqual(built.dropped_anchors, ())
