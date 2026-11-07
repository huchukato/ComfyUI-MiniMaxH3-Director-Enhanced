"""Turbo is the official H3 recipe: a few-step LoRA on the model, nothing else changes in the graph."""
import json
import unittest

from _pack import comfy_available, load_full_pack
import test_product_nodes


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class Turbo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_full_pack().NODE_CLASS_MAPPINGS
        cls.helper = test_product_nodes.ProductNodes()
        cls.helper.nodes = cls.nodes

    def result(self, **turbo):
        director = self.nodes["NGH3Director"]
        values = dict(context=self.helper.packet(), idea="A baker opens a shop.", shots="", project_seconds=8.0,
                      chunk_seconds=5.0, width=384, height=576, mode="auto", continuity="video_audio", pin_frames="22",
                      soundscape="Wind", music="N/A", seed=123, steps=4, sampler_name="res_multistep",
                      scheduler="simple", shift_video=12.0, shift_audio=3.0, **turbo)
        return director.execute(**values).args[0]

    def loras(self, expand):
        return {value["inputs"]["model"][0]: value["inputs"]["lora_name"]
                for value in expand.values() if value["class_type"] == "NGTurboLora"}

    def test_director_offers_turbo_after_every_earlier_widget(self):
        names = [item.id for item in self.nodes["NGH3Director"].GET_SCHEMA().inputs]
        start = names.index("turbo")
        self.assertEqual(names[start:start + 3], ["turbo", "turbo_lora_fl2va", "turbo_lora_ref2va"])
        self.assertEqual(names[start - 1], "shift_audio")
        combo = self.nodes["NGH3Director"].GET_SCHEMA().inputs[start + 2]
        self.assertEqual(combo.options[0], "none")

    def test_the_lora_of_the_other_model_is_not_checked_against_the_folder(self):
        # ComfyUI skips its list check for inputs named in validate_inputs; an absent LoRA fails only where it is loaded
        import inspect
        director = self.nodes["NGH3Director"]
        self.assertTrue({"turbo_lora_fl2va", "turbo_lora_ref2va"} <= set(inspect.getfullargspec(director.validate_inputs).args))
        self.assertIs(director.validate_inputs(turbo_lora_fl2va="not_here.safetensors"), True)
        with self.assertRaisesRegex(FileNotFoundError, "Turbo LoRA not installed: not_here.safetensors"):
            self.nodes["NGTurboLora"].execute(model=None, lora_name="not_here.safetensors", strength=1.0)

    def test_no_turbo_lora_is_preset_the_user_chooses(self):
        from unittest.mock import patch
        product = __import__("mmxd_pack.ng.nodes.product_director_node", fromlist=["turbo_inputs"])
        names = ["minimax-h3/minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors",
                 "minimax-h3/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"]
        with patch.object(product.folder_paths, "get_filename_list", return_value=names):
            inputs = {item.id: item for item in product.turbo_inputs()}
        self.assertEqual((inputs["turbo_lora_fl2va"].default, inputs["turbo_lora_ref2va"].default), ("none", "none"))

    def test_render_sequence_puts_each_lora_on_its_own_model(self):
        result = self.result(turbo=True, turbo_lora_fl2va="fl.safetensors", turbo_lora_ref2va="ref.safetensors")
        render = self.nodes["NGProjectRender"].execute(sequence=result)
        self.assertEqual(self.loras(render.expand), {"fl": "fl.safetensors", "ref": "ref.safetensors"})
        conditioning = next(v for v in render.expand.values() if v["class_type"] == "NGChunkConditioning")["inputs"]
        lora_ids = {key for key, value in render.expand.items() if value["class_type"] == "NGTurboLora"}
        self.assertEqual({conditioning["model_fl2va"][0], conditioning["model_ref2va"][0]}, lora_ids)
        # steps, sampler and scheduler are chosen per part (NGChunkSampling); unknown LoRAs keep the Director's own
        sampling = next(v for v in render.expand.values() if v["class_type"] == "NGChunkSampling")["inputs"]
        self.assertEqual(json.loads(sampling["settings"])["steps"], 4)

    def test_off_or_none_adds_no_lora(self):
        for turbo in ({}, {"turbo": False, "turbo_lora_fl2va": "fl.safetensors"}, {"turbo": True, "turbo_lora_fl2va": "none", "turbo_lora_ref2va": "none"}):
            with self.subTest(turbo=turbo):
                render = self.nodes["NGProjectRender"].execute(sequence=self.result(**turbo))
                self.assertEqual(self.loras(render.expand), {})

    def test_director_output_hands_the_turbo_model_to_an_external_sampler(self):
        result = self.result(turbo=True, turbo_lora_fl2va="fl.safetensors", turbo_lora_ref2va="none")
        output = self.nodes["NGDirectorOutput"].execute(result=result, chunk_index=0)
        self.assertEqual(self.loras(output.expand), {"fl": "fl.safetensors"})
        conditioning = next(v for v in output.expand.values() if v["class_type"] == "NGChunkConditioning")["inputs"]
        self.assertEqual(conditioning["model_ref2va"], ["ref", 0])


if __name__ == "__main__":
    unittest.main()
