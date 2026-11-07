import unittest
from _pack import module

ctx = module("ng.core.context")
checks = module("ng.core.context_checks")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


class Diagnostics(unittest.TestCase):
    def test_discarded_roles_are_visible(self):
        items = (ctx.ContextItem("a", "Start A", "image", "a.png", usage=("first_frame",)),
                 ctx.ContextItem("b", "Start B", "image", "a.png", usage=("first_frame",)),
                 ctx.ContextItem("c", "Clip", "video", "c.mp4"),
                 ctx.ContextItem("d", "Sound", "audio", "d.wav", usage=("lock", "copy")))
        codes = {i.code for i in checks.check_context(ctx.DirectorContext(items=items, mode="fl2va"))}
        self.assertEqual(codes, {"anchor_multiple", "source_shared", "reference_disabled", "audio_roles"})

    def test_unknown_usage_is_not_remapped_and_pending_image_is_reported(self):
        items = tuple(ctx.ContextItem(str(n), media, media, "source", usage=("future",))
                      for n, media in enumerate(("audio", "video", "text")))
        pending = ctx.ContextItem("key", "Key", "image", "key.png", usage=("keyframe",))
        result = project.plan_project(ctx.DirectorContext(idea="A walk", items=items + (pending,)), 10,
                                      chunks.ContinuityPlan("none"))
        self.assertEqual(result.compiled[0].refs, ())
        self.assertNotIn("source", result.compiled[0].prompt)
        self.assertTrue({"usage_unknown", "usage_pending"} <= {i.code for i in result.issues})

class FrameAnchors(unittest.TestCase):
    """R6: one first frame and one last frame per chunk, and the dropped one is named."""

    def image(self, ctx_id, name, usage):
        return ctx.ContextItem(ctx_id, name, "image", "%s.png" % ctx_id, usage=usage)

    def compile_one(self, items, seconds=8, chunk=0.0):
        director = ctx.DirectorContext(idea="A walk.", project_seconds=seconds, soundscape="room tone",
                                       shots_text="0-%d: A walk." % seconds, items=tuple(items))
        return project.plan_project(director, chunk, chunks.ContinuityPlan("video_audio", 22, 24))

    def test_first_and_last_reach_their_own_chunk_only(self):
        result = self.compile_one([self.image("a", "Start", ("first_frame",)), self.image("b", "Ende", ("last_frame",))], 20)
        self.assertTrue(len(result.plan.chunks) > 1)
        first, last = result.compiled[0], result.compiled[-1]
        self.assertEqual([r.kind for r in first.refs], ["first_frame"], "a first frame belongs to the opening chunk")
        self.assertEqual([r.kind for r in last.refs], ["last_frame"], "a last frame belongs to the final chunk")
        self.assertEqual([r.ctx_id for r in last.refs], ["b"])

    def test_only_one_last_frame_is_sent_and_the_dropped_one_is_named(self):
        # H3's frame conditioning has a single slot per role. Before this, both images were handed to the model.
        items = [self.image("a", "Ende A", ("last_frame",)), self.image("b", "Ende B", ("last_frame",))]
        result = self.compile_one(items)
        self.assertEqual([r.kind for r in result.compiled[0].refs], ["last_frame"])
        self.assertEqual([r.ctx_id for r in result.compiled[0].refs], ["a"], "the first item wins the single slot")
        # check_context runs once per project, so this warning sits on the project, not on the chunk.
        note = [i for i in result.issues if i.code == "anchor_multiple"][0]
        self.assertIn("Ende A", str(note))
        self.assertIn("Ende B", str(note))
        self.assertIn("is used", str(note), "the warning must say which one actually reached the model")

    def test_one_first_and_one_last_can_both_be_sent(self):
        compiled = self.compile_one([self.image("a", "Start", ("first_frame",)),
                                     self.image("b", "Ende", ("last_frame",))]).compiled[0]
        self.assertEqual(sorted(r.kind for r in compiled.refs), ["first_frame", "last_frame"])
        self.assertEqual([i.code for i in compiled.issues if i.code == "anchor_multiple"], [])

    def test_a_last_frame_alone_still_switches_the_mode_to_fl2va(self):
        # Without the anchor the planner falls back to t2va, which would ignore the frame entirely.
        compiled = self.compile_one([self.image("b", "Ende", ("last_frame",))]).compiled[0]
        self.assertEqual(compiled.mode, "fl2va")
        self.assertEqual([r.kind for r in compiled.refs], ["last_frame"])

    def test_a_reference_and_a_last_frame_on_one_image_are_both_sent(self):
        # The roles are independent: the picture guides identity, the same file also ends the clip.
        compiled = self.compile_one([self.image("x", "Beides", ("reference", "last_frame"))]).compiled[0]
        self.assertEqual(compiled.mode, "ref2va")
        self.assertIn("picture", [r.kind for r in compiled.refs])
        self.assertIn("last_frame", [r.kind for r in compiled.refs])

    def test_first_and_last_on_one_file_are_named_for_their_own_role(self):
        # Two cards holding the SAME file: each role must still resolve to its own card, and the file is reported.
        items = [ctx.ContextItem("a", "Start", "image", "shared.png", usage=("first_frame",)),
                 ctx.ContextItem("b", "Ende", "image", "shared.png", usage=("last_frame",))]
        result = self.compile_one(items)
        self.assertEqual([(r.kind, r.ctx_id) for r in result.compiled[0].refs],
                         [("first_frame", "a"), ("last_frame", "b")],
                         "the roles must not be mixed up when both cards hold the same file")
        self.assertIn("source_shared", {i.code for i in result.issues})

    def test_an_untimed_guide_is_reported_and_not_sent(self):
        # keyframe without a scene time is pending; it must not appear as a reference.
        result = self.compile_one([self.image("k", "Key", ("keyframe",))])
        self.assertEqual(result.compiled[0].refs, ())
        self.assertIn("usage_pending", {i.code for i in result.compiled[0].issues})


if __name__ == "__main__":
    unittest.main()