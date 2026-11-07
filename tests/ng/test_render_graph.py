import types
import unittest

from _pack import comfy_available, load_full_pack, module


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class RenderGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_full_pack()
        cls.render = cls.pack.NODE_CLASS_MAPPINGS["NGRenderSequence"]
        cls.studio = cls.pack.NODE_CLASS_MAPPINGS["NGDirectorStudio"]

    def values(self):
        return dict(chunks=["plan", 0], clip=["clip", 0], vae=["video_vae", 0], audio_vae=["audio_vae", 0],
                    model_fl2va=["fl2va", 0], model_ref2va=["ref2va", 0], seed=123, steps=8,
                    sampler_name="res_multistep", scheduler="simple", shift_video=12.0, shift_audio=3.0)

    def by_type(self, output, kind):
        return [(key, value) for key, value in output.expand.items() if value["class_type"] == kind]

    def test_models_are_raw_links_so_only_the_selected_model_is_loaded(self):
        for node in (self.render, self.studio):
            inputs = {item.id: item for item in node.GET_SCHEMA().inputs}
            for name in ("clip", "vae", "audio_vae", "model_fl2va", "model_ref2va"):
                self.assertTrue(inputs[name].rawLink, name)
            self.assertTrue(node.GET_SCHEMA().enable_expand)
            self.assertEqual([item.display_name for item in node.GET_SCHEMA().outputs[:3]], ["video", "images", "audio"])

    def test_render_wraps_the_native_loop_and_keeps_previous_latent(self):
        out = self.render.execute(**self.values())
        start_id, start = self.by_type(out, "StartLoop")[0]
        end_id, end = self.by_type(out, "EndLoop")[0]
        conditioning_id, conditioning = self.by_type(out, "NGChunkConditioning")[0]
        sample_id, _ = self.by_type(out, "SamplerCustomAdvanced")[0]
        self.assertEqual(start["_loop_end"], end_id)
        self.assertIn(sample_id, start["_loop_body"])
        self.assertIn(conditioning_id, start["_loop_body"])
        self.assertEqual(conditioning["inputs"]["previous"], [start_id, 4])
        # the sampled part passes NG Resume Chunk (kept on disk for a resume after a crash) on its way to the loop end
        resume_id, resume = self.by_type(out, "NGResumeChunk")[0]
        self.assertEqual(resume["inputs"]["sampled"], [sample_id, 0])
        self.assertEqual(resume["inputs"]["chunk"], [start_id, 3])
        self.assertIn(resume_id, start["_loop_body"])
        # then NG Place Still, which saves the pictures later shots take their place from (core/places.py)
        place_id, place = self.by_type(out, "NGPlaceStill")[0]
        self.assertEqual(place["inputs"]["sampled"], [resume_id, 0])
        self.assertEqual(place["inputs"]["chunk"], [start_id, 3])
        self.assertIn(place_id, start["_loop_body"])
        self.assertEqual(end["inputs"]["next_iteration_value"], [place_id, 0])
        self.assertEqual(end["inputs"]["output_value"], [place_id, 0])
        self.assertTrue(end["inputs"]["accumulate"])
        self.assertEqual(start["inputs"]["mode.list"], ["plan", 0])
        self.assertEqual(len(out.args), 4)
        # by default Collect deletes the kept parts once the video is put together, under the same settings as the keys
        collect = self.by_type(out, "NGCollect")[0][1]
        self.assertEqual(collect["inputs"]["resume_settings"], resume["inputs"]["settings"])

    def test_kept_parts_stay_when_delete_is_off_and_nothing_is_kept_without_resume(self):
        render_sequence = module("ng.adapters.render_graph").render_sequence
        inputs = dict(chunks=["plan", 0], clip=["clip", 0], vae=["v", 0], audio_vae=["a", 0], model_fl2va=["fl2va", 0])
        settings = dict(seed=1, steps=4, sampler_name="euler", scheduler="simple", shift_video=12.0, shift_audio=3.0)
        for extra, kept, deleted in (({"resume_delete_done": False}, True, False), ({"resume": False}, False, False)):
            graph = render_sequence(inputs, {**settings, **extra})[0]
            types_ = [node["class_type"] for node in graph.values()]
            collect = next(node for node in graph.values() if node["class_type"] == "NGCollect")
            self.assertEqual("NGResumeChunk" in types_, kept, extra)
            self.assertEqual("resume_settings" in collect["inputs"], deleted, extra)

    def test_spectrum_wraps_the_sampled_model_with_turbo_off_only(self):
        render_sequence = module("ng.adapters.render_graph").render_sequence
        inputs = dict(chunks=["plan", 0], clip=["clip", 0], vae=["v", 0], audio_vae=["a", 0], model_fl2va=["fl2va", 0])
        settings = dict(seed=1, steps=20, sampler_name="res_multistep", scheduler="simple", shift_video=12.0, shift_audio=3.0)
        for extra, used in (({}, False), ({"spectrum": True}, True), ({"spectrum": True, "turbo": True}, False)):
            graph = render_sequence(inputs, {**settings, **extra})[0]
            spectrum = [key for key, node in graph.items() if node["class_type"] == "SpectrumApplyMiniMaxH3"]
            self.assertEqual(bool(spectrum), used, extra)
            if used:
                guider = next(node for node in graph.values() if node["class_type"] == "BasicGuider")
                self.assertEqual(guider["inputs"]["model"][0], spectrum[0])
                sampling = next(node for node in graph.values() if node["class_type"] == "NGChunkSampling")
                self.assertIn('"spectrum": true', sampling["inputs"]["settings"], "a part sampled with Spectrum is not reused without it")

    def test_missing_optional_model_is_not_added_as_an_invalid_null_link(self):
        values = self.values()
        del values["model_ref2va"]
        out = self.render.execute(**values)
        conditioning = self.by_type(out, "NGChunkConditioning")[0][1]["inputs"]
        self.assertNotIn("model_ref2va", conditioning)
        del values["model_fl2va"]
        with self.assertRaisesRegex(ValueError, "Connect an H3 model"):
            self.render.execute(**values)

    def test_studio_wires_contexts_into_the_same_planner_as_preview(self):
        values = self.values()
        del values["chunks"]
        values.update(idea="@Alice walks.", project_seconds=20.0, shots="", chunk_seconds=10.0,
                      width=384, height=576, mode="auto", continuity="video_audio", pin_frames="22",
                      soundscape="wind", music="N/A", contexts={"context_1": ["alice", 0]})
        out = self.studio.execute(**values)
        plan_id, plan = self.by_type(out, "NGDirector")[0]
        start = self.by_type(out, "StartLoop")[0][1]
        self.assertEqual(plan["inputs"]["contexts.context_1"], ["alice", 0])
        self.assertEqual(plan["inputs"]["idea"], "@Alice walks.")
        self.assertEqual(start["inputs"]["mode.list"], [plan_id, 0])
        self.assertEqual(out.args[4:], ([plan_id, 2], [plan_id, 1]))
        self.assertEqual(len(out.args), 6)

    def test_noise_seed_varies_by_chunk_and_wraps_at_uint64(self):
        noise = self.pack.NODE_CLASS_MAPPINGS["NGChunkNoise"]
        first = noise.execute(chunk=types.SimpleNamespace(index=0), seed=123).args[0]
        second = noise.execute(chunk=[types.SimpleNamespace(index=1)], seed=123).args[0]
        wrap = noise.execute(chunk=types.SimpleNamespace(index=1), seed=(1 << 64) - 1).args[0]
        self.assertEqual((first.seed, second.seed, wrap.seed), (123, 124, 0))
