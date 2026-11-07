import unittest
from types import SimpleNamespace
from unittest.mock import patch

from _pack import comfy_available, module, stub_prompt_server

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    stub_prompt_server()
    join = module("ng.adapters.continuation_join")


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class ContinuationJoin(unittest.TestCase):
    def test_reconstruction_bias_eases_out_without_freezing_motion_or_changing_tail(self):
        known = torch.full((32, 32, 3), 100 / 255)
        source = known + 20 / 255
        future = torch.stack([known + (index + 1) * 2 / 255 for index in range(10)])
        before = future.clone()
        result = join.compensate(source, known, future)
        self.assertIs(result, future)
        self.assertTrue(torch.equal(result[6:], before[6:]))
        self.assertAlmostEqual(float(result[0, 0, 0, 0]), 122 / 255, places=6)
        self.assertNotEqual(float(result[0, 0, 0, 0]), float(source[0, 0, 0]))
        self.assertGreater(float((result[0] - before[0]).mean()), float((result[5] - before[5]).mean()))

    def test_zero_residual_preserves_quantized_frames_and_short_output(self):
        known = torch.full((32, 32, 3), 100 / 255)
        future = torch.stack([known + index / 255 for index in range(10)])
        self.assertTrue(torch.equal(join.compensate(known, known, future.clone()), future))
        single = future[:1].clone()
        self.assertIs(join.compensate(known + .1, known, single), single)
        self.assertTrue(torch.equal(single, future[:1]))

    def test_source_uses_selected_range_and_native_guide_canvas(self):
        options = SimpleNamespace(start_s=2., end_s=4.)
        item = SimpleNamespace(source="source.mp4", options=options, length_s=8.)
        job = SimpleNamespace(chunk=SimpleNamespace(continuation_id="clip"),
                              project=SimpleNamespace(context=SimpleNamespace(item=lambda _: item)))
        future, known = torch.zeros(10, 32, 64, 3), torch.zeros(32, 64, 3)
        source = torch.zeros(1, 64, 64, 3)
        with patch.object(join.video_end, "tail_frames", return_value=source) as load, \
             patch.object(join.native, "_resize", return_value=known[None]) as resize, \
             patch.object(join, "compensate", return_value=future) as correct:
            self.assertIs(join.smooth(job, known, future), future)
        load.assert_called_once_with("source.mp4", 2., 4., 1)
        resize.assert_called_once_with(source, 64, 32, "center")
        self.assertIs(correct.call_args.args[2], future)


if __name__ == "__main__":
    unittest.main()
