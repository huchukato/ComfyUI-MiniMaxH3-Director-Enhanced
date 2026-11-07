"""Actual installed H3 node/Tokenizer contract, using generated tensors instead of model weights."""
import importlib
import json
import unittest
from unittest.mock import patch

from _pack import comfy_available, load_full_pack


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class NativeAssetPresentation(unittest.TestCase):
    def test_shot_scoped_video_soundtrack_and_audio_reach_actual_native_presentation(self):
        import torch
        name = load_full_pack().__name__
        ctx = importlib.import_module(name + ".ng.core.context")
        opts = importlib.import_module(name + ".ng.core.context_options")
        project = importlib.import_module(name + ".ng.core.project")
        chunks = importlib.import_module(name + ".ng.core.chunks")
        media = importlib.import_module(name + ".ng.adapters.media")
        builder = importlib.import_module(name + ".ng.adapters.chunk_builder")
        native = importlib.import_module(name + ".minimax_core").core()
        records = [{"id": identity, "start": start, "end": end, "text": "A quiet room.",
                    "media": [{"schema_version": 1, "context_id": target, "role": "context"} for target in targets]}
                   for identity, start, end, targets in (("first", 0, 85/24, ()), ("middle", 85/24, 8, ()),
                                                        ("last", 8, 277/24, ("move", "voice")))]
        document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": records})
        items = (ctx.ContextItem("move", "Move", "video", "move.mp4", length_s=3,
                                 options=opts.ContextOptions(start_s=.5, end_s=2, video_audio="reference")),
                 ctx.ContextItem("voice", "Voice", "audio", "voice.wav", length_s=2))
        result = project.plan_project(ctx.DirectorContext(shots_text=document, items=items, project_seconds=277/24,
                                                         width=64, height=64), 4, chunks.ContinuityPlan())
        self.assertEqual([c.mode for c in result.compiled], ["t2va", "t2va", "ref2va"])
        self.assertTrue(all(not c.refs for c in result.compiled[:2]))
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
        encoder = Encoder()
        with patch.object(media, "load_picture", side_effect=AssertionError("unexpected picture")), \
             patch.object(media, "load_video", return_value=torch.zeros(36, 64, 64, 3)) as video, \
             patch.object(media, "load_audio", return_value={"waveform": torch.zeros(1, 2, 66150), "sample_rate": 44100}) as audio:
            builder.build_chunk(project.jobs(result)[2], encoder, None, AudioVAE(), mm=native)
        self.assertEqual([(call.args[0].ctx_id, call.args[0].trim_start_f, call.args[0].length_f)
                          for call in video.call_args_list], [("move", 12, 36)])
        self.assertEqual([call.args[0].ctx_id for call in audio.call_args_list], ["voice", "move"])
        self.assertEqual([item["type"] for item in encoder.presentation], ["audio", "video", "audio"])
        self.assertIn("<Audio 1> is the soundtrack of <Video 1>", encoder.prompt)

    def test_native_schema_and_execute_consume_relationships_without_media_inputs(self):
        nodes = load_full_pack().NODE_CLASS_MAPPINGS
        for kind in ("Image", "Video", "Text"):
            node = nodes["NGContext" + kind]
            inputs = {item.id: item for item in node.GET_SCHEMA().inputs}
            self.assertTrue(inputs["subject_ids"].optional)
            self.assertEqual(inputs["subject_ids"].io_type, "STRING")
            self.assertFalse({"IMAGE", "VIDEO", "AUDIO"} & {item.io_type for item in inputs.values()})
        item = nodes["NGContextImage"].execute(image="coat.png", name="Coat", description="", content="outfit", usage="reference",
              preserve="high", context_id="coat", subject_ids='["alice","bob"]').args[0]
        self.assertEqual(item.subject_ids, ("alice", "bob"))
        self.assertNotIn("subject_ids", {item.id for item in nodes["NGContextAudio"].GET_SCHEMA().inputs})

    def test_grouped_pictures_and_paired_audio_reach_the_native_tokenizer_in_label_order(self):
        import torch
        name = load_full_pack().__name__
        ctx = importlib.import_module(name + ".ng.core.context")
        opts = importlib.import_module(name + ".ng.core.context_options")
        project = importlib.import_module(name + ".ng.core.project")
        chunks = importlib.import_module(name + ".ng.core.chunks")
        media = importlib.import_module(name + ".ng.adapters.media")
        builder = importlib.import_module(name + ".ng.adapters.chunk_builder")
        native = importlib.import_module(name + ".minimax_core").core()
        items = (ctx.ContextItem("alice", "Alice", "image", "same.png", usage=("reference",)),
                 ctx.ContextItem("bob", "Bob", "image", "same.png", usage=("reference",)),
                 ctx.ContextItem("coat", "Coat", "image", "same.png", content=("outfit",), usage=("reference",), subject_ids=("alice", "bob")),
                 ctx.ContextItem("move", "Move", "video", "v.mp4", usage=("motion",), length_s=2, subject_ids=("alice",),
                                 options=opts.ContextOptions(video_audio="reference")),
                 ctx.ContextItem("voice", "Voice", "audio", "v.wav", usage=("voice",), speaker="alice", length_s=2))
        result = project.plan_project(ctx.DirectorContext(idea="@Alice wears @Coat.", items=items, project_seconds=8, width=64, height=64),
                                      5, chunks.ContinuityPlan("none"))
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
        loaded = []
        def picture(ref):
            loaded.append(ref.ctx_id)
            return torch.zeros(1, 64, 64, 3)
        encoder = Encoder()
        with patch.object(media, "load_picture", side_effect=picture), \
             patch.object(media, "load_video", return_value=torch.zeros(48, 64, 64, 3)), \
             patch.object(media, "load_audio", return_value={"waveform": torch.zeros(1, 2, 88200), "sample_rate": 44100}):
            builder.build_chunk(project.jobs(result)[0], encoder, None, AudioVAE(), mm=native)
        self.assertEqual(loaded, ["alice", "coat", "bob", "coat"])
        # The native node places a video's paired soundtrack immediately before its video;
        # standalone voice references follow that pair. Audio numbering follows audio tokens.
        self.assertEqual([item["type"] for item in encoder.presentation], ["image"] * 4 + ["audio", "video", "audio"])
        self.assertIn("<Subject 2> uses the outfit reference in <Picture 4>", encoder.prompt)
        self.assertIn("<Audio 1> is the soundtrack of <Video 1>", encoder.prompt)
        self.assertIn("<Audio 2> is the voice-timbre reference for <Subject 1>", encoder.prompt)
