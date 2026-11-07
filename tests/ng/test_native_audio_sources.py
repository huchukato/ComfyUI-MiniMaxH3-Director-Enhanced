"""Audio references retain native samples and rate until H3's own audio encoder resamples them."""
import os
import tempfile
import unittest
import wave
from unittest import mock

from _pack import comfy_available, module, stub_prompt_server


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class NativeAudioSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stub_prompt_server()
        cls.media = module("ng.adapters.media")
        cls.ref = module("ng.core.media_ref").MediaRef

    def test_source_rate_channels_and_sample_accurate_trim_are_preserved(self):
        import numpy as np
        import torch
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "sound.wav")
            for rate, channels in ((32000, 2), (48000, 1)):
                raw = (np.sin(np.arange(rate) * .05) * 28000).astype(np.int16)
                pcm = np.repeat(raw[:, None], channels, axis=1)
                with wave.open(path, "wb") as output:
                    output.setnchannels(channels)
                    output.setsampwidth(2)
                    output.setframerate(rate)
                    output.writeframes(pcm.tobytes())
                expected = torch.from_numpy(pcm[rate // 4:rate * 3 // 4].T.copy()).float() / 32768
                with self.subTest(rate=rate, channels=channels), mock.patch.object(self.media, "input_path", return_value=path):
                    result = self.media.load_audio(self.ref("audio", "sound", "sound.wav", trim_start_f=6, length_f=12))
                    self.assertEqual(result["sample_rate"], rate)
                    self.assertTrue(torch.equal(result["waveform"], expected.unsqueeze(0)))

    def test_empty_selected_audio_is_named_instead_of_becoming_silence(self):
        import torch
        with mock.patch.object(self.media, "input_path", return_value="exists"), \
                mock.patch.object(self.media.native_audio, "load", return_value=(torch.zeros(2, 32000), 32000)):
            with self.assertRaisesRegex(self.media.MediaError, "sound.*empty"):
                self.media.load_audio(self.ref("audio", "sound", "sound.wav", trim_start_f=48, length_f=24))

    def test_44100_hz_half_sample_boundaries_match_native_audio_trim(self):
        import torch
        wave = torch.arange(44100 * 11).repeat(2, 1).float()
        with mock.patch.object(self.media, "input_path", return_value="exists"), \
                mock.patch.object(self.media.native_audio, "load", return_value=(wave, 44100)):
            result = self.media.load_audio(self.ref("audio", "song", "song.mp3", trim_start_f=141, length_f=102))
        start = round(5.875 * 44100)
        count = round(4.25 * 44100)
        self.assertTrue(torch.equal(result["waveform"], wave[:, start:start + count].unsqueeze(0)))
