"""Source samples and story placement are independent, including repeated use and carry heads."""
import math
import unittest
from unittest.mock import patch

from _pack import comfy_available, module, stub_prompt_server
from test_shot_scope_contract import plan, shot

ctx, opts = module("ng.core.context"), module("ng.core.context_options")
chunks, project = module("ng.core.chunks"), module("ng.core.project")
compile_ = module("ng.core.compile")
HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    stub_prompt_server()
    builder, media = module("ng.adapters.chunk_builder"), module("ng.adapters.media")
    from test_chunk_builder import FakeCore, empty_latent


def sound(role, **changes):
    return ctx.ContextItem("sound", "Sound", "audio", "sound.wav", usage=(role,), length_s=12, **changes)


class Placement(unittest.TestCase):
    def test_late_short_selection_starts_at_shot_and_restarts_in_each_binding(self):
        records = [shot("one", 3, 5, [("sound", "context")]), shot("two", 7, 9, [("sound", "context")])]
        for role, kind in (("copy", "audio"), ("lock", "lock")):
            with self.subTest(role=role):
                item = sound(role, options=opts.ContextOptions(start_s=1, end_s=2))
                result = plan(records, (item,), 10, 10)
                refs = result.compiled[0].of_kind(kind)
                self.assertEqual([(r.start_f, r.length_f, r.trim_start_f) for r in refs], [(72, 24, 24), (168, 24, 24)])
                self.assertEqual([r.ctx_id for r in refs], ["sound", "sound"])
                self.assertEqual(result.context.items[0].options, item.options)
                self.assertNotIn("shot_audio_origin", {i.code for i in result.issues})
                restored = compile_.CompiledChunk.from_dict(result.compiled[0].to_dict())
                self.assertEqual(restored, result.compiled[0])
                if role == "copy":
                    self.assertIn("partially_copy", restored.prompt)
                    self.assertIn("3.000-4.000s", restored.prompt)
                    self.assertIn("7.000-8.000s", restored.prompt)
                    self.assertEqual(dict(restored.prompt_labels), {"<Audio 1>": "sound", "<Audio 2>": "sound"})

    def test_carry_advances_source_and_clips_at_actual_shot_end(self):
        for mode in ("none", "video", "video_audio"):
            for role, kind in (("copy", "audio"), ("lock", "lock")):
                with self.subTest(mode=mode, role=role):
                    item = sound(role, options=opts.ContextOptions(start_s=1, end_s=11))
                    records = [shot("late", 2, 10, [("sound", "context")])]
                    result = plan(records, (item,), 12, 5, chunks.ContinuityPlan(mode))
                    for chunk, compiled in zip(result.plan.chunks, result.compiled):
                        window = chunk.story_start_f - chunk.head_frames
                        first, last = max(48, window), min(240, chunk.story_end_f)
                        expected = [(first - window, last - first, 24 + first - 48)] if last > first else []
                        self.assertEqual([(r.start_f, r.length_f, r.trim_start_f) for r in compiled.of_kind(kind)], expected)

    def test_normalized_overlap_and_clipped_end_do_not_use_raw_document_times(self):
        records = [shot("first", 0, 4, []), shot("overlap", 3, 20, [("sound", "lock")])]
        result = plan(records, (sound("lock"),), 10, 10)
        self.assertEqual([(r.start_f, r.length_f, r.trim_start_f) for r in result.compiled[0].of_kind("lock")], [(96, 144, 0)])
        self.assertTrue({"shot_overlap", "shot_clipped"} <= {i.code for i in result.issues})

    def test_selected_source_past_known_file_end_is_not_an_invented_lock(self):
        item = sound("lock", options=opts.ContextOptions(start_s=13))
        result = plan([shot("late", 2, 8, [("sound", "lock")])], (item,))
        self.assertFalse(result.compiled[0].of_kind("lock"))


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class NativeLockPlacement(unittest.TestCase):
    def test_repeated_copy_passes_selected_source_samples_to_actual_native_audio_refs(self):
        records = [shot("one", 3, 5, [("sound", "copy")]), shot("two", 7, 9, [("sound", "copy")])]
        result = plan(records, (sound("copy", options=opts.ContextOptions(start_s=1, end_s=2)),), 10, 10)
        native = module("minimax_core").core()
        waves = []
        class AudioVAE:
            audio_sample_rate = 44100
            def encode(self, wave):
                waves.append(wave.clone())
                return torch.zeros(1, 32, 2, round(wave.shape[1] / 44100 * 40))
        class Encoder:
            def tokenize(self, prompt, **kwargs):
                self.presentation = kwargs["minimax_ref_items"]
                self.prompt = prompt
                return "tokens"
            def encode_from_tokens_scheduled(self, tokens):
                return [[torch.zeros(1, 1, 8), {}]]
        source = torch.arange(3 * 44100, dtype=torch.float32)[None, None, :] / (3 * 44100)
        def loaded(ref):
            a, n = int(ref.trim_start_f / 24 * 44100), int(ref.length_f / 24 * 44100)
            return {"waveform": source[..., a:a+n], "sample_rate": 44100}
        encoder = Encoder()
        with patch.object(media, "load_audio", side_effect=loaded):
            builder.build_chunk(project.jobs(result)[0], encoder, None, AudioVAE(), mm=native)
        self.assertEqual(len(waves), 2)
        self.assertTrue(all(torch.equal(wave, source[..., 44100:88200].movedim(1, -1)) for wave in waves))
        self.assertEqual([item["type"] for item in encoder.presentation], ["audio", "audio"])
        self.assertEqual(encoder.prompt, result.compiled[0].prompt)

    def test_resampling_uses_native_audio_helper_and_limits_to_ref_length(self):
        ref = compile_.MediaRef("lock", "a", "a.wav", 24, 24)
        wave = torch.full((1, 1, 200), .25)
        with patch.object(media, "load_audio", return_value={"waveform": wave, "sample_rate": 100}), \
             patch.object(builder.comfy.audio, "resample", return_value=torch.full((1, 1, 400), .25)) as resample:
            mix = builder._locked_waveform((ref,), 72, 200)["waveform"]
        resample.assert_called_once_with(wave, 100, 200)
        self.assertTrue(torch.all(mix[..., :200] == 0))
        self.assertTrue(torch.all(mix[..., 200:400] == .25))
        self.assertTrue(torch.all(mix[..., 400:] == 0))

    def test_the_lock_track_fills_whole_audio_latent_steps(self):
        # A 209-frame chunk is 348.33 steps at 40/s; with a partial last step the locked song came back garbled for the
        # whole chunk (rendered: 0.3 correlation with the song; padded: 0.95 like 192 and 243 frames).
        ref = compile_.MediaRef("lock", "a", "a.wav", 0, 209)
        with patch.object(media, "load_audio", return_value={"waveform": torch.full((1, 2, 300000), .25), "sample_rate": 32000}):
            padded = builder._locked_waveform((ref,), 209, 32000, 40)["waveform"]
            plain = builder._locked_waveform((ref,), 209, 32000)["waveform"]
        self.assertEqual(padded.shape[-1], 349 * 800, "whole steps of 800 samples at 32 kHz")
        self.assertEqual(plain.shape[-1], round(209 / 24 * 32000))
        self.assertEqual(builder._locked_waveform((), 243, 32000, 40)["waveform"].shape[-1], 405 * 800, "already whole: unchanged")

    def test_overlapping_stereo_and_mono_sum_then_clip_independent_of_order(self):
        refs = (compile_.MediaRef("lock", "a", "a.wav", 24, 48), compile_.MediaRef("lock", "b", "b.wav", 48, 48))
        def loaded(ref):
            if ref.ctx_id == "a":
                return {"waveform": torch.tensor([.2, .4])[None, :, None].expand(1, 2, 200), "sample_rate": 100}
            return {"waveform": torch.full((1, 1, 200), .8), "sample_rate": 100}
        with patch.object(media, "load_audio", side_effect=loaded):
            first = builder._locked_waveform(refs, 120, 100)["waveform"]
            other = builder._locked_waveform(tuple(reversed(refs)), 120, 100)["waveform"]
        self.assertTrue(torch.equal(first, other))
        self.assertTrue(torch.all(first[..., :100] == 0))
        self.assertTrue(torch.all(first[..., 100:200] == torch.tensor([.2, .4])[None, :, None]))
        self.assertTrue(torch.all(first[..., 200:300] == 1))
        self.assertTrue(torch.all(first[..., 300:400] == .8))
        self.assertTrue(torch.all(first[..., 400:] == 0))

    def test_late_lock_keeps_audio_carry_and_masks_only_its_interval(self):
        records = [shot("late", 7, 8, [("sound", "lock")])]
        result = plan(records, (sound("lock"),), 12, 5, chunks.ContinuityPlan())
        job = project.jobs(result)[1]
        previous = empty_latent(result.plan.chunks[0].sampled_frames)
        with patch.object(media, "load_audio", return_value={"waveform": torch.ones(1, 2, 44100), "sample_rate": 44100}):
            built = builder.build_chunk(job, object(), object(), audio_vae=object(), previous=previous, mm=FakeCore())
        self.assertTrue(any("audio_latent" in key for key in built.positive[0][1]["minimax_keyframes"]))
        ref = job.compiled.of_kind("lock")[0]
        first, last = math.floor(ref.start_f / 24 * 40), math.ceil((ref.start_f + ref.length_f) / 24 * 40)
        vm, am = built.latent["noise_mask"].unbind()
        self.assertTrue(torch.all(vm == 1))
        self.assertTrue(torch.all(am[..., :first] == 1))
        self.assertTrue(torch.all(am[..., first:last] == 0))
        self.assertTrue(torch.all(am[..., last:] == 1))


if __name__ == "__main__":
    unittest.main()
