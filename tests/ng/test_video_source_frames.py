"""Actual lossless media: timestamps, source-end selection and reference EOF resampling."""
from fractions import Fraction
import os
import tempfile
import unittest
from unittest import mock

from _pack import module, comfy_available, stub_prompt_server


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class VideoFrames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stub_prompt_server()
        cls.media = module("minimax_media")
        cls.end = module("ng.adapters.video_end")

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def fixture(self, fps=24, offset=0, times=None):
        import av
        import numpy as np
        path = os.path.join(self.folder.name, "source.mkv")
        with av.open(path, "w") as output:
            stream = output.add_stream("ffv1", rate=fps)
            stream.width, stream.height, stream.pix_fmt = 64, 96, "bgr0"
            stream.time_base = stream.codec_context.time_base = Fraction(1, 60000)
            for index, time in enumerate(times if times is not None else [i / fps for i in range(fps)]):
                rgb = np.zeros((96, 64, 3), dtype=np.uint8)
                rgb[:] = [index, index * 3, 80]
                frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
                frame.pts, frame.time_base = round((offset + time) * 60000), Fraction(1, 60000)
                for packet in stream.encode(frame):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
        return path

    def index(self, images):
        return round(float(images[-1, 0, 0, 0]) * 255)

    def test_reference_timestamps_are_relative_to_the_video_start(self):
        path = self.fixture(offset=2)
        probe = module("ng.adapters.probe")
        with mock.patch.object(probe, "input_path", return_value=path):
            self.assertAlmostEqual(probe.duration_seconds("source.mkv"), 1, places=2)
        with mock.patch.object(self.media, "resolve_input_path", return_value=path):
            frames = self.media.load_video_tensor("source.mkv", 0, 1, strict=True)
        self.assertEqual([round(float(frames[i, 0, 0, 0]) * 255) for i in (0, 12, 23)], [0, 12, 23])

    def test_eof_holds_the_actual_last_frame_not_the_previous_resampling_target(self):
        path = self.fixture()
        with mock.patch.object(self.media, "resolve_input_path", return_value=path):
            frames = self.media.load_video_tensor("source.mkv", 0, 1.25, strict=True)
        self.assertEqual(frames.shape[0], 30)
        self.assertEqual(self.index(frames[23:]), 23)
        self.assertEqual(self.index(frames[:24]), 23)

    def test_continuation_preserves_the_true_endpoint_at_all_source_rates(self):
        for fps in (24, 30, 60):
            path = self.fixture(fps)
            with self.subTest(fps=fps), mock.patch.object(self.end, "input_path", return_value=path):
                self.assertEqual(self.index(self.end.tail_frames("source.mkv", 0, 1, 1)), fps - 1)
                self.assertEqual(self.index(self.end.tail_frames("source.mkv", .2, .5, 1)), fps // 2 - 1)

    def test_continuation_clip_keeps_its_size_and_true_last_frame_at_all_rates(self):
        for fps in (24,30,60):
            path = self.fixture(fps,offset=2)
            with self.subTest(fps=fps),mock.patch.object(self.end,'input_path',return_value=path):
                tail = self.end.tail_frames('source.mkv',0,1,22)
                self.assertEqual(tail.shape[0],22)
                self.assertEqual(self.index(tail),fps-1)
                self.assertEqual(self.index(self.end.tail_frames('source.mkv',0,0,22)),fps-1)
                chosen = self.end.tail_frames('source.mkv',.2,.5,5)
                self.assertEqual(self.index(chosen),fps//2-1)

    def test_variable_rate_clip_holds_frames_and_keeps_endpoint(self):
        path = self.fixture(offset=2,times=[0,.04,.12,.38,.49,.72])
        with mock.patch.object(self.end,'input_path',return_value=path):
            tail = self.end.tail_frames('source.mkv',.3,.5,5)
            self.assertEqual(tail.shape[0],5)
            self.assertEqual(self.index(tail),4)

    def test_continuation_normalizes_pts_and_does_not_round_a_variable_rate_endpoint(self):
        path = self.fixture(offset=2, times=[0, .04, .12, .38, .49, .72])
        with mock.patch.object(self.end, "input_path", return_value=path):
            self.assertEqual(self.index(self.end.tail_frames("source.mkv", .3, .5, 1)), 4)
            self.assertEqual(self.index(self.end.tail_frames("source.mkv", 0, 0, 1)), 5)
            with self.assertRaisesRegex(ValueError, "selected range"):
                self.end.tail_frames("source.mkv", .51, .6, 1)

    def test_h264_references_keep_the_native_float_colours(self):
        import av
        import numpy as np
        import torch
        from comfy_api.latest._input_impl.video_types import VideoFromFile
        for width, height, rotation in ((64, 96, 0), (66, 94, 90)):
            path = os.path.join(self.folder.name, "colour.mp4")
            with av.open(path, "w") as output:
                stream = output.add_stream("libx264", rate=24)
                stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
                stream.set_display_rotation(rotation)
                for index in range(4):
                    rgb = np.indices((height, width)).sum(axis=0).astype(np.uint8)
                    rgb = np.stack([rgb, np.roll(rgb, 5, axis=1), 200 - rgb], axis=-1)
                    for packet in stream.encode(av.VideoFrame.from_ndarray(rgb, format="rgb24")):
                        output.mux(packet)
                for packet in stream.encode():
                    output.mux(packet)
            native = VideoFromFile(path).get_components().images
            with mock.patch.object(self.media, "resolve_input_path", return_value=path):
                actual = self.media.load_video_tensor("colour.mp4", 0, 4 / 24, strict=True)
            with self.subTest(width=width, rotation=rotation):
                self.assertTrue(torch.equal(native, actual), "reference colours, edge alignment and rotation must match native")
