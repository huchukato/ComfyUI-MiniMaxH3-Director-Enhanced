"""Guide names resolve only to actual native tokens; unnumbered or omitted guides stay prose."""
import unittest
from unittest.mock import patch

from _pack import comfy_available, load_full_pack, module

ctx = module("ng.core.context")
opts = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def guide(identity, role, **extra):
    media = "video" if role == "continue" else "image"
    return ctx.ContextItem(identity, identity, media, "same.file", usage=(role,), **extra)


def plan(items, text, seconds=12, **extra):
    context = ctx.DirectorContext(idea=text, items=tuple(items), project_seconds=seconds, width=64, height=64,
                                  soundscape="Room tone", music="N/A", **extra)
    return project.plan_project(context, 5, chunks.ContinuityPlan("video_audio", 22, 24))


class GuideMentions(unittest.TestCase):
    def test_frame_only_picture_numbers_follow_native_first_then_last_order(self):
        for roles in (("first_frame",), ("last_frame",), ("last_frame", "first_frame")):
            items = [guide(role, role) for role in roles]
            compiled = plan(items, "Use " + " and ".join("@" + role for role in roles) + ".", seconds=4).compiled[0]
            expected = [role for role in ("first_frame", "last_frame") if role in roles]
            self.assertEqual(dict(compiled.prompt_labels), {"<Picture %d>" % n: role for n, role in enumerate(expected, 1)})
            self.assertNotIn("@", compiled.prompt)
            self.assertNotIn("<Subject", compiled.prompt)
            for n in range(1, len(expected) + 1):
                self.assertIn("<Picture %d>" % n, compiled.prompt)

    @unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
    def test_frame_adapter_sends_the_same_picture_order_to_actual_native_tokenizer(self):
        import torch
        load_full_pack()
        media, builder = module("ng.adapters.media"), module("ng.adapters.chunk_builder")
        native = module("minimax_core").core()
        class Encoder:
            def tokenize(self, prompt, **kwargs):
                self.images = kwargs["images"]
                return "tokens"
            def encode_from_tokens_scheduled(self, tokens):
                return [[torch.zeros(1, 1, 8), {}]]
        class VAE:
            def encode(self, images):
                return torch.zeros(1, 24, 1, 4, 4)
        for roles in (("first_frame",), ("last_frame",), ("last_frame", "first_frame")):
            result = plan([guide(role, role) for role in roles], "Use the frames.", seconds=4)
            encoder = Encoder()
            def picture(ref):
                return torch.full((1, 64, 64, 3), .25 if ref.kind == "first_frame" else .75)
            with patch.object(media, "load_picture", side_effect=picture):
                builder.build_chunk(project.jobs(result)[0], encoder, VAE(), mm=native)
            values = [float(image[0, 0, 0, 0]) for image in encoder.images]
            expected = [value for role, value in (("first_frame", .25), ("last_frame", .75)) if role in roles]
            self.assertEqual(len(values), len(expected))
            for actual, value in zip(values, expected):
                self.assertAlmostEqual(actual, value, delta=1 / 255)  # canvas resize has an 8-bit image boundary
            self.assertEqual(len(result.compiled[0].prompt_labels), len(encoder.images))

    def test_ref2va_anchors_use_actual_picture_ids_and_warn_when_absent_in_later_chunks(self):
        items = [guide("Start", "first_frame"), guide("End", "last_frame"), guide("Alice", "reference")]
        result = plan(items, "@Alice follows @Start then @End.")
        for compiled in result.compiled:
            self.assertNotIn("@", compiled.prompt)
            for number, ref in enumerate(compiled.of_kind("picture"), 1):
                self.assertEqual(dict(compiled.prompt_labels)["<Picture %d>" % number], ref.ctx_id)
            unavailable = [issue.text for issue in compiled.issues if issue.code == "guide_mention_unavailable"]
            if compiled.index != 0:
                self.assertTrue(any("Start" in text for text in unavailable))
            if compiled.index != len(result.compiled) - 1:
                self.assertTrue(any("End" in text for text in unavailable))

    def test_continue_name_uses_prose_and_never_invents_video_or_picture_tokens(self):
        result = plan([guide("Straße", "continue", length_s=4)], "Follow @STRASSE.")
        self.assertIn("Follow the continuation frame.", result.compiled[0].prompt)
        self.assertEqual(dict(result.compiled[0].prompt_labels), {})
        self.assertIn("guide_mention_prose", [issue.code for issue in result.compiled[0].issues])
        for compiled in result.compiled[1:]:
            self.assertIn("Follow Straße.", compiled.prompt)
            self.assertIn("guide_mention_unavailable", [issue.code for issue in compiled.issues])
            self.assertNotIn("<Video", compiled.prompt)
            self.assertNotIn("<Picture", compiled.prompt)

    def test_mixed_motion_continue_keeps_real_video_token_and_native_audio_numbering(self):
        item = ctx.ContextItem("Move", "Move", "video", "same.file", usage=("motion", "continue"), length_s=4,
                               options=opts.ContextOptions(video_audio="reference"))
        for compiled in plan([item], "Follow @Move.").compiled:
            self.assertIn("Follow <Video 1>.", compiled.prompt)
            self.assertEqual(dict(compiled.prompt_labels), {"<Video 1>": "Move", "<Audio 1>": "Move"})
            self.assertFalse(any(issue.code.startswith("guide_mention") for issue in compiled.issues))

    def test_timed_guide_uses_description_without_claiming_a_numbered_picture(self):
        item = guide("Key", "keyframe", description="a red doorway", options=opts.ContextOptions(anchor_s=6))
        for compiled in plan([item], "Approach @Key; leave @Unknown unchanged.").compiled:
            self.assertIn("Approach a red doorway; leave @Unknown unchanged.", compiled.prompt)
            self.assertEqual(dict(compiled.prompt_labels), {})
            code = "guide_mention_prose" if compiled.of_kind("keyframe") else "guide_mention_unavailable"
            self.assertIn(code, [issue.code for issue in compiled.issues])

    def test_ignored_duplicate_anchor_does_not_borrow_the_first_cards_picture(self):
        result = plan([guide("Start", "first_frame"), guide("Other", "first_frame")], "Use @Other.", seconds=4)
        compiled = result.compiled[0]
        self.assertIn("Use Other.", compiled.prompt)
        self.assertEqual(dict(compiled.prompt_labels), {"<Picture 1>": "Start"})
        self.assertIn("guide_mention_unavailable", [issue.code for issue in compiled.issues])

    def test_manual_prompt_override_is_not_rewritten(self):
        compiled = plan([guide("Start", "first_frame")], "Use @Start.", seconds=4,
                        prompt_override="My raw @Start prompt.").compiled[0]
        self.assertEqual(compiled.prompt, "My raw @Start prompt.")
        self.assertFalse(any(issue.code.startswith("guide_mention") for issue in compiled.issues))
