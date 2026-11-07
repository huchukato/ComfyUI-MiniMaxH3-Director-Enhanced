"""Source-prefix synchronization, native target masks and exact source offsets."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from _pack import comfy_available, module, stub_prompt_server

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    from comfy.nested_tensor import NestedTensor
    stub_prompt_server()
    media = module('ng.adapters.continuation_media')
    held = module('ng.adapters.continuation_latent')
    ctx,opts,refs = module('ng.core.context'),module('ng.core.context_options'),module('ng.core.media_ref')


@unittest.skipUnless(HAVE_COMFY,'ComfyUI is not importable')
class ContinuationMedia(unittest.TestCase):
    def test_sound_prefix_is_held_and_only_its_duplicate_guide_is_removed(self):
        video, audio = torch.zeros(1,24,57,4,4), torch.zeros(1,32,2,320)
        prefix = torch.randn(1,32,2,150)
        image = torch.ones(1,24,27,4,4)
        target = {'samples':NestedTensor((video,audio)),
                  'noise_mask':NestedTensor((torch.ones_like(video[:, :1]),torch.ones_like(audio)))}
        row = {'resolved_frame_index':0, 'latent':image, 'audio_latent':prefix}
        later = {'resolved_frame_index':180, 'audio_latent':torch.ones(1,32,2,10)}
        positive = [[None,{'minimax_keyframes':[row,later], 'other':'kept'}]]
        result,cond = held.hold_sound_prefix(target,positive)
        self.assertTrue(torch.equal(result['samples'].unbind()[1][...,:150],prefix))
        self.assertTrue(torch.all(result['samples'].unbind()[1][...,150:]==0))
        self.assertTrue(torch.all(result['noise_mask'].unbind()[1][...,:150]==0))
        self.assertTrue(torch.all(result['noise_mask'].unbind()[1][...,150:]==1))
        self.assertIs(result['samples'].unbind()[0],video)
        self.assertIs(cond[0][1]['minimax_keyframes'][0]['latent'],image)
        self.assertNotIn('audio_latent',cond[0][1]['minimax_keyframes'][0])
        self.assertIs(cond[0][1]['minimax_keyframes'][1]['audio_latent'],later['audio_latent'])
        self.assertIn('audio_latent',row)
        self.assertTrue(torch.all(audio==0))
        self.assertEqual(cond[0][1]['other'],'kept')

    def test_ignore_has_no_sound_prefix_to_hold(self):
        target = {'samples':NestedTensor((torch.zeros(1,24,12,4,4),torch.zeros(1,32,2,65)))}
        positive = [[None,{'minimax_keyframes':[{'resolved_frame_index':0,'latent':torch.zeros(1,24,2,4,4)}]}]]
        result,cond = held.hold_sound_prefix(target,positive)
        self.assertIs(result,target)
        self.assertIs(cond,positive)

    def test_source_sound_ends_with_selected_video_and_partial_hops_pad_only_on_the_right(self):
        wave = torch.arange(192000,dtype=torch.float32).reshape(1,-1).expand(2,-1)
        item = ctx.ContextItem('v','Song','video','v.mp4',length_s=6,
                               options=opts.ContextOptions(end_s=5.875,video_audio='reference'))
        for count,expected_samples in ((39,52000),(22,29600)):
            reference = refs.MediaRef('continue_video','v','v.mp4',length_f=count)
            with patch.object(media.video_end,'tail_frames',return_value='images'), \
                 patch.object(media,'input_path',return_value='v.mp4'),patch.object(media.nodes_audio,'load',return_value=(wave,32000)):
                image,audio = media.load(reference,item,SimpleNamespace(audio_sample_rate=32000))
            first = round((5.875-count/24)*32000)
            actual_count = 188000-first
            self.assertEqual(image,'images')
            self.assertEqual(audio['waveform'].shape[-1],expected_samples)
            self.assertTrue(torch.equal(audio['waveform'][0,:,:actual_count],wave[:,first:188000]))
            self.assertTrue(torch.all(audio['waveform'][...,actual_count:]==0))

    def test_ignore_keeps_video_guidance_without_loading_audio_or_requiring_an_audio_vae(self):
        item = ctx.ContextItem('v','Silent','video','v.mp4',length_s=2)
        reference = refs.MediaRef('continue_video','v','v.mp4',length_f=39)
        with patch.object(media.video_end,'tail_frames',return_value='images'),patch.object(media.nodes_audio,'load') as load:
            self.assertEqual(media.load(reference,item,None),('images',None))
        load.assert_not_called()

    def test_44100_and_48000_hz_tails_stay_on_whole_audio_steps_after_resampling(self):
        item = ctx.ContextItem('v','Song','video','v.mp4',length_s=5.875,
                               options=opts.ContextOptions(video_audio='reference'))
        resample = media.comfy.audio.resample
        for rate, count in ((44100,39),(48000,39),(44100,90),(48000,90)):
            reference = refs.MediaRef('continue_video','v','v.mp4',length_f=count)
            wave = torch.ones(2,rate*6)
            with self.subTest(rate=rate),patch.object(media.video_end,'tail_frames',return_value='images'), \
                 patch.object(media,'input_path',return_value='v.mp4'), \
                 patch.object(media.nodes_audio,'load',return_value=(wave,rate)), \
                 patch.object(media.comfy.audio,'resample',wraps=resample) as convert:
                _,audio = media.load(reference,item,SimpleNamespace(audio_sample_rate=32000))
            self.assertEqual(audio['waveform'].shape,(1,2,round(count/24*32000)))
            self.assertEqual(audio['sample_rate'],32000)
            convert.assert_called_once()
            self.assertEqual(convert.call_args.args[0].shape[-1],round(count/24*rate))

    def test_known_video_prefix_and_existing_audio_mask_are_preserved(self):
        video = torch.zeros(1,24,42,4,4)
        audio = torch.ones(1,32,2,235)
        sound_mask = torch.zeros_like(audio)
        target = {'samples':NestedTensor((video,audio)),
                  'noise_mask':NestedTensor((torch.ones_like(video),sound_mask))}
        prefix = torch.full((1,24,12,4,4),.3)
        result = held.hold_prefix(target,[[None,{'minimax_keyframes':[{'resolved_frame_index':0,'latent':prefix}]}]])
        self.assertTrue(torch.equal(result['samples'].unbind()[0][:,:,:12],prefix))
        self.assertTrue(torch.all(result['samples'].unbind()[0][:,:,12:]==0))
        self.assertTrue(torch.all(result['noise_mask'].unbind()[0][:,:,:12]==0))
        self.assertTrue(torch.all(result['noise_mask'].unbind()[0][:,:,12:]==1))
        self.assertIs(result['noise_mask'].unbind()[1],sound_mask)
        self.assertTrue(torch.all(video==0),'preparation must not mutate a reused target latent')
