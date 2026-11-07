"""BUG-024: die Wellenform-Ansicht rechnet stream.duration mit stream.time_base, ohne zu
pruefen, ob time_base gesetzt ist. Manche Container (raw PCM, manche WAV-Varianten) haben
kein time_base an der Spur; container.duration ist dann der einzige Weg.
Kein Fix, nur Beleg.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import module  # noqa: E402

waveform = module("ng.adapters.waveform")


class FakeLayout:
    channels = (0, 1)          # av exposes channels as a sequence


class FakeStream:
    def __init__(self, duration, time_base):
        self.duration = duration
        self.time_base = time_base
        self.codec_context = type("Codec", (), {"sample_rate": 48000, "layout": FakeLayout})()


class FakeContainer:
    def __init__(self, stream, container_duration):
        self.streams = type("Streams", (), {"audio": [stream]})()
        self.duration = container_duration

    def decode(self, stream):
        return iter(())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def run_with(stream, container_duration):
    with patch.object(waveform.av, "open", lambda _p: FakeContainer(stream, container_duration)), \
            patch.object(waveform, "require_path", lambda _s: "irrelevant"):
        return waveform.envelope("song.wav")


class WaveformDuration(unittest.TestCase):
    def test_control_a_normal_mp4_reads_its_duration(self):
        result = run_with(FakeStream(48000 * 10, 1 / 48000), None)
        self.assertAlmostEqual(result["duration_s"], 10.0, places=3)

    def test_bug_024_a_stream_without_time_base_crashes_the_waveform(self):
        stream = FakeStream(48000 * 10, None)
        self.assertIsNone(stream.time_base,
                          "this test needs a stream whose time_base is None")
        result = run_with(stream, 10 * av_time_base())
        self.assertGreater(result["duration_s"], 0,
                           "the panel must still show a duration when the stream has no time_base")

    def test_control_container_duration_is_used_when_the_stream_has_none(self):
        import av
        result = run_with(FakeStream(None, 1 / 48000), 10 * av.time_base)
        self.assertAlmostEqual(result["duration_s"], 10.0, places=3)


def av_time_base():
    import av
    return av.time_base


if __name__ == "__main__":
    unittest.main()