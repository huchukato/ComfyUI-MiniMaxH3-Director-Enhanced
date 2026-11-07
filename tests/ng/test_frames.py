import unittest

from _pack import module

frames = module("ng.core.frames")
limits = module("ng.core.limits")


class Grid(unittest.TestCase):
    def test_on_grid(self):
        self.assertTrue(all(frames.on_grid(n) for n in (5, 22, 39, 56, 124, 192, 345)))
        self.assertFalse(any(frames.on_grid(n) for n in (0, 4, 6, 21, 100, 361)))

    def test_snap_up_and_down(self):
        self.assertEqual(frames.snap_up(1), 5)
        self.assertEqual(frames.snap_up(5), 5)
        self.assertEqual(frames.snap_up(6), 22)
        self.assertEqual(frames.snap_up(120), 124)
        self.assertEqual(frames.snap_down(123), 107)
        self.assertEqual(frames.snap_down(124), 124)
        self.assertEqual(frames.snap_down(3), 5)

    def test_snap_matches_core_align(self):
        # the Core's own align_frame_count is "while n % 17 != 5: n += 1"
        for n in range(5, 400):
            m = n
            while m % 17 != 5:
                m += 1
            self.assertEqual(frames.snap_up(n), m)

    def test_nearest(self):
        self.assertEqual(frames.snap_nearest(115), 107)
        self.assertEqual(frames.snap_nearest(116), 124)

    def test_seconds_frames_roundtrip(self):
        self.assertEqual(frames.seconds_to_frames(8), 192)
        self.assertAlmostEqual(frames.frames_to_seconds(192), 8.0)


class ContinuedChunks(unittest.TestCase):
    def test_residue_for_pin_windows(self):
        # 5, 22, 39, 56 are all 17m + 5, so a continued chunk delivers multiples of 17
        for head in limits.PIN_VIDEO_WINDOWS:
            self.assertEqual(frames.delivered_residue(head), 0)
        self.assertEqual(frames.delivered_residue(1), 4)   # last-frame anchor, one duplicated frame
        self.assertEqual(frames.delivered_residue(0), 5)   # no continuity: delivered is on the grid itself

    def test_sampled_is_on_grid(self):
        for head in (0, 1, 5, 22, 39, 56):
            for delivered in frames.delivered_candidates(150, head, 20, 400):
                self.assertTrue(frames.on_grid(delivered + head), (head, delivered))

    def test_candidates_nearest_first(self):
        cands = frames.delivered_candidates(240, 22, 96, 340)
        self.assertEqual(cands[0], 238)       # 14 * 17
        self.assertIn(255, cands)


if __name__ == "__main__":
    unittest.main()
