"""Video soundtrack references require an audio VAE on the real conditioning node path."""
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/ng"))
from _pack import comfy_available, load_full_pack


class VideoSoundtrackAudioVae(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved_argv = sys.argv[:]
        try:
            sys.argv = [sys.argv[0], "--cpu"]
            if not comfy_available():
                raise unittest.SkipTest("ComfyUI unavailable")
            cls.pack = load_full_pack()
            import torch
            cls.torch = torch
            for short, name in {"node": "ng.nodes.chunk_node", "builder": "ng.adapters.chunk_builder", "media": "ng.adapters.media",
                                "guides": "ng.adapters.scene_guides", "context": "ng.core.context", "options": "ng.core.context_options",
                                "project": "ng.core.project", "chunks": "ng.core.chunks"}.items():
                setattr(cls, short, importlib.import_module(cls.pack.__name__ + "." + name))
        finally:
            sys.argv = saved_argv

    def setUp(self):
        self.loads = []
        self.calls = []
        def load_audio(ref):
            self.loads.append(ref)
            return {"waveform": self.torch.ones(1, 2, 2000), "sample_rate": 44100}
        for name, fake in {"load_audio": load_audio, "load_video": lambda _ref: self.torch.zeros(5, 8, 8, 3),
                           "load_picture": lambda _ref: self.torch.zeros(1, 8, 8, 3)}.items():
            p = patch.object(self.media, name, fake)
            p.start()
            self.addCleanup(p.stop)
        def execute(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(args=("positive", {"samples": "sentinel-latent"}))
        self.fake = SimpleNamespace(MiniMaxH3ReferenceToVideo=SimpleNamespace(execute=execute))

    def video(self, key, option="reference"):
        return self.context.ContextItem(id=key, name=key, media="video", source=key + ".mp4", usage=("motion",),
                                        options=self.options.ContextOptions(video_audio=option))

    def job(self, items):
        ctx = self.context.DirectorContext(idea="A dance scene.", items=tuple(items))
        return self.project.jobs(self.project.plan_project(ctx, 5, self.chunks.ContinuityPlan("video_audio", 22, 24)))[0]

    def condition(self, job, audio_vae):
        with patch.object(self.node, "core", return_value=self.fake):
            return self.node.NGChunkConditioning.execute(job, object(), object(), audio_vae=audio_vae,
                                                       model_ref2va="model-sentinel", apply_sigma_shift=False)

    def test_actual_optional_audio_vae_node_guard_blocks_before_reference_core(self):
        schema = self.node.NGChunkConditioning.define_schema()
        input_spec = next(value for value in schema.inputs if value.id == "audio_vae")
        self.assertTrue(input_spec.optional)
        with self.assertRaisesRegex(ValueError, "audio.*VAE.*audio_vae"):
            self.condition(self.job([self.video("dance")]), None)
        self.assertEqual(self.calls, [], "No reference conditioning may silently lose soundtrack audio")

    def test_audio_vae_and_paired_video_numbering_reach_core_once(self):
        job = self.job([self.video("silent", "ignore"), self.video("dance", "reference")])
        audio_vae = object()
        with patch.object(self.guides, "video_soundtracks", wraps=self.guides.video_soundtracks) as soundtracks:
            out = self.condition(job, audio_vae)
        self.assertEqual(out.args[0], "model-sentinel")
        self.assertEqual(out.args[1], "positive")
        self.assertEqual(len(self.calls), 1)
        args = self.calls[0]
        self.assertIs(args["audio_vae"], audio_vae)
        self.assertEqual(set(args["ref_videos"]), {"ref_video_1", "ref_video_2"})
        self.assertEqual(set(args["ref_video_audios"]), {"ref_video_audio_2"})
        self.assertIsNone(args["ref_audios"])
        soundtracks.assert_called_once_with(job)
        refs = job.compiled.of_kind("video")
        self.assertEqual([(r.source, r.trim_start_f, r.length_f) for r in self.loads], [(refs[1].source, refs[1].trim_start_f, refs[1].length_f)])

    def test_video_without_soundtrack_keeps_audio_vae_optional(self):
        self.condition(self.job([self.video("silent", "ignore")]), None)
        self.assertIsNone(self.calls[0]["audio_vae"])
        self.assertIsNone(self.calls[0]["ref_video_audios"])
        self.assertIsNone(self.calls[0]["ref_audios"])
        self.assertEqual(self.loads, [])

    def test_standalone_voice_still_requires_audio_vae(self):
        image = self.context.ContextItem(id="picture", name="Dancer", media="image", source="dancer.png", usage=("reference",))
        audio = self.context.ContextItem(id="voice", name="Voice", media="audio", source="voice.wav", usage=("voice",), length_s=5)
        with self.assertRaisesRegex(ValueError, "audio_vae"):
            self.condition(self.job([image, audio]), None)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
