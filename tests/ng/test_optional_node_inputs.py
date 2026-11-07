"""Optional values through ComfyUI's real V3 input preparation and execution."""
import asyncio
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from _pack import comfy_available, load_full_pack


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class OptionalInputContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pack = load_full_pack()
        cls.nodes = pack.NODE_CLASS_MAPPINGS
        cls.packet_module = importlib.import_module(pack.__name__ + ".ng.adapters.director_packets")
        cls.context_module = importlib.import_module(pack.__name__ + ".ng.core.context")
        cls.project_module = importlib.import_module(pack.__name__ + ".ng.core.project")
        cls.chunks_module = importlib.import_module(pack.__name__ + ".ng.core.chunks")
        cls.issues_module = importlib.import_module(pack.__name__ + ".ng.core.issues")
        from comfy_api.latest import _io
        import execution
        cls.io, cls.execution = _io, execution
        cls.packet = cls.packet_module.DirectorInputs(["clip", 0], ["vae", 0], ["audio", 0],
                                                     ["fl", 0], ["ref", 0], (), None)

    def values(self):
        return dict(idea="A baker opens a shop.", shots="", project_seconds=8.0, chunk_seconds=5.0,
                    width=384, height=576, mode="auto", continuity="video_audio", pin_frames="22",
                    soundscape="Wind", music="N/A", style="None", seed=123, steps=8,
                    sampler_name="res_multistep", scheduler="simple", shift_video=12.0, shift_audio=3.0)

    def prepare_product(self, field=None, value=None):
        raw = {**self.values(), "context": ["packet_source", 0]}
        if field:
            raw[field] = ["optional_source", 0]
        outputs = {"packet_source": self.packet, "optional_source": value}
        cache = SimpleNamespace(get_cache=lambda source, target: SimpleNamespace(outputs=[[outputs[source]]]))
        inputs, missing, v3 = self.execution.get_input_data(raw, self.nodes["NGH3Director"], "director", execution_list=cache)
        self.assertFalse(missing)
        return inputs, v3

    def execute_product(self, field=None, value=None):
        inputs, v3 = self.prepare_product(field, value)
        result = asyncio.run(self.execution._async_map_node_over_list(
            "optional-test", "director", self.nodes["NGH3Director"], inputs, "execute", v3_data=v3))
        return result[0].args[0]

    def test_linked_none_optional_strings_plan_as_empty_text(self):
        for field in ("prepend_text", "prompt_override"):
            with self.subTest(field=field):
                inputs, v3 = self.prepare_product(field, None)
                self.assertEqual(inputs[field], [None])
                nested = self.io.build_nested_inputs({key: value[0] for key, value in inputs.items()}, v3)
                self.assertIsNone(nested[field])
                result = self.execute_product(field, None)
                self.assertEqual(getattr(result.project.context, field), "")
                self.assertTrue(all("baker" in item.prompt.lower() for item in result.project.compiled))

    def test_omitted_optional_strings_are_absent_and_plan_normally(self):
        inputs, _ = self.prepare_product()
        self.assertNotIn("prepend_text", inputs)
        self.assertNotIn("prompt_override", inputs)
        self.assertEqual(self.execute_product().project.context.prepend_text, "")

    def test_valid_strings_and_manual_prompt_are_preserved(self):
        self.assertEqual(self.execute_product("prepend_text", "LoRA trigger.").project.context.prepend_text, "LoRA trigger.")
        self.assertTrue(all(item.prompt == "Exact manual prompt." for item in
                            self.execute_product("prompt_override", "Exact manual prompt.").project.compiled))
        self.assertEqual(self.execute_product("prompt_override", "").project.context.prompt_override, "")

    def test_invalid_optional_values_are_not_converted_to_empty_text(self):
        for field in ("prepend_text", "prompt_override"):
            for value in (0, False, 42, []):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(self.issues_module.SchemaError, "expected text"):
                    self.execute_product(field, value)

    def test_required_style_keeps_its_type_contract(self):
        with self.assertRaisesRegex(self.issues_module.SchemaError, "style: expected text, got NoneType"):
            self.execute_product("style", None)

    def test_invalid_core_model_is_rejected_before_compiling(self):
        # prepend_text and prompt_override are optional inputs: None from a bypassed node means empty (BUG-062).
        for field in ("style",):
            context = self.context_module.DirectorContext(idea="A baker opens a shop.", **{field: None})
            with self.subTest(field=field), patch.object(self.project_module, "compile_chunk") as compiler:
                with self.assertRaisesRegex(self.issues_module.SchemaError, "expected text"):
                    self.project_module.plan_project(context, 5, self.chunks_module.ContinuityPlan())
                compiler.assert_not_called()

    def studio(self, extra):
        node = self.nodes["NGDirectorStudio"]
        raw = {**self.values(), "clip": ["clip", 0], "vae": ["vae", 0], "audio_vae": ["audio", 0],
               "model_fl2va": ["fl", 0], "model_ref2va": ["ref", 0], **extra}
        inputs, missing, v3 = self.execution.get_input_data(raw, node, "studio")
        self.assertFalse(missing)
        nested = self.io.build_nested_inputs({key: value[0] for key, value in inputs.items()}, v3)
        result = asyncio.run(self.execution._async_map_node_over_list(
            "optional-test", "studio", node, inputs, "execute", v3_data=v3))[0]
        planning = next(item for item in result.expand.values() if item["class_type"] == "NGDirector")["inputs"]
        return nested, planning, v3

    def test_unwired_and_none_autogrow_groups_are_empty_before_studio_execution(self):
        for extra in ({}, {"contexts": None}):
            with self.subTest(extra=extra):
                nested, planning, v3 = self.studio(extra)
                self.assertEqual(nested["contexts"], {})
                self.assertEqual(self.io.build_nested_inputs({"contexts": None}, v3)["contexts"], {})
                self.assertFalse(any(key.startswith("contexts.") for key in planning))

    def test_connected_autogrow_preserves_its_raw_context_link(self):
        nested, planning, _ = self.studio({"contexts.context_0": ["subject", 0]})
        self.assertEqual(nested["contexts"], {"context_0": ["subject", 0]})
        self.assertEqual(planning["contexts.context_0"], ["subject", 0])


if __name__ == "__main__":
    unittest.main()
