"""Native AI jobs consume CLIP links without pulling H3 render models into the job."""
import json
import unittest

from _pack import comfy_available, load_full_pack, module


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class NativeAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_full_pack().NODE_CLASS_MAPPINGS
        cls.adapter = module("ng.adapters.native_ai")

    def provider(self, **changes):
        values = dict(source="clip", clip=["encoder", 0], provider="ollama", base_url="", model="",
                      api_key_env="", vision=True, audio=False, timeout_seconds=120, max_tokens=256, keep_alive=0)
        values.update(changes)
        return self.nodes["NGAIProvider"].execute(**values).args[0]

    def payload(self, media="text"):
        return json.dumps({"media": media, "widgets": {media: "Slow camera and consistent lighting.", "content": "rules"}})

    def test_loader_keeps_the_actual_unevaluated_clip_link(self):
        provider = self.provider()
        self.assertEqual(provider.clip, ["encoder", 0])
        self.assertEqual(provider.config.max_tokens, 256)
        # The message has to name both ways in, since the card offers both now.
        with self.assertRaisesRegex(ValueError, "Connect Load CLIP"):
            self.provider(clip=None, local_model="")

    def test_expansion_uses_native_generate_text_and_bound_settings(self):
        self.assertTrue(self.nodes["NGAIRequest"].GET_SCHEMA().enable_expand)
        job = self.nodes["NGAIRequest"].execute(ai_provider=self.provider(), action="analyze", request_json=self.payload())
        kinds = {value["class_type"]: value["inputs"] for value in job.expand.values()}
        # Generate Text reads the clip through the encoder check, which reads the connected link.
        self.assertEqual(kinds["NGAICheckEncoder"]["clip"], ["encoder", 0])
        check = next(key for key, value in job.expand.items() if value["class_type"] == "NGAICheckEncoder")
        self.assertEqual(kinds["TextGenerate"]["clip"], [check, 0])
        self.assertEqual(kinds["TextGenerate"]["max_length"], 256)
        direct = json.dumps({"director": {"idea": "A walk.", "project_seconds": 8}, "contexts": []})
        job = self.nodes["NGAIRequest"].execute(ai_provider=self.provider(), action="direct", request_json=direct)
        self.assertEqual(next(v["inputs"]["max_length"] for v in job.expand.values() if v["class_type"] == "TextGenerate"), 2048,
                         "a shot list needs room; Auto Direct never asks for less than 2048")
        self.assertEqual(kinds["TextGenerate"]["sampling_mode"], "off")
        self.assertIn("Slow camera", kinds["TextGenerate"]["prompt"])
        self.assertIn("NGAIResult", kinds)
        self.assertNotIn("SamplerCustomAdvanced", kinds)

    def test_an_installed_encoder_uses_the_native_clip_loader_without_loading_during_config(self):
        """The encoder card has no switch any more: no Load CLIP connected means the installed
        encoder is what the request uses. It must still load lazily, inside the AI job only."""
        provider = self.provider(clip=None, source="clip", local_model="qwen3vl_4b_bf16.safetensors")
        self.assertIsNone(provider.clip)
        job = self.nodes["NGAIRequest"].execute(ai_provider=provider, action="analyze", request_json=self.payload())
        kinds = {value["class_type"]: value["inputs"] for value in job.expand.values()}
        self.assertEqual(kinds["CLIPLoader"]["clip_name"], "qwen3vl_4b_bf16.safetensors")
        self.assertEqual(kinds["CLIPLoader"]["type"], "stable_diffusion")
        # Neither a clip nor a chosen encoder: the card cannot do anything, and must say so.
        with self.assertRaisesRegex(ValueError, "Connect Load CLIP"):
            self.provider(clip=None, source="clip", local_model="")

    def test_the_h3_conditioning_encoder_is_refused_before_it_runs_into_the_timeout(self):
        """H3's 32B file has 50 of 64 layers and no output head: it ran ten minutes and wrote commas."""
        check = self.nodes["NGAICheckEncoder"]
        minimax = module("ng.adapters.native_ai")
        class MiniMaxH3TEModel: pass
        class MiniMaxH3TEModel_(MiniMaxH3TEModel): pass
        class Qwen3VLModel: pass
        class Clip:
            def __init__(self, model): self.cond_stage_model = model
        h3, qwen = Clip(MiniMaxH3TEModel_()), Clip(Qwen3VLModel())
        with self.assertRaisesRegex(ValueError, "conditioning encoder.*cannot write text"):
            check.execute(clip=h3)
        self.assertIs(check.execute(clip=qwen).args[0], qwen)
        self.assertTrue(minimax.conditioning_file("MiniMax-H3/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "stable_diffusion"))
        provider = self.provider(clip=None, local_model="qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors", local_type="minimax")
        with self.assertRaisesRegex(ValueError, "qwen3vl_4b"):
            self.nodes["NGAIRequest"].execute(ai_provider=provider, action="direct",
                                              request_json=json.dumps({"director": {"idea": "x", "project_seconds": 8}, "contexts": []}))

    def test_a_connected_clip_wins_over_a_leftover_model_name(self):
        """Choosing an encoder once and connecting Load CLIP later must not leave two candidates."""
        provider = self.provider(source="clip", local_model="qwen3vl_4b_bf16.safetensors")
        self.assertEqual(provider.clip, ["encoder", 0])
        self.assertEqual(provider.local_model, "", "the encoder is not read while a clip is connected")

    def test_asking_again_is_never_answered_from_comfyuis_cache(self):
        # The second "split into shots" with the same prompt reported "The AI job finished without a suggestion":
        # the cached request and result nodes did not run. NaN never equals itself, so ComfyUI runs them every time.
        for name, inputs in (("NGAIRequest", dict(ai_provider=None, action="direct", request_json="{}")),
                             ("NGAIResult", dict(text="{}", action="direct", request_json="{}"))):
            first, second = (self.nodes[name].fingerprint_inputs(**inputs) for _ in range(2))
            self.assertNotEqual(first, second, name)

    def test_native_ai_packet_reaches_context_and_connector_without_generation(self):
        provider = self.provider()
        text = self.nodes["NGContextText"].execute(text="Slow camera.", name="Camera", description="",
                                                  content="rules", usage="rule", preserve="high", ai_provider=provider).args[0]
        packet = self.nodes["NGContextConnector"].execute(clip=["h3_clip", 0], vae=["vae", 0], audio_vae=["audio", 0],
                                                         model_fl2va=["fl2va", 0], ai_provider=provider,
                                                         context_text={"text_0": text}).args[0]
        self.assertIs(packet.ai_provider, provider)
        self.assertEqual(packet.clip, ["h3_clip", 0])
        self.assertEqual(provider.clip, ["encoder", 0], "AI and H3 conditioning must remain independent")

    def test_media_capabilities_and_response_validation_are_enforced(self):
        for media, options in (("image", {"vision": False}), ("audio", {"audio": False})):
            with self.subTest(media=media), self.assertRaisesRegex(ValueError, "is off on the H3 AI Loader"):
                self.nodes["NGAIRequest"].execute(ai_provider=self.provider(**options), action="analyze", request_json=self.payload(media))
        with self.assertRaises(ValueError):
            self.nodes["NGAIResult"].execute(text="This isn't JSON", action="analyze", request_json=self.payload())
        result = self.nodes["NGAIResult"].execute(text='{"content":"rules","description":"Slow camera."}', action="analyze", request_json=self.payload())
        self.assertEqual(result.ui["ng_suggestion"][0]["description"], "Slow camera.")
        result = self.nodes["NGAIResult"].execute(text='assistant\n{"content":"rules","description":"Slow camera."}', action="analyze", request_json=self.payload())
        self.assertEqual(result.ui["ng_suggestion"][0]["content"], "rules")


if __name__ == "__main__":
    unittest.main()
