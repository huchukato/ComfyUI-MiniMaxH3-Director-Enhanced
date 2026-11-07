"""Shared image assets, paired video audio and distinct voice windows through actual H3 presentation."""
import unittest
from unittest.mock import patch

from _pack import comfy_available, load_full_pack, module

ctx = module("ng.core.context")
opts = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def mixed_project(extra_take=False):
    items = [ctx.ContextItem("alice", "Straße", "image", "same.png", content=("character",), usage=("reference",)),
             ctx.ContextItem("bob", "Bob", "image", "same.png", content=("character",), usage=("reference",)),
             ctx.ContextItem("coat", "Coat", "image", "same.png", content=("outfit",), usage=("reference",),
                             subject_ids=("alice", "bob")),
             ctx.ContextItem("move", "Move", "video", "v.mp4", content=("motion",), usage=("motion",), length_s=8,
                             subject_ids=("alice", "bob"), options=opts.ContextOptions(start_s=.5, end_s=3.5, video_audio="reference")),
             ctx.ContextItem("voice_a", "VoiceA", "audio", "v.wav", usage=("voice",), speaker="STRASSE", length_s=12,
                             options=opts.ContextOptions(start_s=.5, end_s=2.5)),
             ctx.ContextItem("voice_b", "VoiceB", "audio", "v.wav", usage=("voice",), speaker="bob", length_s=12,
                             options=opts.ContextOptions(start_s=0, end_s=1.5)),
             ctx.ContextItem("rules", "Rules", "text", "Keep @STRASSE and @Bob visible; @VoiceA and @VoiceB stay separate.",
                             usage=("rule",), subject_ids=("alice", "bob"))]
    if extra_take:
        items.append(ctx.ContextItem("take_a", "ExtraA", "audio", "v.wav", usage=("voice",), speaker="alice", length_s=12,
                                     options=opts.ContextOptions(start_s=1, end_s=2.5)))
    context = ctx.DirectorContext(idea="@STRASSE and @Bob wear @Coat.", items=tuple(items), project_seconds=12,
                 width=64, height=64, shots_text="0-4: @STRASSE looks up.\n@STRASSE says: Hello.\n"
                 "4-8: @Bob smiles.\n@Bob says: Good morning.\n8-12: @STRASSE and @Bob turn.")
    return project.plan_project(context, 5, chunks.ContinuityPlan("video_audio", 22, 24))


class MultiSubjectMedia(unittest.TestCase):
    def test_two_voices_keep_their_windows_and_dialogue_is_not_repeated_in_carried_shots(self):
        result = mixed_project()
        self.assertEqual(len(result.compiled), 3)
        for compiled in result.compiled:
            labels = dict(compiled.prompt_labels)
            self.assertEqual([r.ctx_id for r in compiled.of_kind("picture")], ["alice", "coat", "bob", "coat"])
            self.assertEqual([labels["<Audio %d>" % n] for n in (1, 2, 3)], ["move", "voice_a", "voice_b"])
            self.assertEqual([(r.ctx_id, r.trim_start_f, r.length_f) for r in compiled.of_kind("audio")],
                             [("voice_a", 12, 48), ("voice_b", 0, 36)])
            self.assertIn("<Subject 2> uses the outfit reference in <Picture 4>", compiled.prompt)
            self.assertIn("For <Subject 1> and <Subject 2>: Keep <Subject 1> and <Subject 2>", compiled.prompt)
            self.assertIn("<Audio 3> is the voice-timbre reference for <Subject 2>", compiled.prompt)
        prompt = "\n".join(c.prompt for c in result.compiled)
        self.assertEqual(prompt.count("<d>[English] Hello.</d>"), 1)
        self.assertEqual(prompt.count("<d>[English] Good morning.</d>"), 1)
        self.assertNotIn("@", prompt)

    def test_extra_take_remains_a_named_reference_without_displacing_either_subject_voice(self):
        for compiled in mixed_project(extra_take=True).compiled:
            self.assertEqual([r.ctx_id for r in compiled.of_kind("audio")], ["voice_a", "voice_b", "take_a"])
            self.assertEqual(dict(compiled.prompt_labels)["<Audio 4>"], "take_a")
            self.assertIn("<Audio 2> is the voice-timbre reference for <Subject 1>", compiled.prompt)
            self.assertIn("<Audio 3> is the voice-timbre reference for <Subject 2>", compiled.prompt)
            notes = [issue for issue in compiled.issues if issue.code == "voice_extra_take"]
            self.assertEqual([issue.ref for issue in notes], ["ExtraA"])

    @unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
    def test_native_tokenizer_receives_four_pictures_paired_soundtrack_and_two_voice_clips(self):
        import torch
        load_full_pack()
        media, builder = module("ng.adapters.media"), module("ng.adapters.chunk_builder")
        native = module("minimax_core").core()
        class Encoder:
            def tokenize(self, prompt, **kwargs):
                self.prompt, self.presentation = prompt, kwargs["minimax_ref_items"]
                return "tokens"
            def encode_from_tokens_scheduled(self, tokens):
                return [[torch.zeros(1, 1, 8), {}]]
        class AudioVAE:
            audio_sample_rate = 44100
            def encode(self, wave):
                return torch.zeros(1, 32, 2, round(wave.shape[1] / 44100 * 40))
        pictures, audios = [], []
        def picture(ref):
            pictures.append(ref.ctx_id)
            return torch.zeros(1, 64, 64, 3)
        def audio(ref):
            audios.append((ref.ctx_id, ref.trim_start_f, ref.length_f))
            return {"waveform": torch.zeros(1, 2, round(ref.length_f / 24 * 44100)), "sample_rate": 44100}
        encoder = Encoder()
        with patch.object(media, "load_picture", side_effect=picture), patch.object(media, "load_audio", side_effect=audio), \
             patch.object(media, "load_video", return_value=torch.zeros(72, 64, 64, 3)):
            built = builder.build_chunk(project.jobs(mixed_project())[0], encoder, None, AudioVAE(), mm=native)
        self.assertEqual(pictures, ["alice", "coat", "bob", "coat"])
        self.assertEqual(audios, [("voice_a", 12, 48), ("voice_b", 0, 36), ("move", 12, 72)])
        self.assertEqual([item["type"] for item in encoder.presentation], ["image"] * 4 + ["audio", "video", "audio", "audio"])
        self.assertEqual([r["ref_audio_t"] for r in built.positive[0][1]["minimax_refs"]], [80, 60])
        self.assertIn("<Audio 3> is the voice-timbre reference for <Subject 2>", encoder.prompt)
