"""A file may be reused by several cards; prompt labels still have to describe the media actually sent."""
import importlib
import unittest
from unittest.mock import patch

from _pack import module, comfy_available, load_full_pack

ctx=module("ng.core.context")
opt=module("ng.core.context_options")
chunks=module("ng.core.chunks")
project=module("ng.core.project")


class MediaIdentity(unittest.TestCase):
    def compile(self,items,**changes):
        settings=dict(idea="@Mage moves while @Move guides the camera.",project_seconds=8,width=64,height=64,
             shots_text="0-8: @Mage looks up.\n@Mage says: Hello.",items=tuple(items),soundscape="Room",music="N/A")
        settings.update(changes)
        context=ctx.DirectorContext(**settings)
        return project.plan_project(context,5,chunks.ContinuityPlan("video_audio",22,24))

    def image(self):
        return ctx.ContextItem("mage","Mage","image","mage.png",usage=("reference",),content=("character",))

    def test_shared_video_file_preserves_both_card_ids_windows_and_soundtrack_choices(self):
        first=ctx.ContextItem("silent","Silent","video","move.mp4",usage=("motion",),length_s=8,
                              options=opt.ContextOptions(start_s=0,end_s=2,video_audio="ignore"))
        second=ctx.ContextItem("move","Move","video","move.mp4",usage=("motion",),length_s=8,
                              options=opt.ContextOptions(start_s=3,end_s=6,video_audio="reference"))
        result=self.compile([self.image(),first,second])
        for compiled in result.compiled:
            self.assertEqual([(r.ctx_id,r.trim_start_f,r.length_f) for r in compiled.of_kind("video")],
                             [("silent",0,48),("move",72,72)])

    def test_shared_audio_file_cannot_apply_the_first_cards_trim_to_the_bound_voice(self):
        background=ctx.ContextItem("music","Song","audio","same.wav",usage=("music_style",),length_s=8,
                                   options=opt.ContextOptions(start_s=1,end_s=2))
        voice=ctx.ContextItem("voice","Voice","audio","same.wav",usage=("voice",),speaker="mage",length_s=8,
                              options=opt.ContextOptions(start_s=3,end_s=6))
        result=self.compile([self.image(),background,voice])
        for compiled in result.compiled:
            self.assertEqual([(r.ctx_id,r.trim_start_f,r.length_f) for r in compiled.of_kind("audio")],
                             [("voice",72,72),("music",24,24)])

    def test_paired_video_audio_is_numbered_before_a_subjects_standalone_voice(self):
        video=ctx.ContextItem("move","Move","video","move.mp4",usage=("motion",),length_s=3,
                              options=opt.ContextOptions(video_audio="reference"))
        voice=ctx.ContextItem("voice","Voice","audio","voice.wav",usage=("voice",),speaker="mage",length_s=3)
        note=ctx.ContextItem("note","Rules","text","Keep @Mage in warm lighting. Use @Move for the camera.",usage=("rule",))
        result=self.compile([self.image(),video,voice,note])
        for compiled in result.compiled:
            self.assertIn("<Audio 1> is the soundtrack of <Video 1>",compiled.prompt)
            self.assertIn("<Audio 2> is the voice-timbre reference for <Subject 1>",compiled.prompt)
            self.assertIn("Keep <Subject 1> in warm lighting.",compiled.prompt)
            self.assertIn("Use <Video 1> for the camera.",compiled.prompt)
            self.assertNotIn("@Move",compiled.prompt)

    def test_copied_audio_sections_and_named_mentions_follow_the_paired_audio_offset(self):
        video=ctx.ContextItem("move","Move","video","move.mp4",usage=("motion",),length_s=3,
                              options=opt.ContextOptions(video_audio="reference"))
        copied=ctx.ContextItem("song","Große Musik","audio","song.wav",usage=("copy",),length_s=8)
        note=ctx.ContextItem("note","Rules","text","Use @Große Musik as the song.",usage=("rule",))
        for compiled in self.compile([self.image(),video,copied,note],soundscape="",music="").compiled:
            self.assertIn("Use <Audio 2> as the song.",compiled.prompt)
            sound=compiled.prompt.split("overall_soundscape:",1)[1]
            self.assertIn("<Audio 2>",sound)
            self.assertNotIn("<Audio 1>",sound)

    def test_dropped_paired_video_does_not_shift_the_surviving_voice(self):
        videos=[ctx.ContextItem("v%d"%n,"Video%d"%n,"video","v%d.mp4"%n,usage=("motion",),length_s=10,
                 options=opt.ContextOptions(video_audio="reference" if n else "ignore")) for n in range(2)]
        voice=ctx.ContextItem("voice","Voice","audio","voice.wav",usage=("voice",),speaker="mage",length_s=3)
        compiled=self.compile([self.image(),*videos,voice]).compiled[0]
        self.assertEqual([r.ctx_id for r in compiled.of_kind("video")],["v0"])
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1>",compiled.prompt)
        self.assertNotIn("soundtrack of",compiled.prompt)


@unittest.skipUnless(comfy_available(),"ComfyUI is not importable")
class NativePresentation(unittest.TestCase):
    def test_compiled_labels_match_real_native_h3_tokenizer_presentation_and_card_windows(self):
        import torch
        name=load_full_pack().__name__
        context=importlib.import_module(name+".ng.core.context")
        options=importlib.import_module(name+".ng.core.context_options")
        planner=importlib.import_module(name+".ng.core.project")
        chunkmod=importlib.import_module(name+".ng.core.chunks")
        builder=importlib.import_module(name+".ng.adapters.chunk_builder")
        media=importlib.import_module(name+".ng.adapters.media")
        native=importlib.import_module(name+".minimax_core").core()
        items=(context.ContextItem("mage","Mage","image","mage.png",usage=("reference",)),
               context.ContextItem("silent","Silent","video","same.mp4",usage=("motion",),length_s=8,
                                   options=options.ContextOptions(start_s=0,end_s=2)),
               context.ContextItem("move","Move","video","same.mp4",usage=("motion",),length_s=8,
                                   options=options.ContextOptions(start_s=3,end_s=6,video_audio="reference")),
               context.ContextItem("voice","Voice","audio","voice.wav",usage=("voice",),speaker="mage",length_s=8,
                                   options=options.ContextOptions(start_s=1,end_s=4)),
               context.ContextItem("note","Rules","text","Keep @Mage under warm light and follow @Move.",usage=("rule",)))
        plan=planner.plan_project(context.DirectorContext(idea="@Mage walks.",items=items,project_seconds=8,width=64,height=64),
                                  5,chunkmod.ContinuityPlan("video_audio",22,24))
        job=planner.jobs(plan)[0]
        class Encoder:
            def tokenize(self,prompt,**kwargs):
                self.prompt,self.presentation=prompt,kwargs["minimax_ref_items"]
                return "tokens"
            def encode_from_tokens_scheduled(self,tokens):
                return [[torch.zeros(1,1,8),{}]]
        class AudioVAE:
            audio_sample_rate=44100
            def encode(self,wave):
                return torch.zeros(1,32,2,round(wave.shape[1]/44100*40))
        clip=Encoder()
        loaded=[]
        def audio(ref):
            loaded.append(ref)
            return {"waveform":torch.zeros(1,2,round(ref.length_f/24*44100)),"sample_rate":44100}
        with patch.object(media,"load_picture",return_value=torch.zeros(1,64,64,3)), \
             patch.object(media,"load_video",return_value=torch.zeros(72,64,64,3)),patch.object(media,"load_audio",side_effect=audio):
            builder.build_chunk(job,clip,None,audio_vae=AudioVAE(),mm=native)
        self.assertEqual([entry["type"] for entry in clip.presentation],["image","video","audio","video","audio"])
        self.assertIn("<Audio 1> is the soundtrack of <Video 2>",clip.prompt)
        self.assertIn("<Audio 2> is the voice-timbre reference for <Subject 1>",clip.prompt)
        self.assertEqual([(ref.ctx_id,ref.trim_start_f,ref.length_f) for ref in loaded],[("voice",24,72),("move",72,72)])



if __name__=="__main__":
    unittest.main()
