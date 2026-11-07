"""Regression test for BUG-062: NGH3Director and compiler crash on None optional inputs.

When ComfyUI executes nodes with optional inputs that are unwired, bypassed, or
connected to nodes producing None, ComfyUI passes kwargs with value None
(e.g. prompt_override=None, prepend_text=None).

In ng/nodes/product_director_node.py:60-61:
    prepend_text=values.get("prepend_text", "")
    prompt_override=values.get("prompt_override", "")
Because the keys exist in values, values.get(key, "") evaluates to None instead of "".
This passes prompt_override=None and prepend_text=None into DirectorContext.
When plan_project executes, _prepare() runs DirectorContext.from_dict(), where
fields.read_str raises:
    SchemaError: director.prompt_override: expected text, got NoneType
    SchemaError: director.prepend_text: expected text, got NoneType
Furthermore, ng/core/compile.py:91/123/134 calls context.prompt_override.strip(),
which raises AttributeError: 'NoneType' object has no attribute 'strip'.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NG_TESTS = os.path.dirname(HERE)
if NG_TESTS not in sys.path:
    sys.path.insert(0, NG_TESTS)

from _pack import comfy_available, load_full_pack, module

compile_mod = module("ng.core.compile")
ctx_mod = module("ng.core.context")
chunks_mod = module("ng.core.chunks")


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class TestBug062DirectorOptionalNoneInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_full_pack()
        cls.nodes = cls.pack.NODE_CLASS_MAPPINGS
        provider = cls.nodes["NGAIProvider"].execute(
            source="local", provider="custom", base_url="http://127.0.0.1:18319",
            model="mock", api_key_env="", vision=True, audio=False,
            timeout_seconds=90, max_tokens=256, keep_alive=30, clip=["clip", 0]
        ).args[0]
        text = cls.nodes["NGContextText"].execute(
            text="Slow camera.", name="Camera", description="",
            content="rules", usage="rule", preserve="high"
        ).args[0]
        cls.context_packet = cls.nodes["NGContextConnector"].execute(
            clip=["clip", 0], vae=["vae", 0], audio_vae=["audio", 0],
            model_fl2va=["fl", 0], model_ref2va=["ref", 0], ai_provider=provider,
            context_text={"text_0": text}
        ).args[0]

    def _base_kwargs(self):
        return dict(
            context=self.context_packet,
            idea="A baker opens a shop.",
            shots="",
            project_seconds=8.0,
            chunk_seconds=5.0,
            width=384,
            height=576,
            mode="auto",
            continuity="video_audio",
            pin_frames="22",
            soundscape="Wind",
            music="N/A",
            seed=123,
            steps=8,
            sampler_name="res_multistep",
            scheduler="simple",
            shift_video=12.0,
            shift_audio=3.0,
        )

    # ------------------ GREEN CONTROLS ------------------

    def test_control_empty_string_prompt_override_succeeds(self):
        kwargs = self._base_kwargs()
        kwargs["prompt_override"] = ""
        kwargs["prepend_text"] = ""
        output = self.nodes["NGH3Director"].execute(**kwargs)
        self.assertIsNotNone(output)
        self.assertTrue(len(output.args) >= 2)

    def test_control_omitted_optional_inputs_succeed(self):
        kwargs = self._base_kwargs()
        output = self.nodes["NGH3Director"].execute(**kwargs)
        self.assertIsNotNone(output)
        self.assertTrue(len(output.args) >= 2)

    def test_control_valid_prompt_override_text_compiles(self):
        kwargs = self._base_kwargs()
        kwargs["prompt_override"] = "Custom manual prompt override."
        output = self.nodes["NGH3Director"].execute(**kwargs)
        result = output.args[0]
        compiled_prompts = [chunk.prompt for chunk in result.project.compiled]
        self.assertTrue(all("Custom manual prompt override." in p for p in compiled_prompts))

    # ------------------ RED REGRESSION TESTS ------------------

    def test_bug_062_product_director_prompt_override_none_must_not_crash(self):
        """When ComfyUI supplies prompt_override=None (e.g. bypassed node or None output),

        NGH3Director.execute must coerce None to empty string and complete planning.
        """
        kwargs = self._base_kwargs()
        kwargs["prompt_override"] = None
        # On current codebase, this raises SchemaError: director.prompt_override: expected text, got NoneType
        output = self.nodes["NGH3Director"].execute(**kwargs)
        self.assertIsNotNone(output)
        self.assertTrue(len(output.args) >= 2)

    def test_bug_062_product_director_prepend_text_none_must_not_crash(self):
        """When ComfyUI supplies prepend_text=None (e.g. bypassed LoRA trigger text node),

        NGH3Director.execute must coerce None to empty string and complete planning.
        """
        kwargs = self._base_kwargs()
        kwargs["prepend_text"] = None
        # On current codebase, this raises SchemaError: director.prepend_text: expected text, got NoneType
        output = self.nodes["NGH3Director"].execute(**kwargs)
        self.assertIsNotNone(output)
        self.assertTrue(len(output.args) >= 2)

    def test_bug_062_compile_chunk_with_none_prompt_override_must_not_crash(self):
        """compile_chunk must treat context.prompt_override=None identically to empty string

        instead of crashing with AttributeError: 'NoneType' object has no attribute 'strip'.
        """
        ctx = ctx_mod.DirectorContext(idea="A baker opens a shop.", prompt_override=None)
        chunk = chunks_mod.Chunk(index=0, story_start_f=0, delivered_frames=49, head_frames=0, is_last=True)
        plan = chunks_mod.ContinuityPlan("video_audio", 22, 24)
        # On current codebase, this raises AttributeError: 'NoneType' object has no attribute 'strip'
        compiled = compile_mod.compile_chunk(ctx, chunk, plan)
        self.assertIsNotNone(compiled)
        self.assertIsInstance(compiled.prompt, str)


if __name__ == "__main__":
    unittest.main()
