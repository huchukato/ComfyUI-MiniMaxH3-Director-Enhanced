"""Output Lock preserves source samples across native audio-grid boundaries."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from _pack import comfy_available, module, stub_prompt_server

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch


@unittest.skipUnless(HAVE_COMFY, "ComfyUI unavailable")
class LockOutput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stub_prompt_server()
        cls.locks = module("ng.adapters.audio_locks")
        cls.project = module("ng.core.project")
        cls.context = module("ng.core.context")
        cls.chunks = module("ng.core.chunks")
        cls.compile = module("ng.core.compile")

    def test_full_song_is_sample_exact_across_all_chunk_boundaries(self):
        item = self.context.ContextItem("song", "Song", "audio", "song.wav", usage=("lock",), length_s=60)
        plan = self.project.plan_project(self.context.DirectorContext(idea="A walk.", project_seconds=60, items=(item,)),
                                         10, self.chunks.ContinuityPlan("video_audio", 22, 24))
        for rate in (32000, 44100, 48000):
            with self.subTest(rate=rate):
                count = round(plan.plan.total_frames / 24 * rate)
                source = torch.arange(count + rate).float().reshape(1, 1, -1) / (count + rate)
                source = source.expand(1, 2, -1)
                restored = []
                with patch.object(self.locks.media, "load_audio_source", return_value=source):
                    for job in self.project.jobs(plan):
                        first = round(job.chunk.story_start_f / 24 * rate)
                        last = round(job.chunk.story_end_f / 24 * rate)
                        wave = torch.full((1, 2, last - first), -0.5)
                        actual = self.locks.restore_waveform(job, wave, rate)
                        self.assertTrue(torch.equal(actual, source[..., first:last]))
                        restored.append(actual)
                self.assertTrue(torch.equal(torch.cat(restored, dim=-1), source[..., :count]))

    def test_partial_offset_lock_preserves_generated_sound_outside_its_span(self):
        rate = 32000
        refs = (self.compile.MediaRef("lock", "song", "song.wav", start_f=30, length_f=24, trim_start_f=7),)
        job = SimpleNamespace(chunk=SimpleNamespace(story_start_f=243, head_frames=22),
                              compiled=self.compile.CompiledChunk(1, "fl2va", "", refs))
        source = torch.arange(rate * 20).float().reshape(1, 1, -1).expand(1, 2, -1) / (rate * 20)
        wave = torch.full((1, 2, rate * 3), -0.5)
        with patch.object(self.locks.media, "load_audio_source", return_value=source):
            actual = self.locks.restore_waveform(job, wave, rate)
        first = round(251 / 24 * rate) - round(243 / 24 * rate)
        last = round(275 / 24 * rate) - round(243 / 24 * rate)
        source_first = round(251 / 24 * rate) + round((7 - 251) / 24 * rate)
        self.assertTrue(torch.equal(actual[..., :first], wave[..., :first]))
        self.assertTrue(torch.equal(actual[..., last:], wave[..., last:]))
        self.assertTrue(torch.equal(actual[..., first:last], source[..., source_first:source_first + last - first]))
        self.assertTrue(torch.all(wave == -0.5))

    def test_overlapping_locks_mix_and_clip_without_changing_free_sound(self):
        refs = (self.compile.MediaRef("lock", "a", "a.wav", start_f=24, length_f=48),
                self.compile.MediaRef("lock", "b", "b.wav", start_f=48, length_f=48))
        job = SimpleNamespace(chunk=SimpleNamespace(story_start_f=0, head_frames=0),
                              compiled=self.compile.CompiledChunk(0, "fl2va", "", refs))
        wave = torch.full((1, 2, 160000), -0.5)
        with patch.object(self.locks.media, "load_audio_source", return_value=torch.full((1, 2, 160000), 0.6)):
            actual = self.locks.restore_waveform(job, wave, 32000)
        for first, last, value in ((0, 32000, -0.5), (32000, 64000, 0.6), (64000, 96000, 1.0),
                                   (96000, 128000, 0.6), (128000, 160000, -0.5)):
            self.assertTrue(torch.all(actual[..., first:last] == value))

    def test_no_lock_returns_the_original_waveform(self):
        job = SimpleNamespace(compiled=self.compile.CompiledChunk(0, "fl2va", "", ()))
        wave = torch.rand(1, 2, 100)
        with patch.object(self.locks.media, "load_audio_source") as load:
            self.assertIs(self.locks.restore_waveform(job, wave, 32000), wave)
        load.assert_not_called()
