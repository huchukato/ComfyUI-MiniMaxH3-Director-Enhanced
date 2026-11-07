import unittest

from _pack import comfy_available, module

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    from comfy.nested_tensor import NestedTensor

chunks = module("ng.core.chunks")
conditioning = module("ng.adapters.conditioning")
latents = module("ng.adapters.latents")


def av(frames, h=4, w=4, seed=0):
    gen = torch.Generator().manual_seed(seed)
    video = torch.randn(1, 24, ((frames - 5) // 17) * 5 + 2, h, w, generator=gen)
    audio = torch.randn(1, 32, 2, round(frames / 24.0 * 40), generator=gen)
    return {"samples": NestedTensor((video, audio))}


def cond(existing=None):
    extra = {"minimax_keyframes": existing} if existing else {}
    return [[torch.zeros(1, 4, 8), extra]]


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class Pin(unittest.TestCase):
    def test_first_chunk_and_none_pass_through(self):
        c = cond()
        self.assertEqual(conditioning.pin_previous(c, av(124), None, chunks.ContinuityPlan("video_audio")), (c, 0, ()))
        self.assertEqual(conditioning.pin_previous(c, av(124), av(124), chunks.ContinuityPlan("none")), (c, 0, ()))

    def test_picture_only_has_no_audio_rows(self):
        out, trim, _ = conditioning.pin_previous(cond(), av(124), av(124, seed=1), chunks.ContinuityPlan("video", 22, 24))
        keyframes = out[0][1]["minimax_keyframes"]
        self.assertEqual(trim, 22)
        self.assertEqual(len(keyframes), 7)
        self.assertTrue(all("audio_latent" not in k for k in keyframes))

    def test_every_window_cuts_the_right_number_of_steps(self):
        for window, steps in ((5, 2), (22, 7), (39, 12), (56, 17)):
            out, trim, _ = conditioning.pin_previous(cond(), av(192), av(192, seed=2), chunks.ContinuityPlan("video_audio", window, 24))
            blocks = [k for k in out[0][1]["minimax_keyframes"] if "latent" in k]
            self.assertEqual((len(blocks), trim), (steps, window))

    def test_anchor_inside_the_head_is_dropped_and_reported(self):
        existing = [{"resolved_frame_index": 0, "latent": torch.zeros(1, 24, 1, 4, 4)},
                    {"resolved_frame_index": 100, "latent": torch.zeros(1, 24, 1, 4, 4)}]
        out, _, dropped = conditioning.pin_previous(cond(existing), av(124), av(124, seed=3), chunks.ContinuityPlan("video", 22, 24))
        self.assertEqual(dropped, (0,))
        kept = [k["resolved_frame_index"] for k in out[0][1]["minimax_keyframes"]]
        self.assertIn(100, kept)
        self.assertEqual(kept.count(0), 1)

    def test_input_conditioning_is_not_modified(self):
        original = cond()
        conditioning.pin_previous(original, av(124), av(124, seed=4), chunks.ContinuityPlan("video_audio"))
        self.assertEqual(original[0][1], {})

    def test_changed_resolution_names_both_sizes(self):
        with self.assertRaises(ValueError) as e:
            conditioning.pin_previous(cond(), av(124, h=4, w=4), av(124, h=6, w=4), chunks.ContinuityPlan("video"))
        self.assertIn("64x96", str(e.exception))
        self.assertIn("64x64", str(e.exception))

    def test_plain_latent_is_refused(self):
        with self.assertRaises(ValueError):
            latents.split_av({"samples": torch.zeros(1, 4, 8, 8)})


if __name__ == "__main__":
    unittest.main()
