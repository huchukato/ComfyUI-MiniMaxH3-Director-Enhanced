"""Continuation sound belongs to the timed source prefix, never a general AV reference."""
import unittest

from _pack import module


class ContinueSoundtrack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = module("ng.core.context")
        cls.options = module("ng.core.context_options")
        cls.project = module("ng.core.project")
        cls.chunks = module("ng.core.chunks")

    def plan(self, mode, sound):
        item = self.context.ContextItem("source", "Source", "video", "clip.mp4", usage=("continue",), length_s=8,
                                        options=self.options.ContextOptions(start_s=.5, end_s=3.5, video_audio=sound))
        context = self.context.DirectorContext(idea="Continue walking.", mode=mode, project_seconds=5, items=(item,))
        project = self.project.plan_project(context, 6, self.chunks.ContinuityPlan("video_audio", 22, 24))
        return self.project.jobs(project)[0]

    def test_auto_and_ref_keep_a_timed_prefix_without_a_repeating_video_reference(self):
        for mode in ("auto", "ref2va"):
            with self.subTest(mode=mode):
                job = self.plan(mode, "reference")
                self.assertEqual(job.compiled.mode, "t2va" if mode == "auto" else "ref2va")
                self.assertEqual(len(job.compiled.of_kind("continue_video")), 1)
                refs = job.compiled.of_kind("video")
                self.assertEqual(refs, ())
                self.assertNotIn("<Video 1>", job.compiled.prompt)
                self.assertEqual(job.chunk.head_frames, 39 if mode == "auto" else 56)
                self.assertEqual(job.compiled.of_kind("continue_video")[0].trim_start_f, 45 if mode == "auto" else 28)
                self.assertFalse(any(i.code == "reference_disabled" for i in job.project.issues))

    def test_explicit_fl_uses_its_sound_prefix_without_a_false_unsupported_warning(self):
        job = self.plan("fl2va", "reference")
        self.assertEqual(job.compiled.mode, "t2va")
        self.assertEqual(len(job.compiled.of_kind("continue_video")), 1)
        self.assertEqual(job.compiled.of_kind("video"), ())
        warnings = [i.text for i in job.project.issues if i.code == "reference_disabled"]
        self.assertEqual(warnings, [])

    def test_ignore_keeps_auto_fl_without_video_reference(self):
        job = self.plan("auto", "ignore")
        self.assertEqual(job.compiled.mode, "t2va")
        self.assertEqual(len(job.compiled.of_kind("continue_video")), 1)
        self.assertEqual(job.compiled.of_kind("video"), ())


if __name__ == "__main__":
    unittest.main()
