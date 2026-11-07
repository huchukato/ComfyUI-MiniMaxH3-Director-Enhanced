"""BUG-060 Regression Test: preview_media.video_images crash on time_base=None and 0s collapse on stream.duration=None.

In ng.adapters.preview_media.video_images:
    stream = container.streams.video[0]
    duration = (stream.duration or 0) * float(stream.time_base)

When a video container (such as MKV, WebM, or certain MP4 files without stream duration headers):
1. Has stream.time_base as None:
   float(stream.time_base) raises TypeError: float() argument must be a string or a real number, not 'NoneType'.
2. Has stream.duration as None:
   (stream.duration or 0) evaluates to 0, causing duration = 0.0 and end = 0.0.
   The loop for seconds in (0.0, end / 2, max(0.0, end - 0.2)) evaluates to (0.0, 0.0, 0.0),
   causing all 3 stills extracted for the Vision AI model to be sampled at timestamp 0.0s (the same opening frame),
   even though container.duration is valid (e.g. 10.0 seconds).

Proper fallback (consistent with ng.adapters.waveform:13 and ng.adapters.probe:17):
    duration = (float(stream.duration * stream.time_base)
                if stream.duration and stream.time_base
                else float(container.duration or 0) / float(av.time_base))
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import av
import PIL.Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module  # noqa: E402

preview_media = module("ng.adapters.preview_media")


class FakeStream:
    def __init__(self, duration, time_base):
        self.duration = duration
        self.time_base = time_base


class FakeContainer:
    def __init__(self, stream, container_duration):
        self.streams = MagicMock()
        self.streams.video = [stream]
        self.duration = container_duration
        self.seeks = []
        self.current_time = 0.0

    def seek(self, ts, **kwargs):
        self.seeks.append(ts)
        self.current_time = float(ts) / float(av.time_base)

    def decode(self, stream):
        frame = MagicMock()
        frame.time = self.current_time
        frame.to_image.return_value = PIL.Image.new("RGB", (64, 64), color="blue")
        return [frame]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def run_with(stream, container_duration):
    container = FakeContainer(stream, container_duration)
    with patch.object(preview_media.av, "open", return_value=container), \
            patch.object(preview_media, "require_path", return_value="dummy.mp4"):
        images = preview_media.video_images("dummy.mp4")
        return container, images


class VideoImagesDuration(unittest.TestCase):
    def test_control_normal_stream_duration_is_used(self):
        """Green control: video with valid stream.duration and stream.time_base samples across the video."""
        stream = FakeStream(240, 1 / 24)  # 240 frames at 24fps = 10.0s
        container, images = run_with(stream, int(10.0 * av.time_base))
        self.assertEqual(len(images), 3)
        expected_seeks = [0, int(5.0 * av.time_base), int(9.8 * av.time_base)]
        self.assertEqual(container.seeks, expected_seeks,
                         "Normal stream must seek to start (0.0s), midpoint (5.0s), and near-end (9.8s)")

    def test_bug_060_video_images_without_time_base_must_not_crash(self):
        """BUG-060: when stream.time_base is None, video_images must fall back to container.duration instead of raising TypeError."""
        stream = FakeStream(240, None)
        self.assertIsNone(stream.time_base, "this test requires a stream whose time_base is None")
        container, images = run_with(stream, int(10.0 * av.time_base))
        self.assertEqual(len(images), 3)
        expected_seeks = [0, int(5.0 * av.time_base), int(9.8 * av.time_base)]
        self.assertEqual(container.seeks, expected_seeks)

    def test_bug_060_video_images_without_stream_duration_uses_container_duration(self):
        """BUG-060: when stream.duration is None, video_images must use container.duration instead of collapsing to 0.0s."""
        stream = FakeStream(None, 1 / 24)
        self.assertIsNone(stream.duration, "this test requires a stream whose duration is None")
        container, images = run_with(stream, int(10.0 * av.time_base))
        self.assertEqual(len(images), 3)
        expected_seeks = [0, int(5.0 * av.time_base), int(9.8 * av.time_base)]
        self.assertEqual(container.seeks, expected_seeks,
                         "A video missing stream.duration must use container.duration to sample frames across the video, "
                         "not collapse all 3 samples to [0, 0, 0]")


if __name__ == "__main__":
    unittest.main()
