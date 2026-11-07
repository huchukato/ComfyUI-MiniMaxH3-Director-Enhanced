import unittest

from _pack import module

pin = module("ng.core.pin")
limits = module("ng.core.limits")


class VideoSteps(unittest.TestCase):
    def test_windows_are_whole_steps(self):
        self.assertEqual([pin.steps_for_frames(n) for n in (1, 5, 22, 39, 56)], [1, 2, 7, 12, 17])
        self.assertIsNone(pin.steps_for_frames(6))
        self.assertIsNone(pin.steps_for_frames(23))

    def test_pixel_frames_and_offsets(self):
        self.assertEqual([pin.pixel_frames(n) for n in (2, 7, 12, 17)], [5, 22, 39, 56])
        self.assertEqual(pin.step_offsets(7), [0, 1, 5, 9, 13, 17, 18])

    def test_tail_always_starts_on_a_cycle_for_grid_clips(self):
        for clip_frames in (124, 107, 192, 243, 345):
            clip_steps = ((clip_frames - 5) // 17) * 5 + 2
            for window in limits.PIN_VIDEO_WINDOWS:
                found = pin.video_pin(window, clip_steps)
                self.assertEqual(found.start_step % 5, 0)
                self.assertEqual(found.span, window)

    def test_refuses_off_grid_requests(self):
        with self.assertRaises(ValueError):
            pin.video_pin(30, 30)
        with self.assertRaises(ValueError):
            pin.video_pin(56, 12)
        with self.assertRaises(ValueError):
            pin.video_pin(22, 8)       # 8 steps is not a 17k+5 clip


class AudioPinning(unittest.TestCase):
    def audio_steps(self, frames):
        return round(frames / 24.0 * 40)

    def test_overhang_is_zero_or_a_third(self):
        seen = set()
        for frames in (124, 107, 192, 243, 345, 260, 124 + 17 * 3):
            video = ((frames - 5) // 17) * 5 + 2
            seen.add(round(pin.audio_overhang(self.audio_steps(frames), video), 3))
        self.assertTrue(seen <= {0.0, 0.333, -0.333}, seen)

    def test_window_ends_on_the_target_grid_at_the_join(self):
        for frames in (124, 107, 192, 243, 345):
            video = ((frames - 5) // 17) * 5 + 2
            found = pin.audio_pin(24, self.audio_steps(frames), video, head_frames=22)
            self.assertEqual(found.steps, 40)
            self.assertAlmostEqual(found.index * pin.FRAME_RESCALE + found.steps, found.end_coord, places=9)
            self.assertAlmostEqual(found.end_coord, 22 * pin.FRAME_RESCALE, delta=1)     # within one step of the pinned head's end
            self.assertLess(found.index, 0)

    def test_measured_window_length(self):
        self.assertEqual(pin.audio_pin(24, 300, 52, 22).steps, 40)      # 24 frames = exactly one second
        self.assertEqual(pin.audio_pin(48, 300, 52, 22).steps, 80)

    def test_never_asks_for_more_than_exists(self):
        self.assertEqual(pin.audio_pin(240, 30, 12, 22).steps, 30)


if __name__ == "__main__":
    unittest.main()
