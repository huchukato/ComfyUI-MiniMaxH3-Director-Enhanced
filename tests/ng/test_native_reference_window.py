"""A reference video reaches the native node with its paired soundtrack cut to the same span.

The stock node cuts a reference video down to the 17k+5 grid but keeps the whole soundtrack. We never patch ComfyUI, so
minimax_refprep makes the cut first and trims the soundtrack with it. These tests run the real native node behind it and must
pass on a stock ComfyUI as well as on one that already keeps the window itself."""
import importlib
import unittest

from _pack import comfy_available, load_full_pack

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch


@unittest.skipUnless(HAVE_COMFY, "ComfyUI unavailable")
class ReferenceWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pack = load_full_pack().__name__
        cls.native = importlib.import_module(pack + '.minimax_core').core()
        cls.refprep = importlib.import_module(pack + '.minimax_refprep')

    def run_reference(self, frames, audio_seconds, length=124):
        class Clip:
            def tokenize(self, prompt, **kwargs):
                self.items = kwargs['minimax_ref_items']
                return None
            def encode_from_tokens_scheduled(self, tokens):
                return [[torch.zeros(1, 1, 8), {}]]
        class VideoVAE:
            def encode(self, images):
                self.frames = images.shape[0]
                return torch.zeros(1, 24, ((self.frames + 16) // 17) * 5 - 3, 4, 4)
        class AudioVAE:
            audio_sample_rate = 32000
            def encode(self, wave):
                self.samples = wave.shape[1]
                return torch.zeros(1, 32, 2, (self.samples + 799) // 800)
        clip, video, audio = Clip(), VideoVAE(), AudioVAE()
        videos, sounds = self.refprep.grid_references(
            {'ref_video_1': torch.zeros(frames, 64, 64, 3)},
            {'ref_video_audio_1': {'waveform': torch.zeros(1, 2, 32000 * audio_seconds), 'sample_rate': 32000}},
            self.refprep.chunk_frames(length))
        out = self.native.MiniMaxH3ReferenceToVideo.execute(
            clip=self.refprep.h3_clip(clip), vae=video, audio_vae=audio, prompt='A cube moves.', width=64, height=64,
            length=length, ref_videos=videos, ref_video_audios=sounds)
        return clip, video, audio, out.args[0][0][1]['minimax_refs'][0]

    def test_72_selected_frames_keep_56_and_the_sound_matches_them(self):
        clip, video, audio, block = self.run_reference(72, 3)
        self.assertEqual(video.frames, 56)
        self.assertEqual(audio.samples, round(56 / 24 * 32000))
        self.assertEqual(clip.items[1]['data'].shape[0], 5, 'Qwen samples the kept frames at 2 fps')
        self.assertEqual(clip.items[1]['timestamps'], [0, 0.5, 1, 1.5, 2])

    def test_target_duration_limit_also_clips_the_paired_soundtrack(self):
        _, video, audio, _ = self.run_reference(158, 7)
        self.assertEqual(video.frames, 124)
        self.assertEqual(audio.samples, round(124 / 24 * 32000))

    def test_chunk_frames_match_the_native_count(self):
        for n in (1, 5, 6, 72, 124, 125, 362):
            self.assertEqual(self.refprep.chunk_frames(n), self.native.align_frame_count(max(5, n)), n)

    def test_a_short_soundtrack_is_padded_to_the_video(self):
        _, video, audio, _ = self.run_reference(124, 2)
        self.assertEqual(video.frames, 124)
        self.assertEqual(audio.samples, round(124 / 24 * 32000))


@unittest.skipUnless(HAVE_COMFY, "ComfyUI unavailable")
class QwenSizing(unittest.TestCase):
    """What the stock Qwen path makes of our pre-sized data equals what H3's released processor makes of the original."""

    @classmethod
    def setUpClass(cls):
        pack = load_full_pack().__name__
        cls.refprep = importlib.import_module(pack + '.minimax_refprep')
        from comfy.text_encoders.qwen_vl import process_qwen2vl_images
        cls.process = staticmethod(process_qwen2vl_images)

    def stock_image(self, image):
        return self.process(image, patch_size=16, image_mean=[0.5] * 3, image_std=[0.5] * 3)

    def h3_image(self, image):
        return self.process(image, min_pixels=65536, max_pixels=16777216, patch_size=16, image_mean=[0.5] * 3, image_std=[0.5] * 3)

    def test_pictures_get_the_tokens_of_the_h3_processor(self):
        torch.manual_seed(0)
        for h, w in ((64, 64), (100, 300), (256, 256), (768, 1344), (1531, 1021), (2048, 3072)):
            image = torch.rand(1, h, w, 3)
            ours, ours_grid = self.stock_image(self.refprep.qwen_picture(image))
            h3, h3_grid = self.h3_image(image)
            self.assertEqual(ours_grid.tolist(), h3_grid.tolist(), (h, w))
            self.assertTrue(torch.allclose(ours, h3, atol=1e-5), (h, w))

    def test_a_64px_reference_gets_64_tokens_not_4(self):
        _, grid = self.stock_image(self.refprep.qwen_picture(torch.rand(1, 64, 64, 3)))
        grid = grid.flatten()
        self.assertEqual(int(grid[1] * grid[2]) // 4, 64)

    def test_video_frames_follow_the_whole_reference_budget(self):
        # 30 sampled frames (15 s at 2 fps) at 1344x768: 30 x 1.03 MP is over H3's 25.2 MP video budget, so each frame shrinks.
        h, w = self.refprep.qwen_video_size(30, 768, 1344)
        self.assertLessEqual(30 * h * w, 25165824)
        self.assertEqual((h % 32, w % 32), (0, 0))
        self.assertLess(h * w, 768 * 1344)
        # two sampled frames stay at full size
        self.assertEqual(self.refprep.qwen_video_size(2, 768, 1344), (768, 1344))

    def test_items_and_frame_pictures_are_resized_audio_passes(self):
        seen = {}

        class Clip:
            def tokenize(self, text, **kwargs):
                seen.update(kwargs)
            other = 'kept'

        wrapped = self.refprep.h3_clip(Clip())
        wrapped.tokenize('p', images=[torch.rand(1, 64, 64, 3)],
                         minimax_ref_items=[{'type': 'audio'}, {'type': 'image', 'data': torch.rand(1, 64, 64, 3)},
                                            {'type': 'video', 'data': torch.rand(4, 32, 32, 3), 'timestamps': [0, .5, 1, 1.5]}])
        self.assertEqual(tuple(seen['images'][0].shape), (1, 256, 256, 3))
        self.assertEqual(seen['minimax_ref_items'][0], {'type': 'audio'})
        self.assertEqual(tuple(seen['minimax_ref_items'][1]['data'].shape), (1, 256, 256, 3))
        self.assertEqual(seen['minimax_ref_items'][2]['timestamps'], [0, .5, 1, 1.5])
        self.assertEqual(wrapped.other, 'kept')
        self.assertIs(self.refprep.h3_clip(wrapped), wrapped)



@unittest.skipUnless(HAVE_COMFY, "ComfyUI unavailable")
class FramesWithReferences(unittest.TestCase):
    """fl2va with First / Last frame plus a reference picture (ng.core.fl2va_refs): the frames come first for Qwen, both
    payloads reach the DiT."""

    @classmethod
    def setUpClass(cls):
        pack = load_full_pack().__name__
        cls.native = importlib.import_module(pack + '.minimax_core').core()
        cls.builder = importlib.import_module(pack + '.ng.adapters.chunk_builder')

    def test_frames_then_references(self):
        seen = {}

        class Clip:
            def tokenize(self, prompt, **kwargs):
                seen.update(kwargs)
            def encode_from_tokens_scheduled(self, tokens):
                return [[torch.zeros(1, 1, 8), {}]]

        class VideoVAE:
            def encode(self, images):
                return torch.full((1, 24, 1, images.shape[1] // 16, images.shape[2] // 16), float(images.shape[1]))

        first, last, sheet = torch.zeros(1, 64, 64, 3), torch.ones(1, 64, 64, 3), torch.rand(1, 96, 128, 3)
        cond, latent = self.builder._frames_with_references(self.native, 'p', Clip(), VideoVAE(), 64, 64, 124, first, last, [sheet], 'match')
        values = cond[0][1]
        self.assertEqual([k['resolved_frame_index'] for k in values['minimax_keyframes']], [0, 123])
        self.assertEqual([(b['kind'], b['latent_h'], b['latent_w']) for b in values['minimax_refs']], [('image', 4, 4)], 'sized like MiniMaxH3ReferenceToVideo (match)')
        items = seen['minimax_ref_items']
        self.assertEqual([i['type'] for i in items], ['image'] * 3)
        self.assertEqual(float(items[1]['data'].mean()), 1.0, 'the last frame is <Picture 2>, the reference follows')
        self.assertEqual(tuple(items[2]['data'].shape)[1:3], (256, 256), 'Qwen gets the reference at H3 size (64 tokens minimum)')
        self.assertEqual(latent['samples'].unbind()[0].shape[2], 37, '124 frames = 37 latent steps')

    def test_references_without_frames(self):
        class Clip:
            def tokenize(self, prompt, **kwargs):
                return None
            def encode_from_tokens_scheduled(self, tokens):
                return [[torch.zeros(1, 1, 8), {}]]

        class VideoVAE:
            def encode(self, images):
                return torch.zeros(1, 24, 1, images.shape[1] // 16, images.shape[2] // 16)

        cond, _ = self.builder._frames_with_references(self.native, 'p', Clip(), VideoVAE(), 64, 64, 124, None, None,
                                                       [torch.rand(1, 64, 64, 3)], 'match')
        self.assertNotIn('minimax_keyframes', cond[0][1])
        self.assertEqual(len(cond[0][1]['minimax_refs']), 1)


if __name__ == '__main__':
    unittest.main()
