"""Known turbo LoRAs bring their measured steps, sampler and scheduler to the parts of their own model (core/turbo_profiles.py)."""
import json
import types
import unittest

from _pack import comfy_available, module, stub_prompt_server

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    profiles = module("ng.core.turbo_profiles")

OWN = {"steps": 20, "sampler_name": "res_multistep", "scheduler": "simple"}
REF2V = "MiniMax-H3\\minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
CKPT500 = "minimax-h3/MINIMAX_H3_TURBO_4STEP_CKPT500_PRUNED_COMFYUI.safetensors"  # 8 steps, euler, beta


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class PartSettings(unittest.TestCase):
    def test_each_part_takes_the_profile_of_its_own_model(self):
        settings = {**OWN, "turbo": True, "turbo_lora_fl2va": CKPT500, "turbo_lora_ref2va": REF2V}
        self.assertEqual(profiles.part_settings("fl2va", settings)["steps"], 8, "any folder, any case")
        self.assertEqual(profiles.part_settings("ref2va", settings)["steps"], 6, "4 steps left a white veil (2026-10-19)")

    def test_unknown_lora_or_turbo_off_keeps_the_directors_settings(self):
        unknown = {**OWN, "turbo": True, "turbo_lora_fl2va": "my_own_turbo.safetensors"}
        self.assertEqual(profiles.part_settings("fl2va", unknown), unknown)
        off = {**OWN, "turbo": False, "turbo_lora_ref2va": REF2V}
        self.assertEqual(profiles.part_settings("ref2va", off), off)

    def test_a_text_only_part_takes_the_fl2va_loras_values(self):
        settings = {**OWN, "turbo": True, "turbo_lora_fl2va": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"}
        self.assertEqual(profiles.part_settings("t2va", settings)["steps"], 8)

    def test_every_profile_names_a_real_sampler_and_scheduler(self):
        from comfy.samplers import KSampler
        for name, entry in profiles.PROFILES.items():
            # video values, picture values ("still"), or both
            measured = [one for one in (entry, entry.get("still")) if one and "steps" in one]
            self.assertTrue(measured, name)
            for profile in measured:
                self.assertIn(profile["sampler_name"], KSampler.SAMPLERS, name)
                self.assertIn(profile["scheduler"], KSampler.SCHEDULERS, name)
                self.assertTrue(profile["source"], name)

    def test_chunk_sampling_uses_the_part_profile(self):
        stub_prompt_server()
        node = module("ng.nodes.render_node").NGChunkSampling
        calls = []
        fake_scheduler = types.SimpleNamespace(execute=lambda **kw: calls.append(kw) or types.SimpleNamespace(args=("sigmas",)))
        fake_select = types.SimpleNamespace(execute=lambda **kw: calls.append(kw) or types.SimpleNamespace(args=("sampler",)))
        render_node = module("ng.nodes.render_node")
        job = types.SimpleNamespace(compiled=types.SimpleNamespace(mode="fl2va"))
        settings = json.dumps({**OWN, "turbo": True, "turbo_lora_fl2va": CKPT500})
        original = render_node.BasicScheduler, render_node.KSamplerSelect
        render_node.BasicScheduler, render_node.KSamplerSelect = fake_scheduler, fake_select
        try:
            out = node.execute(chunk=[job], model="m", settings=settings)
        finally:
            render_node.BasicScheduler, render_node.KSamplerSelect = original
        self.assertEqual(out.args, ("sampler", "sigmas"))
        self.assertEqual(calls, [{"sampler_name": "euler"}, {"model": "m", "scheduler": "beta", "steps": 8, "denoise": 1.0}])


if __name__ == "__main__":
    unittest.main()
