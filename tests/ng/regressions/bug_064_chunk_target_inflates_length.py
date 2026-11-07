"""BUG-064: a render-part target shorter than H3's minimum clip multiplies the finished video's length.

User flow (Studio): set Duration to 5.3 s and Render part to "5 s" (an option the Studio offers), keep the default
continuity. The planner splits the 127 frames into two parts; each part must be at least as long as H3's trained minimum,
so the plan delivers 192 frames (8.0 s). The same happens for native NGDirector/NGH3Director widgets (`chunk_seconds`,
0-15 s, step 0.5) and for a 4 s part (the lower end of the documented 4-15 s range) on a 10 s project.

Expected: the finished video stays within one 17-frame grid step of the requested duration, which is the contract
`test_chunks.test_every_pin_window_and_many_lengths_stay_on_grid` already asserts for every target of 200 frames, and what the
`project_seconds` tooltip promises ("can differ by a fraction of a second").

Run: python -B tests/ng/regressions/bug_064_chunk_target_inflates_length.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _pack import module  # noqa: E402

chunks = module("ng.core.chunks")
context = module("ng.core.context")
project = module("ng.core.project")

GRID_STEP = 17


def planned(seconds, part_seconds, continuity=None):
    director = context.DirectorContext.from_dict({"schema_version": 1, "idea": "A woman walks along a quiet beach.",
                                                  "project_seconds": seconds, "items": []})
    return project.plan_project(director, part_seconds, continuity or chunks.ContinuityPlan())


class ChunkTargetKeepsLength(unittest.TestCase):
    def assertLengthKept(self, seconds, part_seconds, continuity=None):
        plan = planned(seconds, part_seconds, continuity).plan
        requested = int(round(seconds * 24))
        self.assertLessEqual(abs(plan.total_frames - requested), GRID_STEP,
                             "%.1f s project with %.1f s render parts became %d frames (%.1f s) in %d parts, requested %d frames"
                             % (seconds, part_seconds, plan.total_frames, plan.total_frames / 24.0, len(plan.chunks), requested))

    def test_bug_064_studio_5_3_seconds_with_5_second_parts_default_continuity(self):
        self.assertLengthKept(5.3, 5.0)

    def test_bug_064_studio_5_3_seconds_with_5_second_parts_hard_cuts(self):
        self.assertLengthKept(5.3, 5.0, chunks.ContinuityPlan("none"))

    def test_bug_064_four_second_parts_on_a_ten_second_project(self):
        self.assertLengthKept(10.0, 4.0, chunks.ContinuityPlan("none"))

    # Controls: the same planner keeps the length when the part target is not below what two parts can hold.
    def test_control_auto_part_keeps_the_length(self):
        self.assertLengthKept(5.3, 0.0)

    def test_control_five_second_parts_on_ten_seconds(self):
        self.assertLengthKept(10.0, 5.0)

    def test_control_ten_second_parts_on_twelve_seconds(self):
        self.assertLengthKept(12.0, 10.0)


if __name__ == "__main__":
    unittest.main()
