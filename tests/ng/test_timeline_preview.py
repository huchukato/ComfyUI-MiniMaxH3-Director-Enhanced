import unittest

from _pack import module

preview = module("ng.core.preview")
project = module("ng.core.project")
context = module("ng.core.context")


class TimelinePreview(unittest.TestCase):
    def test_exact_frame_axis_matches_real_planner_for_short_and_long_projects(self):
        for seconds, target in ((10, 0), (10, 5), (120, 10)):
            with self.subTest(seconds=seconds, target=target):
                data = preview.plan_preview({"director": {"idea": "A calm scene.", "project_seconds": seconds,
                                                          "chunk_seconds": target}})
                self.assertTrue(data["ok"])
                self.assertEqual(data["fps"], 24)
                self.assertEqual(data["requested_frames"], seconds * 24)
                planned = project.plan_project(context.DirectorContext.from_dict(data["director_context"]),
                                               target, preview.ContinuityPlan())
                self.assertEqual(data["total_frames"], planned.plan.total_frames)
                self.assertEqual(len(data["chunks"]), 12 if seconds == 120 else (2 if target == 5 else 1))
                self.assertEqual(len(data["chunks"]), len(planned.plan.chunks))
                for shown, chunk in zip(data["chunks"], planned.plan.chunks):
                    self.assertEqual(shown["story_start_f"], chunk.story_start_f)
                    self.assertEqual(shown["story_end_f"], chunk.story_end_f)
                    self.assertEqual(shown["story_end_f"] - shown["story_start_f"], shown["delivered_frames"])
                    self.assertEqual(shown["sampled_frames"], shown["delivered_frames"] + shown["head_frames"])

    def test_grid_warning_agrees_with_the_displayed_frame_duration(self):
        data = preview.plan_preview({"director": {"idea": "A calm scene.", "project_seconds": 10, "chunk_seconds": 5}})
        warning = next(issue for issue in data["issues"] if issue["code"] == "length_snapped")
        self.assertIn("10.125s (243 frames)", warning["text"])
