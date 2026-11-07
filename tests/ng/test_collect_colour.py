"""NG Collect Video writes BT.709 and says so: untagged BT.601 showed green 160 as 143 in the browser (2026-10-20)."""
import os
import tempfile
import unittest
from fractions import Fraction

import av
import torch

from _pack import module

collect = module("ng.adapters.collect")
COLOURS = ((40, 160, 60), (220, 170, 140), (30, 60, 200))


def decode_709(frame):
    """The frame's mean colour as a browser reads a BT.709 limited-range stream."""
    plane = frame.to_ndarray(format="yuv420p")
    h = plane.shape[0] * 2 // 3
    y, u, v = plane[:h].mean(), plane[h:h + h // 4].mean(), plane[h + h // 4:].mean()
    kr, kb = 0.2126, 0.0722
    yy, cb, cr = (y - 16) * 255 / 219, (u - 128) * 255 / 224, (v - 128) * 255 / 224
    r, b = yy + 2 * (1 - kr) * cr, yy + 2 * (1 - kb) * cb
    return r, (yy - kr * r - kb * b) / (1 - kr - kb), b


class Colour(unittest.TestCase):
    def test_colours_survive_a_bt709_reader_and_the_stream_is_tagged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "colour.mp4")
            with av.open(path, "w", format="mp4") as out:
                stream = out.add_stream("libx264", rate=Fraction(24, 1))
                stream.width, stream.height, stream.pix_fmt = 128, 64, "yuv420p"
                collect._bt709(stream.codec_context)
                for colour in COLOURS:
                    image = torch.tensor(colour, dtype=torch.float32).div(255).expand(64, 128, 3)
                    for _ in range(4):
                        out.mux(stream.encode(collect.video_frame(image)))
                out.mux(stream.encode(None))
            with av.open(path) as source:
                stream = source.streams.video[0]
                self.assertEqual(int(stream.codec_context.colorspace), 1)          # BT.709
                self.assertEqual(int(stream.codec_context.color_primaries), 1)
                decoded = [decode_709(f) for n, f in enumerate(source.decode(stream)) if n % 4 == 2]
        for want, got in zip(COLOURS, decoded):
            for a, b in zip(want, got):
                self.assertAlmostEqual(a, b, delta=4, msg=(want, got))


if __name__ == "__main__":
    unittest.main()
