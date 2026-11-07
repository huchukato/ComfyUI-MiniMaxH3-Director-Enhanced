"""Reference audio numbering and guide timing at the native H3 adapter boundary."""
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from _pack import comfy_available, load_full_pack


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class SceneGuides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = load_full_pack().__name__
        cls.adapter = importlib.import_module(name + ".ng.adapters.scene_guides")
        cls.compile = importlib.import_module(name + ".ng.core.compile")
        cls.context = importlib.import_module(name + ".ng.core.context")
        cls.options = importlib.import_module(name + ".ng.core.context_options")

    def test_paired_soundtrack_keeps_video_number_and_trim_when_first_is_ignored(self):
        ctx, opt, comp = self.context, self.options, self.compile
        items = (ctx.ContextItem("a", "Silent", "video", "a.mp4"),
                 ctx.ContextItem("b", "Sound", "video", "b.mp4", options=opt.ContextOptions(video_audio="reference")))
        context = ctx.DirectorContext(items=items)
        refs = (comp.MediaRef("video", "a", "a.mp4", length_f=96),
                comp.MediaRef("video", "b", "b.mp4", length_f=72, trim_start_f=48))
        job = SimpleNamespace(project=SimpleNamespace(context=context), compiled=comp.CompiledChunk(0, "ref2va", "", refs))
        with patch.object(self.adapter.media, "load_audio", return_value="sound") as load:
            self.assertEqual(self.adapter.video_soundtracks(job), {"ref_video_audio_2": "sound"})
        ref = load.call_args.args[0]
        self.assertEqual((ref.source, ref.length_f, ref.trim_start_f), ("b.mp4", 72, 48))

    def test_keyframe_keeps_local_time_and_continuation_sends_its_source_clip_and_sound(self):
        import torch
        comp = self.compile
        refs = (comp.MediaRef("keyframe", "i", "image.png", start_f=39),
                comp.MediaRef("continue_video", "v", "clip.mp4", length_f=39, trim_start_f=105))
        item = self.context.ContextItem("v", "Source", "video", "clip.mp4", length_s=8,
                                        options=self.options.ContextOptions(start_s=3, end_s=6, video_audio="reference"))
        job = SimpleNamespace(compiled=comp.CompiledChunk(0, "fl2va", "", refs),
                              project=SimpleNamespace(context=self.context.DirectorContext(items=(item,))))
        calls = []
        def execute(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(args=("next",))
        mm = SimpleNamespace(MiniMaxH3AddGuide=SimpleNamespace(execute=execute))
        image, frames = torch.zeros(1, 2, 2, 3), torch.zeros(39, 2, 2, 3)
        sound = {"waveform": torch.zeros(1,2,52000), "sample_rate":32000}
        with patch.object(self.adapter.media, "load_picture", return_value=image), \
             patch.object(self.adapter.continuation_media, "load", return_value=(frames,sound)) as load:
            self.assertEqual(self.adapter.apply_guides(mm, job, "positive", "latent", "vae", "audio_vae"), "next")
        load.assert_called_once_with(refs[1],item,"audio_vae")
        self.assertEqual([call["frame_idx"] for call in calls], [39, 0])
        self.assertEqual(calls[1]["positive"], "next")
        self.assertTrue(torch.equal(calls[1]["image"], frames))
        self.assertIs(calls[1]["audio"],sound)

    def test_global_ref_first_last_are_timed_guides_without_duplicating_fl_anchors(self):
        import torch
        refs = (self.compile.MediaRef("first_frame", "first", "first.png", start_f=0),
                self.compile.MediaRef("last_frame", "last", "last.png", start_f=123))
        calls = []
        def execute(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(args=("next",))
        native = SimpleNamespace(MiniMaxH3AddGuide=SimpleNamespace(execute=execute))
        with patch.object(self.adapter.media, "load_picture", return_value=torch.zeros(1, 2, 2, 3)):
            for mode, expected in (("ref2va", [0, 123]), ("fl2va", [])):
                calls.clear()
                job = SimpleNamespace(compiled=self.compile.CompiledChunk(0, mode, "", refs))
                self.adapter.apply_guides(native, job, "positive", "latent", "vae")
                self.assertEqual([call["frame_idx"] for call in calls], expected)


if __name__ == "__main__":
    unittest.main()
