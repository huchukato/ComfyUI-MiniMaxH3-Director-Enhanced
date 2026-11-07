"""Real ComfyUI contracts for the Connector → Director → Output product path."""
import unittest

from _pack import comfy_available, load_full_pack


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class ProductNodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_full_pack().NODE_CLASS_MAPPINGS

    def packet(self):
        provider = self.nodes["NGAIProvider"].execute(source="local", provider="custom", base_url="http://127.0.0.1:18319",
                                                     model="mock", api_key_env="", vision=True, audio=False,
                                                     timeout_seconds=90, max_tokens=256, keep_alive=30,
                                                     clip=["clip", 0]).args[0]
        text = self.nodes["NGContextText"].execute(text="Slow camera.", name="Camera", description="",
                                                 content="rules", usage="rule", preserve="high").args[0]
        return self.nodes["NGContextConnector"].execute(clip=["clip", 0], vae=["vae", 0], audio_vae=["audio", 0],
                                                        model_fl2va=["fl", 0], model_ref2va=["ref", 0], ai_provider=provider,
                                                        context_text={"text_0": text}).args[0]

    def result(self):
        return self.nodes["NGH3Director"].execute(context=self.packet(), idea="A baker opens a shop.", shots="",
                                                 project_seconds=8.0, chunk_seconds=5.0, width=384, height=576,
                                                 mode="auto", continuity="video_audio", pin_frames="22",
                                                 soundscape="Wind", music="N/A", seed=123, steps=8,
                                                 sampler_name="res_multistep", scheduler="simple",
                                                 shift_video=12.0, shift_audio=3.0).args[0]

    def test_ai_loader_takes_an_optional_clip_and_keeps_its_panel_settings(self):
        schema = self.nodes["NGAIProvider"].GET_SCHEMA()
        clip = {value.id: value for value in schema.inputs}["clip"]
        self.assertEqual(clip.io_type, "CLIP")
        self.assertTrue(clip.optional, "the AI Loader must work without a CLIP")
        self.assertTrue(clip.rawLink, "a loader link must not evaluate the CLIP on its own")
        self.assertTrue(clip.lazy)
        for name in ("source", "timeout_seconds", "max_tokens", "keep_alive"):
            self.assertIn(name, {value.id for value in schema.inputs})
        config = self.nodes["NGAIProvider"].execute(source="local", provider="ollama", base_url="", model="qwen2.5vl:7b",
                                                    api_key_env="", vision=True, audio=False, timeout_seconds=45,
                                                    max_tokens=256, keep_alive=60).args[0]
        self.assertEqual((config.timeout_seconds, config.max_tokens, config.keep_alive), (45, 256, 60))
        self.assertNotIn("source", config.to_dict(), "the card choice is panel state, not provider configuration")

    def test_registered_schemas_have_native_model_ports_and_distinct_ai_type(self):
        connector = self.nodes["NGContextConnector"].GET_SCHEMA()
        inputs = {value.id: value for value in connector.inputs}
        for name in ("model_fl2va", "model_ref2va", "clip", "vae", "audio_vae", "preview_vae"):
            self.assertTrue(inputs[name].rawLink)
            self.assertTrue(inputs[name].lazy, "raw links must also be lazy to avoid evaluating both loaders")
        self.assertEqual(inputs["model_fl2va"].io_type, "MODEL")
        self.assertEqual(inputs["clip"].io_type, "CLIP")
        self.assertEqual(inputs["vae"].io_type, "VAE")
        self.assertEqual(inputs["ai_provider"].io_type, "NG_AI_PROVIDER")
        director_outputs = self.nodes["NGH3Director"].GET_SCHEMA().outputs
        self.assertEqual([value.io_type for value in director_outputs], ["NG_DIRECTOR_RESULT", "NG_CHUNK"])
        self.assertTrue(director_outputs[1].is_output_list)
        outputs = self.nodes["NGDirectorOutput"].GET_SCHEMA().outputs
        from comfy.samplers import KSampler
        self.assertEqual([value.io_type for value in outputs],
                         ["MODEL", "CONDITIONING", "CONDITIONING", "LATENT", "FLOAT", "INT", "INT", "STRING", "NG_DIRECTOR_RESULT", "INT",
                          "INT", "FLOAT", KSampler.SAMPLERS, KSampler.SCHEDULERS, "SAMPLER", "SIGMAS", "VAE"])

    def test_media_contexts_load_files_directly_without_external_media_ports(self):
        for media in ("image", "video", "audio"):
            schema = self.nodes["NGContext" + media.title()].GET_SCHEMA()
            inputs = {value.id:value for value in schema.inputs}
            self.assertEqual(inputs[media].io_type, "COMBO")
            self.assertIsNotNone(inputs[media].upload)
            self.assertFalse({"IMAGE", "VIDEO", "AUDIO"} & {value.io_type for value in schema.inputs})
            self.assertNotIn("source_revision", inputs)
        self.assertNotIn("NGHTTPContextAnalysis", self.nodes)

    def test_context_groups_reject_wrong_media_and_models_are_not_evaluated(self):
        packet = self.packet()
        self.assertEqual(packet.model_fl2va, ["fl", 0])
        self.assertEqual(packet.model_ref2va, ["ref", 0])
        self.assertEqual(packet.contexts[0].name, "Camera")
        self.assertEqual(packet.ai_provider.model, "mock")
        with self.assertRaisesRegex(ValueError, "image Context"):
            self.nodes["NGContextConnector"].execute(clip=["c", 0], vae=["v", 0], audio_vae=["a", 0],
                                                      model_fl2va=["m", 0], context_image={"image_0": packet.contexts[0]})
        with self.assertRaisesRegex(ValueError, "Connect an H3 model"):
            self.nodes["NGContextConnector"].execute(clip=["c", 0], vae=["v", 0], audio_vae=["a", 0])

    def test_output_prepares_selected_chunk_and_zeroes_negative_without_sampling(self):
        result = self.result()
        self.assertEqual(len(result.project.plan.chunks), 2)
        output = self.nodes["NGDirectorOutput"].execute(result=result, chunk_index=1, previous=["previous", 0])
        kinds = {value["class_type"]: value for value in output.expand.values()}
        conditioning = kinds["NGChunkConditioning"]["inputs"]
        self.assertEqual(conditioning["chunk"].index, 1)
        self.assertEqual(conditioning["previous"], ["previous", 0])
        self.assertEqual(conditioning["model_fl2va"], ["fl", 0])
        self.assertIn("ConditioningZeroOut", kinds)
        self.assertNotIn("SamplerCustomAdvanced", kinds)
        self.assertEqual(output.args[4:7], (24.0, 384, 576))
        self.assertIs(output.args[8], result)
        with self.assertRaisesRegex(ValueError, "Choose a chunk"):
            self.nodes["NGDirectorOutput"].execute(result=result, chunk_index=2)

    def test_sequence_keeps_native_loop_and_all_planned_chunks(self):
        result = self.result()
        chunks = self.nodes["NGProjectChunks"].execute(sequence=result).args[0]
        self.assertEqual([chunk.index for chunk in chunks], [0, 1])
        render = self.nodes["NGProjectRender"].execute(sequence=result)
        kinds = {value["class_type"]: (key, value) for key, value in render.expand.items()}
        start = kinds["StartLoop"][1]
        self.assertEqual(start["_loop_end"], kinds["EndLoop"][0])
        self.assertIn(kinds["SamplerCustomAdvanced"][0], start["_loop_body"])
        self.assertEqual(kinds["NGChunkConditioning"][1]["inputs"]["previous"], [kinds["StartLoop"][0], 4])
        self.assertEqual(len(render.args), 4)
        from comfy_execution.graph_utils import is_link
        for value in render.expand.values():
            for input_value in value["inputs"].values():
                if is_link(input_value):
                    self.assertIn(input_value[0], set(render.expand) | {"clip", "vae", "audio", "fl", "ref"})
        chunk_id = kinds["NGProjectChunks"][0]
        self.assertEqual(start["inputs"]["mode.list"], [chunk_id, 0])


if __name__ == "__main__":
    unittest.main()
