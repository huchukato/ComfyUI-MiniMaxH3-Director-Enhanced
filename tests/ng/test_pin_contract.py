"""Contract between NG's pin arithmetic and the Core's real H3 layout.

If ComfyUI ever changes how keyframe rows are placed, these fail instead of the join landing at the wrong instant.
Skipped (loudly) when ComfyUI cannot be imported; run with the ComfyUI embedded interpreter.
"""
import unittest

from _pack import comfy_available, module

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    from comfy.nested_tensor import NestedTensor
    mm = __import__("comfy.ldm.minimax.model", fromlist=["x"])

chunks = module("ng.core.chunks")
conditioning = module("ng.adapters.conditioning")
latents = module("ng.adapters.latents")

TEXT_LEN = 6
H = W = 4


def clip_latent(frames, seed=0):
    video_steps = ((frames - 5) // 17) * 5 + 2
    audio_steps = round(frames / 24.0 * 40)
    gen = torch.Generator().manual_seed(seed)
    video = torch.randn(1, 24, video_steps, H, W, generator=gen)
    audio = torch.randn(1, 32, 2, audio_steps, generator=gen)
    return {"samples": NestedTensor((video, audio))}


def segment(layout, kind):
    return [(a, b) for a, b, k in layout.segments if k == kind]


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable; the layout contract was NOT checked")
class Contract(unittest.TestCase):
    def setUp(self):
        self.previous = clip_latent(124, seed=1)
        self.current = clip_latent(124, seed=2)
        self.cont = chunks.ContinuityPlan("video_audio", 22, 24)
        cond, self.trim, dropped = conditioning.pin_previous([[torch.zeros(1, TEXT_LEN, 8), {}]], self.current, self.previous, self.cont)
        self.assertEqual(dropped, ())
        self.keyframes = cond[0][1]["minimax_keyframes"]
        video, audio = latents.split_av(self.current)
        self.layout = mm.PackedLayout(TEXT_LEN, video.shape[2], H, W, audio.shape[-1], keyframes=self.keyframes)

    def test_trim_is_the_pinned_span(self):
        self.assertEqual(self.trim, 22)

    def test_pinned_picture_rows_sit_exactly_on_the_first_target_steps(self):
        rows = self.layout.position_ids
        cond = segment(self.layout, "cond")
        target_start, target_stop = segment(self.layout, "video")[0]
        per_step = (target_stop - target_start) // 37
        self.assertEqual(len(cond), 7)
        for k, (a, _b) in enumerate(cond):
            self.assertAlmostEqual(float(rows[a, 0]), float(rows[target_start + k * per_step, 0]), places=9, msg="step %d" % k)

    def test_pinned_sound_ends_on_the_target_audio_grid_at_the_join(self):
        rows = self.layout.position_ids
        (a, b), = segment(self.layout, "cond_audio")
        steps = (b - a) // 2
        self.assertEqual(steps, 40)
        times = rows[a:a + steps, 0]
        target_audio_start = float(rows[segment(self.layout, "audio")[0][0], 0])
        end = float(times[-1]) + 1.0 - target_audio_start
        self.assertAlmostEqual(end, round(end), places=9)
        self.assertAlmostEqual(end, 22 * 5.0 / 3.0, delta=1.0)
        self.assertTrue(all(abs(float(t) - round(float(t))) < 1e-9 for t in times))

    def test_pinned_content_is_the_previous_tail(self):
        video, audio = latents.split_av(self.previous)
        pinned = [k["latent"] for k in self.keyframes if "latent" in k]
        self.assertTrue(torch.equal(torch.cat(pinned, 2), video[:1, :, -7:]))
        tail = [k["audio_latent"] for k in self.keyframes if "audio_latent" in k][0]
        self.assertTrue(torch.equal(tail, audio[:1, ..., -40:]))


if __name__ == "__main__":
    unittest.main()
