"""Decode real local MKV previews without a stream duration; keep the sampling window bounded."""
from fractions import Fraction
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import av
import numpy as np
from PIL import Image

from _pack import module

preview = module("ng.adapters.preview_media")


def make_video(path, seconds):
    with av.open(str(path), "w") as container:
        stream = container.add_stream("ffv1", rate=5)
        stream.width = stream.height = 32
        stream.pix_fmt = "yuv420p"
        for number in range(seconds * 5):
            rgb = np.full((32, 32, 3), number * 2, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            frame.pts = number
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


class VideoImages(unittest.TestCase):
    def check_real(self, seconds, expected):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preview.mkv"
            make_video(path, seconds)
            actual = av.open(str(path))
            seeks = []
            self.assertIsNone(actual.streams.video[0].duration)
            self.assertEqual(actual.duration / av.time_base, seconds)

            class Container:
                streams, duration = actual.streams, actual.duration

                def seek(self, timestamp, **kwargs):
                    seeks.append(timestamp / av.time_base)
                    actual.seek(timestamp, **kwargs)

                def decode(self, stream):
                    return actual.decode(stream)

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    actual.close()

            with patch.object(preview, "require_path", return_value=str(path)), patch.object(preview.av, "open", return_value=Container()):
                images = preview.video_images("preview.mkv")
            self.assertEqual(seeks, expected)
            self.assertEqual(len(images), 3)
            self.assertEqual(len(set(images)), 3, "the three real JPEGs must depict different times")

    def test_real_mkv_missing_stream_duration_samples_across_container(self):
        self.check_real(10, [0.0, 5.0, 9.8])

    def test_real_long_mkv_keeps_fifteen_second_limit(self):
        self.check_real(20, [0.0, 7.5, 14.8])

    def test_metadata_fallbacks_are_nonnegative_and_keep_stream_priority(self):
        cases = ((240, Fraction(1, 24), 30, [0, 5, 9.8]),
                 (None, None, 10, [0, 5, 9.8]), (None, None, None, [0, 0, 0]),
                 (None, None, -1, [0, 0, 0]), (None, Fraction(1, 24), 30, [0, 7.5, 14.8]))
        for duration, time_base, seconds, expected in cases:
            with self.subTest(duration=duration, time_base=time_base, seconds=seconds):
                stream = SimpleNamespace(duration=duration, time_base=time_base)
                seeks = []
                frame = SimpleNamespace(time=None, to_image=lambda: Image.new("RGB", (16, 16)))
                container = SimpleNamespace(streams=SimpleNamespace(video=[stream]), duration=None if seconds is None else seconds * av.time_base)
                with patch.object(preview, "require_path", return_value="metadata"), patch.object(preview.av, "open") as opened:
                    opened.return_value.__enter__.return_value = container
                    container.seek = lambda timestamp, **kwargs: seeks.append(timestamp)
                    container.decode = lambda stream: iter([frame])
                    self.assertEqual(len(preview.video_images("metadata")), 3)
                self.assertEqual(seeks, [int(time * av.time_base) for time in expected])


if __name__ == "__main__":
    unittest.main()
