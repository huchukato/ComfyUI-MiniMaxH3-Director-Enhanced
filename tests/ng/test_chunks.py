import unittest

from _pack import module

chunks = module("ng.core.chunks")
frames = module("ng.core.frames")
limits = module("ng.core.limits")
shots = module("ng.core.shots")
issues = module("ng.core.issues")

VIDEO = chunks.ContinuityPlan("video_audio", 22, 24)
NONE = chunks.ContinuityPlan("none")


def codes(plan):
    return [i.code for i in plan.issues]


class Lengths(unittest.TestCase):
    def test_single_chunk_snaps_to_grid(self):
        plan = chunks.plan_chunks(240, 240, VIDEO)
        self.assertEqual(len(plan.chunks), 1)
        self.assertEqual(plan.chunks[0].delivered_frames, 243)
        self.assertTrue(frames.on_grid(plan.chunks[0].sampled_frames))
        self.assertIn("length_snapped", codes(plan))

    def test_exact_grid_length_has_no_issue(self):
        plan = chunks.plan_chunks(243, 243, VIDEO)
        self.assertEqual(plan.total_frames, 243)
        self.assertEqual(plan.issues, ())

    def test_sixty_seconds_in_ten_second_chunks(self):
        plan = chunks.plan_chunks(1440, 240, VIDEO)
        self.assertEqual(len(plan.chunks), 6)
        self.assertLessEqual(abs(plan.total_frames - 1440), 8)
        for c in plan.chunks:
            self.assertTrue(frames.on_grid(c.sampled_frames), c)
            self.assertTrue(limits.SAMPLED_MIN_FRAMES <= c.sampled_frames <= limits.SAMPLED_MAX_FRAMES, c)
        self.assertEqual([c.head_frames for c in plan.chunks], [0, 22, 22, 22, 22, 22])
        self.assertEqual([c.story_start_f for c in plan.chunks][1:], [sum(c.delivered_frames for c in plan.chunks[:i]) for i in range(1, 6)])
        self.assertTrue(plan.chunks[-1].is_last and not plan.chunks[0].is_last)

    def test_target_longer_than_the_model_allows_is_capped(self):
        plan = chunks.plan_chunks(1000, 100000, VIDEO)
        self.assertTrue(all(c.sampled_frames <= limits.SAMPLED_MAX_FRAMES for c in plan.chunks))
        self.assertGreaterEqual(len(plan.chunks), 3)

    def test_project_shorter_than_the_minimum(self):
        plan = chunks.plan_chunks(24, 240, VIDEO)
        self.assertEqual(len(plan.chunks), 1)
        self.assertGreaterEqual(plan.chunks[0].sampled_frames, limits.SAMPLED_MIN_FRAMES)
        self.assertIn("length_snapped", codes(plan))

    def test_continuity_modes_change_the_grid(self):
        for mode, head in ((NONE, 0), (chunks.ContinuityPlan("video", 5, 24), 5), (chunks.ContinuityPlan("video", 39, 24), 39)):
            plan = chunks.plan_chunks(900, 200, mode)
            self.assertEqual(plan.chunks[1].head_frames, head)
            for c in plan.chunks:
                self.assertTrue(frames.on_grid(c.sampled_frames), (mode.mode, c))

    def test_every_pin_window_and_many_lengths_stay_on_grid(self):
        for window in limits.PIN_VIDEO_WINDOWS:
            for total in range(100, 2000, 37):
                plan = chunks.plan_chunks(total, 200, chunks.ContinuityPlan("video", window, 24))
                self.assertTrue(all(frames.on_grid(c.sampled_frames) for c in plan.chunks), (window, total))
                self.assertLessEqual(abs(plan.total_frames - total), 17, (window, total))

    def test_warnings(self):
        self.assertIn("no_continuity", codes(chunks.plan_chunks(900, 200, NONE)))
        self.assertIn("audio_dulling", codes(chunks.plan_chunks(1440, 240, VIDEO)))
        self.assertNotIn("audio_dulling", codes(chunks.plan_chunks(480, 240, VIDEO)))
        self.assertNotIn("no_continuity", codes(chunks.plan_chunks(200, 240, NONE)))

    @staticmethod
    def story_with_a_change_at(frame):
        text = "0-%s: a\n%s-40: b" % (frame / 24.0 - 0.5, frame / 24.0)
        return shots.parse_shots(text, 900)[0]

    def test_shot_change_right_after_a_join_is_flagged(self):
        plain = chunks.plan_chunks(900, 240, VIDEO)                    # no shots, so the boundaries are not moved
        boundary = plain.chunks[1].story_start_f
        near = self.story_with_a_change_at(boundary + 24)
        self.assertEqual([i.code for i in chunks._late_changes(near, plain.chunks)], ["late_change"])
        far = self.story_with_a_change_at(boundary + 120)
        self.assertEqual(chunks._late_changes(far, plain.chunks), [])

    def test_the_planner_fixes_what_it_can_instead_of_warning(self):
        boundary = chunks.plan_chunks(900, 240, VIDEO).chunks[1].story_start_f
        near = self.story_with_a_change_at(boundary + 24)
        self.assertNotIn("late_change", codes(chunks.plan_chunks(900, 240, VIDEO, near)))
        self.assertNotIn("late_change", codes(chunks.plan_chunks(900, 240, NONE, near)))

    def test_rejects_empty_project(self):
        with self.assertRaises(ValueError):
            chunks.plan_chunks(0, 240, VIDEO)


class ShotMapping(unittest.TestCase):
    def plan(self):
        story, _ = shots.parse_shots("0-8: one\n8-22: two\n22-30: three", 30 * 24)
        return chunks.plan_chunks(30 * 24, 240, VIDEO, story), story

    def test_every_shot_frame_lands_in_exactly_one_delivered_part(self):
        plan, story = self.plan()
        covered = {s.index: 0 for s in story}
        for c in plan.chunks:
            for cs in c.shots:
                start = max(cs.local_start_f, c.head_frames)
                covered[cs.shot_index] += cs.local_end_f - start
        for s in story:
            expected = min(s.end_f, plan.total_frames) - s.start_f
            self.assertEqual(covered[s.index], expected, s)

    def test_flags_and_head_offset(self):
        plan, _ = self.plan()
        first, second = plan.chunks[0], plan.chunks[1]
        self.assertEqual(first.shots[0].local_start_f, 0)
        two_in_first = [s for s in first.shots if s.shot_index == 2][0]
        self.assertTrue(two_in_first.continues and not two_in_first.carried)
        two_in_second = [s for s in second.shots if s.shot_index == 2][0]
        self.assertTrue(two_in_second.carried)
        self.assertEqual(two_in_second.local_start_f, 0)        # shot 2 was already running in the pinned head
        one_in_second = [s for s in second.shots if s.shot_index == 1]
        self.assertEqual(one_in_second, [])                     # shot 1 ended before the pinned head begins

    def test_no_shots_gives_empty_lists(self):
        plan = chunks.plan_chunks(480, 240, VIDEO, ())
        self.assertTrue(all(c.shots == () for c in plan.chunks))


class Persistence(unittest.TestCase):
    def test_plan_roundtrip(self):
        story, _ = shots.parse_shots("0-8: one\n8-20: two", 20 * 24)
        plan = chunks.plan_chunks(480, 240, VIDEO, story)
        self.assertEqual(chunks.SequencePlan.from_dict(plan.to_dict()), plan)

    def test_continuity_validation(self):
        with self.assertRaises(issues.SchemaError):
            chunks.ContinuityPlan.from_dict({"schema_version": 1, "video_frames": 30})
        with self.assertRaises(issues.SchemaError):
            chunks.ContinuityPlan.from_dict({"schema_version": 1, "mode": "magic"})
        self.assertEqual(chunks.ContinuityPlan.from_dict(VIDEO.to_dict()), VIDEO)


if __name__ == "__main__":
    unittest.main()
