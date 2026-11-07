"""H3 Control Video: each render part gets its own window of the control video, its pinned head included."""
import types
import unittest

from _pack import comfy_available, module

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    control = module("ng.adapters.control")
    chunks = module("ng.core.chunks")


def job(story_start, delivered, head):
    return types.SimpleNamespace(chunk=chunks.Chunk(index=1, story_start_f=story_start, delivered_frames=delivered, head_frames=head))


class FakeCore:
    def __init__(self):
        self.calls = []
        outer = self

        class Apply:
            @staticmethod
            def execute(**kw):
                outer.calls.append(kw)
                return types.SimpleNamespace(args=("patched",))
        self.MiniMaxH3FunControlNetApply = Apply


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class Window(unittest.TestCase):
    def test_a_continued_part_gets_its_head_and_new_frames(self):
        frames = torch.arange(500).float().view(500, 1, 1, 1).expand(500, 2, 2, 3)
        part = control.part_frames(frames, job(241, 221, 22))
        self.assertEqual(part.shape[0], 243)
        self.assertEqual((float(part[0, 0, 0, 0]), float(part[-1, 0, 0, 0])), (219.0, 461.0))

    def test_a_short_video_ends_before_the_part(self):
        frames = torch.zeros(100, 2, 2, 3)
        self.assertIsNone(control.part_frames(frames, job(241, 221, 22)))
        self.assertEqual(control.part_frames(frames, job(0, 243, 0)).shape[0], 100, "ComfyUI holds the last frame")

    def test_apply_passes_the_windows_and_reads_the_source_only_with_a_mask(self):
        fake, frames = FakeCore(), torch.zeros(300, 2, 2, 3)
        self.assertEqual(control.apply(fake, "model", "patch", "vae", job(0, 243, 0), 1.0, 0.0, 1.0, control_video=frames,
                                       source_video=frames), "patched")
        self.assertEqual(fake.calls[-1]["control_video"].shape[0], 243)
        self.assertIsNone(fake.calls[-1]["source_video"])
        control.apply(fake, "model", "patch", "vae", job(0, 243, 0), 1.0, 0.0, 1.0, mask=torch.ones(300, 2, 2), source_video=frames)
        self.assertEqual((fake.calls[-1]["mask"].shape[0], fake.calls[-1]["source_video"].shape[0]), (243, 243))


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class MaskShape(unittest.TestCase):
    def mask(self):
        m = torch.zeros(2, 20, 30)
        m[0, 5:8, 10:12] = 1.0           # a small figure
        m[0, 12, 20] = 1.0               # a stray pixel widens the box
        return m

    def test_box_covers_the_bounding_box_plus_grow(self):
        box = control.shaped(self.mask(), "box", 2)
        ys, xs = box[0].nonzero(as_tuple=True)
        self.assertEqual((int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())), (3, 14, 8, 22))
        self.assertEqual(float(box[0, 10, 15]), 1.0, "the inside of the box is regenerated too")
        self.assertEqual(float(box[1].sum()), 0.0, "an empty frame stays empty")

    def test_outline_grows_the_shape_only(self):
        out = control.shaped(self.mask(), "outline", 1)
        self.assertEqual(float(out[0, 10, 15]), 0.0)
        self.assertEqual(float(out[0, 4, 9]), 1.0)
        self.assertTrue(torch.equal(control.shaped(self.mask(), "outline", 0), self.mask()))

    def test_apply_shapes_the_mask(self):
        fake, frames = FakeCore(), torch.zeros(300, 20, 30, 3)
        mask = torch.zeros(300, 20, 30)
        mask[:, 5:8, 10:12] = 1.0
        control.apply(fake, "m", "p", "v", job(0, 243, 0), 1.0, 0.0, 1.0, mask=mask, source_video=frames)
        # rows 5-7 and columns 10-11 grown by the default 16 px, clipped to the 20 x 30 frame: rows 0-19, columns 0-27
        self.assertEqual(float(fake.calls[-1]["mask"][0].sum()), 20.0 * 28.0)
        self.assertEqual(float(fake.calls[-1]["mask"][0, 0, 29]), 0.0)


if __name__ == "__main__":
    unittest.main()
