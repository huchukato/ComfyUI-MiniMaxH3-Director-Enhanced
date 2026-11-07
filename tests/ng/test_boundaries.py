import unittest

from _pack import module

boundaries = module("ng.core.boundaries")
chunks = module("ng.core.chunks")
frames = module("ng.core.frames")
limits = module("ng.core.limits")
shots = module("ng.core.shots")

VIDEO = chunks.ContinuityPlan("video_audio", 22, 24)


def parse(text, seconds):
    return shots.parse_shots(text, round(seconds * 24))[0]


class Align(unittest.TestCase):
    def test_a_shot_just_after_a_boundary_moves_the_boundary_earlier(self):
        story = parse("0-12: a\n12-30: b", 30)                    # shot b starts at frame 288, 45 frames after the first boundary (243)
        plan = chunks.plan_chunks(720, 240, VIDEO, story)
        self.assertEqual(plan.chunks[0].delivered_frames, 226)    # 243 - 17
        self.assertGreaterEqual(288 - plan.chunks[1].story_start_f, limits.LATE_CHANGE_FRAMES)
        self.assertNotIn("late_change", [i.code for i in plan.issues])

    def test_a_shot_in_a_parts_last_two_seconds_moves_the_boundary(self):
        # Ref2VA minute 2026-10-20: shot 2 at 20.0 s, part edge at 20.04 s -> H3 cut at 18.38 s and the next part cut again
        story = parse("0-20: a\n20-40: b", 40)
        plan = chunks.plan_chunks(960, 240, VIDEO, story)
        for chunk in plan.chunks[:-1]:
            offset = 480 - chunk.story_end_f
            self.assertFalse(-boundaries.END_LEAD < offset < limits.LATE_CHANGE_FRAMES, [c.story_end_f for c in plan.chunks])
        self.assertEqual(plan.total_frames, chunks.plan_chunks(960, 240, VIDEO).total_frames)

    def test_total_length_and_the_grid_do_not_change(self):
        story = parse("0-12: a\n12-24: b\n24-30: c", 30)
        plain = chunks.plan_chunks(720, 240, VIDEO)
        aligned = chunks.plan_chunks(720, 240, VIDEO, story)
        self.assertEqual(aligned.total_frames, plain.total_frames)
        for chunk in aligned.chunks:
            self.assertTrue(frames.on_grid(chunk.sampled_frames), chunk)
            low, high = limits.SAMPLED_MIN_FRAMES, limits.SAMPLED_MAX_FRAMES
            self.assertTrue(low <= chunk.sampled_frames <= high, chunk)

    def test_boundaries_that_are_fine_stay(self):
        story = parse("0-5: a\n5-30: b", 30)                     # the change is far from every boundary
        self.assertEqual([c.delivered_frames for c in chunks.plan_chunks(720, 240, VIDEO, story).chunks],
                         [c.delivered_frames for c in chunks.plan_chunks(720, 240, VIDEO).chunks])

    def test_a_shot_right_after_the_boundary_can_also_be_pulled_into_the_earlier_chunk(self):
        shift = boundaries._candidates(243, 250)
        self.assertEqual(sorted(shift, key=abs)[0], shift[0])
        self.assertIn(-68, shift)
        self.assertIn(68, shift)

    def test_infeasible_shifts_are_skipped(self):
        # chunk lengths at their minimum cannot give up frames
        low_first = frames.delivered_bounds(0)[0]
        low_first = frames.snap_up(low_first)
        low_next = (frames.delivered_bounds(22)[0] // 17 + 1) * 17
        lengths = [low_first, low_next, 300]
        start = low_first + 20
        out = boundaries.align_to_shots(lengths, 22, parse("0-%s: a\n%s-30: b" % (start / 24.0, start / 24.0), 40))
        self.assertEqual(sum(out), sum(lengths))
        self.assertGreaterEqual(out[0], low_first)

    def test_no_shots_or_no_continuity_leaves_lengths_alone(self):
        self.assertEqual(boundaries.align_to_shots([243, 238], 22, ()), [243, 238])
        story = parse("0-12: a\n12-30: b", 30)
        none = chunks.plan_chunks(720, 240, chunks.ContinuityPlan("none"), story)
        self.assertEqual(none.chunks[0].delivered_frames, 243)


if __name__ == "__main__":
    unittest.main()
