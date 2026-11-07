"""Continuation guides stay inside the selected source interval, even shorter than one second."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from _pack import comfy_available, load_full_pack, module

ctx = module("ng.core.context")
opts = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def continued(start, end, duration=5):
    video = ctx.ContextItem("continue", "Continue", "video", "window.mp4", usage=("continue",), length_s=duration,
                            options=opts.ContextOptions(start_s=start, end_s=end))
    director = ctx.DirectorContext(idea="Continue the camera.", items=(video,), project_seconds=8)
    return project.plan_project(director, 5, chunks.ContinuityPlan("video_audio"))


class ContinueWindow(unittest.TestCase):
    def test_continuation_stays_inside_short_and_long_source_windows(self):
        for start, end, expected in ((2, 2.25, (49, 5)), (2, 2.125, (50, 1)), (2, 2.0416666667, (48, 1)),
                                     (2, 4, (57, 39)), (2, 0, (81, 39))):
            with self.subTest(start=start, end=end):
                result = continued(start, end)
                guide = result.compiled[0].of_kind("continue_video")[0]
                self.assertEqual((guide.trim_start_f, guide.length_f), expected)
                self.assertEqual(result.compiled[1].of_kind("continue_video"), (), "only the first chunk reads the source guide")


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class ContinueLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib
        pack = load_full_pack().__name__
        cls.media = importlib.import_module(pack + ".ng.adapters.media")
        cls.compile = importlib.import_module(pack + ".ng.core.compile")

    def test_a_single_guide_frame_is_valid_but_a_short_video_reference_is_not(self):
        import torch
        with patch.object(self.media, "input_path", return_value="present.mp4"), \
             patch.object(self.media.legacy, "load_video_tensor", return_value=torch.ones(1, 32, 32, 3)):
            guide = self.compile.MediaRef("continue_video", "v", "present.mp4", length_f=1, trim_start_f=48)
            self.assertEqual(self.media.load_video(guide).shape[0], 1)
            with self.assertRaises(self.media.MediaError):
                self.media.load_video(self.compile.MediaRef("video", "v", "present.mp4", length_f=1))

    def test_a_failed_guide_decode_names_the_context_instead_of_using_a_blank(self):
        with patch.object(self.media, "input_path", return_value="broken.mp4"), \
             patch.object(self.media.legacy, "load_video_tensor", side_effect=ValueError("bad video")) as loader:
            with self.assertRaisesRegex(self.media.MediaError, "Guide.*broken.mp4"):
                self.media.load_video(self.compile.MediaRef("continue_video", "Guide", "broken.mp4", length_f=1))
            self.assertIs(loader.call_args.kwargs["strict"], True)

    def test_real_decode_returns_the_last_selected_frame_for_one_three_and_six_frames(self):
        import av
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frames.mkv"
            with av.open(str(path), "w") as container:
                stream = container.add_stream("ffv1", rate=24)
                stream.width = stream.height = 32
                stream.pix_fmt = "bgr0"
                for index in range(120):
                    pixels = np.zeros((32, 32, 3), dtype=np.uint8)
                    pixels[..., 0] = index
                    for packet in stream.encode(av.VideoFrame.from_ndarray(pixels, format="rgb24")):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            with patch.object(self.media, "input_path", return_value=str(path)), \
                 patch.object(self.media.legacy, "resolve_input_path", return_value=str(path)):
                for end, last in ((2.0416666667, 48), (2.125, 50), (2.25, 53), (4, 95)):
                    guide = continued(2, end).compiled[0].of_kind("continue_video")[0]
                    frames = self.media.load_video(guide)
                    self.assertEqual(round(float(frames[-1, 0, 0, 0]) * 255), last)

    def test_broken_file_keeps_legacy_fallback_but_ng_strict_decode_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broken.mp4"
            path.write_bytes(b"not a video")
            with patch.object(self.media, "input_path", return_value=str(path)), \
                 patch.object(self.media.legacy, "resolve_input_path", return_value=str(path)):
                self.assertEqual(tuple(self.media.legacy.load_video_tensor("broken.mp4", 0, 1).shape), (1, 512, 512, 3))
                with self.assertRaisesRegex(self.media.MediaError, "Guide.*broken.mp4"):
                    self.media.load_video(self.compile.MediaRef("continue_video", "Guide", "broken.mp4", length_f=1))


if __name__ == "__main__":
    unittest.main()
