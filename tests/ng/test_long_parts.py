"""A small canvas allows longer render parts (frames x area, up to 30 s): one 30 s clip at 640x352 held without drift, with
motion and references; from 45 s on H3 repeated lines (comparison 2026-10-20/21, M13, M19). 1280x704 keeps the trained maximum."""
import json
import unittest

from _pack import module

ctx, project, chunks, limits = module("ng.core.context"), module("ng.core.project"), module("ng.core.chunks"), module("ng.core.limits")


def plan(seconds, size, part_seconds):
    shots = [{"id": "a", "start": 0, "end": seconds, "text": "A baker kneads dough. The camera holds a static shot.", "media": []}]
    context = ctx.DirectorContext(shots_text=json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": shots}),
                                  project_seconds=seconds, width=size[0], height=size[1], music="N/A", soundscape="Quiet.")
    return project.plan_project(context, part_seconds, chunks.ContinuityPlan("video_audio"))


class LongParts(unittest.TestCase):
    def test_the_longest_clip_follows_the_picture_area(self):
        self.assertEqual(limits.max_frames(1280, 704), limits.SAMPLED_MAX_FRAMES)
        self.assertEqual(limits.max_frames(768, 1152), limits.SAMPLED_MAX_FRAMES, "close to 1280x704: unchanged")
        self.assertEqual(limits.max_frames(640, 352), limits.LONG_PART_FRAMES)
        self.assertTrue(limits.SAMPLED_MAX_FRAMES < limits.max_frames(960, 544) < limits.LONG_PART_FRAMES)

    def test_thirty_second_parts_at_a_small_size(self):
        small = plan(58, (640, 352), 30)           # a continued part carries its 22 pinned frames inside the 30 s
        self.assertEqual(len(small.plan.chunks), 2)
        self.assertTrue(all(c.sampled_frames <= limits.LONG_PART_FRAMES for c in small.plan.chunks))
        self.assertNotIn("part_capped", [i.code for i in small.issues])

    def test_a_large_size_keeps_its_parts_and_says_so(self):
        large = plan(60, (1280, 704), 30)
        self.assertTrue(all(c.sampled_frames <= limits.SAMPLED_MAX_FRAMES for c in large.plan.chunks))
        self.assertIn("part_capped", [i.code for i in large.issues])
        self.assertEqual([c.delivered_frames for c in plan(60, (1280, 704), 10).plan.chunks],
                         [c.delivered_frames for c in plan(60, (1280, 704), 0).plan.chunks])


if __name__ == "__main__":
    unittest.main()
