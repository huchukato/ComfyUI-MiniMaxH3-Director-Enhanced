"""A turbo LoRA's pieces that do not fit the model are left out, not logged 51 times per step (user log, 2026-10-11)."""
import types
import unittest

from _pack import module

fit = module("ng.adapters.lora_fit")


class Shape:
    def __init__(self, *shape):
        self.shape = shape


class LoRAAdapter:          # the name is what lora_fit checks, as in comfy.weight_adapter.lora
    def __init__(self, up, down):
        self.weights = (Shape(*up), Shape(*down), None, None, None, None)


def model():
    linear = types.SimpleNamespace(weight=Shape(96768, 8))          # pruned H3 AdaLN: input 8
    qkv = types.SimpleNamespace(weight=Shape(21504, 5376))
    block = types.SimpleNamespace(adaln_proj=types.SimpleNamespace(linear=linear), attn=types.SimpleNamespace(qkv_proj=qkv))
    return types.SimpleNamespace(diffusion_model=types.SimpleNamespace(blocks=[block]), **{})


class LoraFit(unittest.TestCase):
    def test_full_model_adaln_pieces_are_left_out_on_a_pruned_model(self):
        m = model()
        m.diffusion_model.blocks = types.SimpleNamespace(**{"0": m.diffusion_model.blocks[0]})
        loaded = {"diffusion_model.blocks.0.adaln_proj.linear.weight": LoRAAdapter((96768, 16), (16, 2688)),   # ckpt500, not pruned
                  "diffusion_model.blocks.0.attn.qkv_proj.weight": LoRAAdapter((21504, 12), (12, 5376))}
        keep, left_out = fit.fitting(m, loaded)
        self.assertEqual(list(keep), ["diffusion_model.blocks.0.attn.qkv_proj.weight"])
        self.assertEqual(left_out, ["diffusion_model.blocks.0.adaln_proj.linear.weight"])

    def test_fitting_pieces_and_other_patch_kinds_stay(self):
        m = model()
        m.diffusion_model.blocks = types.SimpleNamespace(**{"0": m.diffusion_model.blocks[0]})
        loaded = {"diffusion_model.blocks.0.adaln_proj.linear.weight": LoRAAdapter((96768, 16), (16, 8)),      # hmmotion: fits
                  ("diffusion_model.blocks.0.attn.qkv_proj.weight", (0, 0, 1)): ("diff", (None,)),               # not a plain LoRA
                  "diffusion_model.unknown.weight": LoRAAdapter((4, 2), (2, 4))}                                 # not in the model
        keep, left_out = fit.fitting(m, loaded)
        self.assertEqual((len(keep), left_out), (3, []))


if __name__ == "__main__":
    unittest.main()
