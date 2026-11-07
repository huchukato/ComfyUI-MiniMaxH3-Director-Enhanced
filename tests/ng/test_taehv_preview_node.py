"""The Connector routes a separate TAEHV VAE to the external Preview Override."""
import asyncio
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from _pack import comfy_available, load_full_pack

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    import nodes
    import comfy.patcher_extension as patcher_extension
    from comfy.model_patcher import ModelPatcher
    from comfy.taesd.taehv import TAEHV
    from comfy_api.latest import io
    from comfy_execution.graph import DynamicPrompt
    from comfy_extras.nodes_custom_sampler import KSamplerSelect, BasicScheduler
    from execution import get_input_data, get_output_data, execute, ExecutionResult


class MemoryOutputs:
    def __init__(self):
        self.entries = {}

    async def get(self, key):
        return self.entries.get(key)

    async def set(self, key, value):
        self.entries[key] = value


class CachedLinks:
    def __init__(self, entries):
        self.entries = entries
        self.reads = []
        self.strong_links = []

    def get_cache(self, source, target):
        self.reads.append((source, target))
        return self.entries.get(source)

    def cache_update(self, key, entry):
        self.entries[key] = entry

    def add_strong_link(self, source, slot, target):
        self.strong_links.append((source, slot, target))


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class TAEHVPreviewNode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_full_pack()
        cls.nodes = cls.pack.NODE_CLASS_MAPPINGS
        cls.preview = cls.nodes["MiniMaxH3PreviewOverrideCS"]
        cls.packets = importlib.import_module(cls.pack.__name__ + ".ng.adapters.director_packets")
        cls.runtime = importlib.import_module(cls.pack.__name__ + ".minimax_preview_runtime")

    def values(self):
        return dict(chunks=["plan", 0], clip=["clip", 0], vae=["video_vae", 0], audio_vae=["audio_vae", 0],
                    model_fl2va=["fl2va", 0], seed=123, steps=8, sampler_name="res_multistep",
                    scheduler="simple", shift_video=12.0, shift_audio=3.0)

    def planning(self):
        return dict(idea="A person walks.", project_seconds=8.0, shots="", chunk_seconds=5.0,
                    width=384, height=576, mode="auto", continuity="video_audio", pin_frames="22",
                    soundscape="wind", music="N/A", seed=123, steps=8, sampler_name="res_multistep",
                    scheduler="simple", shift_video=12.0, shift_audio=3.0)

    def result(self, preview_vae=None):
        values = self.values()
        packet = self.nodes["NGContextConnector"].execute(
            clip=values["clip"], vae=values["vae"], audio_vae=values["audio_vae"],
            model_fl2va=values["model_fl2va"], preview_vae=preview_vae).args[0]
        return self.nodes["NGH3Director"].execute(context=packet, **self.planning()).args[0]

    def run_node(self, cls, node_id, inputs, dyn, cache):
        data, missing, v3 = get_input_data(inputs, cls, node_id, execution_list=cache, dynprompt=dyn)
        self.assertFalse(missing)
        output, _, expanded, pending = asyncio.run(
            get_output_data("preview-contract", node_id, cls, data, v3_data=v3))
        self.assertFalse(pending)
        return output, expanded

    def assert_no_automatic_preview(self, output):
        graph = output.expand
        self.assertNotIn("NGH3Preview", [node["class_type"] for node in graph.values()])
        self.assertNotIn("MiniMaxH3PreviewOverrideCS", [node["class_type"] for node in graph.values()])
        guider = next(node for node in graph.values() if node["class_type"] == "BasicGuider")
        conditioning_id = guider["inputs"]["model"][0]
        self.assertEqual(graph[conditioning_id]["class_type"], "NGChunkConditioning")
        scheduler = next(node for node in graph.values() if node["class_type"] in ("BasicScheduler", "NGChunkSampling"))
        self.assertEqual(scheduler["inputs"]["model"], [conditioning_id, 0])

    def test_connector_appends_an_optional_raw_lazy_preview_vae(self):
        schema = self.nodes["NGContextConnector"].GET_SCHEMA()
        value = schema.inputs[-2]
        self.assertEqual((value.id, value.display_name, value.io_type), ("preview_vae", "preview VAE", "VAE"))
        self.assertTrue(value.optional)
        self.assertTrue(value.rawLink)
        self.assertTrue(value.lazy)

    def test_output_appends_preview_vae_and_preserves_all_existing_slots(self):
        names = self.nodes["NGDirectorOutput"].RETURN_NAMES
        self.assertEqual(list(names), ["model", "positive", "negative", "latent", "fps", "width", "height", "prompt",
                                       "sequence", "seed", "steps", "cfg", "sampler_name", "scheduler", "sampler", "sigmas",
                                       "preview VAE"])
        self.assertEqual(self.nodes["NGDirectorOutput"].RETURN_TYPES[-1], "VAE")
        for preview in (None, ["preview_vae", 0]):
            with self.subTest(preview=preview):
                result = self.result(preview)
                out = self.nodes["NGDirectorOutput"].execute(result)
                self.assertEqual(len(out.args), 17)
                self.assertEqual(out.args[16], preview)
                self.assertEqual(out.args[4:7], (24.0, 384, 576))
                self.assertIs(out.args[8], result)
                self.assertNotIn("preview_vae", result.inputs.links())
                self.assertTrue(all("preview_vae" not in node["inputs"] for node in out.expand.values()))

    def test_native_mapping_keeps_loader_links_unevaluated_at_connector(self):
        inputs = dict(clip=["clip", 0], vae=["video_vae", 0], audio_vae=["audio_vae", 0],
                      model_fl2va=["fl2va", 0], preview_vae=["preview_vae", 0])
        cache = CachedLinks({})
        dyn = DynamicPrompt({"connector": {"class_type": "NGContextConnector", "inputs": inputs}})
        output, expanded = self.run_node(self.nodes["NGContextConnector"], "connector", inputs, dyn, cache)
        self.assertFalse(expanded)
        self.assertEqual(cache.reads, [], "the Connector must not execute a loader")
        self.assertEqual(output[0][0].preview_vae, ["preview_vae", 0])

    def test_native_expansion_resolves_preview_vae_into_external_preview(self):
        connector_inputs = dict(clip=["clip", 0], vae=["video_vae", 0], audio_vae=["audio_vae", 0],
                                model_fl2va=["fl2va", 0], preview_vae=["preview_vae", 0])
        director_inputs = dict(context=["connector", 0], **self.planning())
        preview_inputs = dict(model=["output", 0], vae=["output", 16], max_resolution=768, preview_fps=24.0,
                              jpeg_quality=90, every_n_steps=1, max_preview_overhead=25, suppress_default_preview=True)
        dyn = DynamicPrompt({"connector": {"class_type": "NGContextConnector", "inputs": connector_inputs},
                             "director": {"class_type": "NGH3Director", "inputs": director_inputs},
                             "output": {"class_type": "NGDirectorOutput", "inputs": {"result": ["director", 0]}},
                             "preview": {"class_type": "MiniMaxH3PreviewOverrideCS", "inputs": preview_inputs}})
        cache = CachedLinks({})
        packet, expanded = self.run_node(self.nodes["NGContextConnector"], "connector", connector_inputs, dyn, cache)
        self.assertFalse(expanded)
        self.assertEqual(cache.reads, [])
        cache.entries["connector"] = SimpleNamespace(outputs=packet)
        director, expanded = self.run_node(self.nodes["NGH3Director"], "director", director_inputs, dyn, cache)
        self.assertFalse(expanded)
        cache.entries["director"] = SimpleNamespace(outputs=director)
        outputs = MemoryOutputs()
        pending = {}
        caches = SimpleNamespace(outputs=outputs, objects=MemoryOutputs(), all=[])
        mapping = {"NGDirectorOutput": self.nodes["NGDirectorOutput"],
                   "NGChunkConditioning": self.nodes["NGChunkConditioning"],
                   "ConditioningZeroOut": nodes.ConditioningZeroOut,
                   "KSamplerSelect": KSamplerSelect, "BasicScheduler": BasicScheduler}
        with patch.dict(nodes.NODE_CLASS_MAPPINGS, mapping):
            first = asyncio.run(execute(SimpleNamespace(client_id=None), dyn, caches,
                                        "output", {}, set(), "preview-contract", cache, pending, {}, {}, None))
        self.assertEqual(first, (ExecutionResult.PENDING, None, None))
        self.assertIn(("preview_vae", 0, "output"), cache.strong_links)
        graph = dyn.ephemeral_prompt
        returned = pending["output"][0][1]
        self.assertEqual(returned[16], ["preview_vae", 0])
        self.assertTrue(all("preview_vae" not in node["inputs"] for node in graph.values()))

        # The installed resolver reads the expansion's links from cached outputs;
        # no model loading, conditioning or sampling is performed here.
        model = ModelPatcher(torch.nn.Linear(1, 1), torch.device("cpu"), torch.device("cpu"))
        stage = TAEHV.__new__(TAEHV)
        torch.nn.Module.__init__(stage)
        stage.latent_channels, stage.patch_size = 24, 2
        vae = SimpleNamespace(first_stage_model=stage)
        cache.entries["preview_vae"] = SimpleNamespace(outputs=[[vae]])
        for key, node in graph.items():
            if node["class_type"] == "NGChunkConditioning":
                cache.entries[key] = SimpleNamespace(outputs=[[model], [object()], [object()], ["prompt"]])
            else:
                cache.entries[key] = SimpleNamespace(outputs=[[object()]])
        with patch.dict(nodes.NODE_CLASS_MAPPINGS, {"NGDirectorOutput": self.nodes["NGDirectorOutput"]}):
            result = asyncio.run(execute(SimpleNamespace(client_id=None), dyn, caches,
                                         "output", {}, set(), "preview-contract", cache, pending, {}, {}, None))
        self.assertEqual(result, (ExecutionResult.SUCCESS, None, None))
        self.assertEqual(pending, {})
        resolved = outputs.entries["output"].outputs
        self.assertIs(resolved[0][0], model)
        self.assertIs(resolved[16][0], vae)
        self.assertIn(("preview_vae", "output"), cache.reads)

        # Native input mapping and the real Preview node attach the selected VAE
        # to one wrapper without decoding frames or invoking a sampler.
        with patch.object(vae, "decode", create=True, side_effect=AssertionError("must not decode")):
            preview, expanded = self.run_node(self.preview, "preview", preview_inputs, dyn, cache)
        self.assertFalse(expanded)
        wrapped = preview[0][0]
        wrappers = patcher_extension.get_all_wrappers(patcher_extension.WrappersMP.OUTER_SAMPLE,
                                                     wrapped.model_options, is_model_options=True)
        self.assertEqual(len(wrappers), 1)
        self.assertIsInstance(wrappers[0], self.runtime.OuterSamplePreview)
        self.assertIs(wrappers[0].vae, vae)
        self.assertEqual(wrappers[0].node_id, "preview")
        self.assertEqual(patcher_extension.get_all_wrappers(patcher_extension.WrappersMP.OUTER_SAMPLE,
                                                           model.model_options, is_model_options=True), [])

    def test_render_sequence_without_preview_vae_inserts_no_preview(self):
        self.assert_no_automatic_preview(self.nodes["NGRenderSequence"].execute(**self.values()))

    def test_project_render_previews_each_part_with_connector_or_default_taeh3(self):
        for connected in (["preview_vae", 0], None):
            with self.subTest(connected=connected):
                graph = self.nodes["NGProjectRender"].execute(self.result(connected)).expand
                preview_id, preview = next((key, node) for key, node in graph.items() if node["class_type"] == "NGH3Preview")
                if connected is None:
                    self.assertNotIn("vae", preview["inputs"])
                else:
                    self.assertEqual(preview["inputs"]["vae"], connected)
                self.assertEqual(graph[preview["inputs"]["model"][0]]["class_type"], "NGChunkConditioning")
                guider = next(node for node in graph.values() if node["class_type"] == "BasicGuider")
                sampling = next(node for node in graph.values() if node["class_type"] == "NGChunkSampling")
                self.assertEqual(guider["inputs"]["model"], [preview_id, 0])
                self.assertEqual(sampling["inputs"]["model"], [preview_id, 0])

    def test_ng_preview_falls_back_to_default_taeh3_when_omitted_or_taesd3(self):
        preview_mod = importlib.import_module(self.pack.__name__ + ".ng.nodes.preview_node")
        stage = TAEHV.__new__(TAEHV)
        torch.nn.Module.__init__(stage)
        stage.latent_channels, stage.patch_size = 24, 2
        fallback = SimpleNamespace(first_stage_model=stage)
        model = ModelPatcher(torch.nn.Linear(1, 1), torch.device("cpu"), torch.device("cpu"))
        node = self.nodes["NGH3Preview"]
        node.hidden = SimpleNamespace(unique_id="8.0.preview", dynprompt=SimpleNamespace(get_display_node_id=lambda _: "8"))
        with patch.object(preview_mod, "_load_default_taeh3", return_value=fallback):
            for given in (None, SimpleNamespace(first_stage_model=SimpleNamespace(latent_channels=16, patch_size=1))):
                wrapped = node.execute(model, vae=given).args[0]
                wrappers = patcher_extension.get_all_wrappers(patcher_extension.WrappersMP.OUTER_SAMPLE,
                                                             wrapped.model_options, is_model_options=True)
                self.assertEqual(len(wrappers), 1)
                self.assertIs(wrappers[0].vae, fallback)
                self.assertEqual(wrappers[0].node_id, "8")

    def test_studio_does_not_insert_automatic_preview(self):
        values = self.values()
        del values["chunks"]
        values.update({name: value for name, value in self.planning().items() if name not in values}, contexts={})
        self.assert_no_automatic_preview(self.nodes["NGDirectorStudio"].execute(**values))

    def test_external_preview_requires_a_vae_and_uses_native_hidden_ids(self):
        schema = self.preview.GET_SCHEMA()
        inputs = {item.id: item for item in schema.inputs}
        self.assertEqual(inputs["vae"].io_type, "VAE")
        self.assertFalse(inputs["vae"].optional)
        self.assertEqual(schema.hidden, [io.Hidden.unique_id, io.Hidden.dynprompt])


if __name__ == "__main__":
    unittest.main()
