"""Attached TAEHV contracts: real CPU tensors/JPEG, stub neural decoding."""
import base64
import copy
import io
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(os.environ.get("MINIMAX_TEST_REPO", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPO / "tests" / "ng"))
sys.path.insert(0, str(REPO.parents[1]))
from _pack import module
import torch
from PIL import Image
import comfy.nested_tensor
import comfy.utils

runtime = module("minimax_preview_runtime")
preview_node = module("minimax_preview")


class StubVAE:
    def __init__(self, device="cpu", dtype=torch.float32):
        self.first_stage_model = runtime.TAEHV.__new__(runtime.TAEHV)
        torch.nn.Module.__init__(self.first_stage_model)
        self.first_stage_model.latent_channels = 24
        self.first_stage_model.patch_size = 2
        self.device, self.vae_dtype = torch.device(device), dtype
        self.patcher = object()
        self.inputs, self.threads = [], []
        self.last_output = None

    def decode(self, value):
        self.inputs.append(value.clone())
        self.threads.append(threading.get_ident())
        count = {1: 1, 2: 5, 7: 22, 37: 124}[int(value.shape[2])]
        images = torch.full((1, count, 8, 16, 3), float(value[0, 0, 0, 0, 0]))
        self.last_output = images
        return images


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.event_lock = threading.Lock()
        def send(event, data, sid=None):
            with self.event_lock:
                self.events.append((event, dict(data), sid))
        self.server = SimpleNamespace(client_id="request-A", send_sync=send)
        self.server_patch = patch.object(runtime.server.PromptServer, "instance", self.server, create=True)
        self.server_patch.start()
        self.addCleanup(self.server_patch.stop)

    def options(self, **values):
        return runtime.PreviewOptions.from_values({"max_preview_overhead": 0, **values})

    def buffer_events(self):
        return [item for item in self.events if isinstance(item[1].get("frames"), list)]

    def wait_buffers(self, count):
        deadline = time.monotonic() + 3
        while len(self.buffer_events()) < count and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertGreaterEqual(len(self.buffer_events()), count, self.events)


class DecoderContract(RuntimeCase):
    def test_uses_attached_h3_taehv_without_loading_another_checkpoint(self):
        vae = StubVAE()
        with patch.object(runtime.comfy.utils, "load_torch_file", side_effect=AssertionError("hidden load")):
            self.assertIs(runtime.require_taehv(vae), vae)
            worker = runtime.PreviewWorker("42", self.options(), "run", vae)
            worker.offer(0, torch.full((1, 24, 7, 1, 2), 0.25), 4)
            worker.finish()
        self.assertEqual(len(vae.inputs), 1)
        self.assertIsNone(worker.vae)

    def test_full_video_vae_wrong_tae_and_legacy_patch1_are_rejected(self):
        mismatch, old = StubVAE(), StubVAE()
        mismatch.first_stage_model.latent_channels = 16
        old.first_stage_model.patch_size = 1
        full = SimpleNamespace(first_stage_model=SimpleNamespace(latent_channels=24, patch_size=2))
        for invalid in (None, full, mismatch, old):
            with self.assertRaisesRegex(ValueError, "H3-TAEHV.*taeh3"):
                runtime.require_taehv(invalid)

    def test_spatial_cap_preserves_all_temporal_frames(self):
        video = torch.arange(37, dtype=torch.float32).view(1, 1, 37, 1, 1).expand(1, 24, 37, 9, 16).clone()
        result = runtime.resize_latent(video, 128)
        self.assertEqual(tuple(result.shape), (1, 24, 37, 4, 8))
        torch.testing.assert_close(result[0, 0, :, 0, 0], torch.arange(37, dtype=torch.float32))
        small = torch.zeros(1, 24, 7, 2, 3)
        self.assertEqual(tuple(runtime.resize_latent(small, 768).shape), tuple(small.shape))

    def test_jpeg_buffer_uses_full_decoded_timeline_and_zero_to_one_range(self):
        images = torch.full((1, 124, 8, 16, 3), 0.25)
        for requested, count, fps in ((24, 124, 24), (12, 62, 12), (30, 124, 24)):
            data = runtime.encode_frames(images, self.options(preview_fps=requested))
            self.assertEqual(len(data["frames"]), count)
            self.assertAlmostEqual(data["duration"], 124 / 24)
            self.assertAlmostEqual(data["fps"], fps)
            self.assertEqual((data["width"], data["height"]), (16, 8))
            with Image.open(io.BytesIO(base64.b64decode(data["frames"][0]))) as frame:
                self.assertEqual(frame.format, "JPEG")
                self.assertTrue(all(abs(channel - 64) <= 2 for channel in frame.getpixel((4, 4))))

    def test_requested_cadence_does_not_speed_up_short_sequence(self):
        data = runtime.encode_frames(torch.zeros(1, 5, 8, 16, 3), self.options(preview_fps=12))
        self.assertAlmostEqual(data["duration"], 5 / 24)
        self.assertLessEqual(data["fps"], 12)


class WorkerContract(RuntimeCase):
    def test_decode_stays_on_sampler_thread_and_preserves_connected_vae_policy(self):
        for device in ("cpu", "cuda:0"):
            vae = StubVAE(device, torch.bfloat16)
            patcher = vae.patcher
            original = torch.full((2, 24, 37, 9, 16), 0.25, dtype=torch.float16)
            caller, encoded_on = threading.get_ident(), []
            encode = runtime.encode_frames
            def record_encode(images, options):
                encoded_on.append((threading.get_ident(), str(images.device)))
                return encode(images, options)
            worker = runtime.PreviewWorker("42", self.options(max_resolution=128), "run", vae)
            with patch.object(runtime, "encode_frames", side_effect=record_encode):
                worker.offer(0, original, 4)
                worker.finish()
            self.assertEqual(tuple(vae.inputs[0].shape), (1, 24, 37, 4, 8))
            self.assertEqual(vae.inputs[0].dtype, torch.float16)
            self.assertEqual(vae.threads, [caller])
            self.assertEqual(vae.device, torch.device(device))
            self.assertEqual(vae.vae_dtype, torch.bfloat16)
            self.assertIs(vae.patcher, patcher)
            self.assertNotEqual(encoded_on[0][0], caller)
            self.assertEqual(encoded_on[0][1], "cpu")

    def test_cpu_rgb_queue_owns_storage_and_keeps_latest_pending_buffer(self):
        entered, release = threading.Event(), threading.Event()
        vae, calls = StubVAE(), []
        encode = runtime.encode_frames
        def gated_encode(images, options):
            if not calls:
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("JPEG gate not released")
            calls.append(float(images[0, 0, 0, 0, 0]))
            return encode(images, options)
        worker = runtime.PreviewWorker("42", self.options(), "run", vae)
        with patch.object(runtime, "encode_frames", side_effect=gated_encode):
            worker.offer(0, torch.full((1, 24, 7, 1, 2), 0.25), 4)
            self.assertTrue(entered.wait(3))
            worker.offer(1, torch.full((1, 24, 7, 1, 2), 0.5), 4)
            worker.offer(2, torch.full((1, 24, 7, 1, 2), 0.75), 4)
            vae.last_output.zero_()
            release.set()
            worker.finish()
        self.assertEqual(calls, [0.25, 0.75])
        self.assertEqual([item[1]["step"] for item in self.buffer_events()], [1, 3])
        self.assertIsNone(worker.pending)
        self.assertIsNone(worker.thread)

    def test_event_contract_captures_request_client_and_full_shot_duration(self):
        worker = runtime.PreviewWorker("42", self.options(), "run", StubVAE())
        self.server.client_id = "other-request"
        worker.offer(0, torch.full((1, 24, 37, 1, 2), 0.25), 20)
        worker.finish()
        event, data, sid = self.buffer_events()[0]
        self.assertEqual((event, sid), (runtime.EVENT, "request-A"))
        self.assertEqual((data["node_id"], data["run_id"], data["decoder"]), ("42", "run", "TAEHV"))
        self.assertEqual((data["step"], data["total_steps"], len(data["frames"])), (1, 20, 124))
        self.assertEqual((data["fps"], data["source_fps"]), (24, 24))
        self.assertAlmostEqual(data["duration"], 124 / 24)
        self.assertIn("sequence_id", data)
        self.assertGreaterEqual(data["ms"], 0)

    def test_jpeg_failure_emits_error_and_releases_queue(self):
        worker = runtime.PreviewWorker("42", self.options(), "run", StubVAE())
        with patch.object(runtime, "encode_frames", side_effect=RuntimeError("JPEG exploded")), \
                self.assertLogs(runtime.log, level="WARNING"):
            worker.offer(0, torch.zeros(1, 24, 7, 1, 2), 4)
            worker.finish()
        self.assertTrue(worker.failed)
        self.assertFalse(self.buffer_events())
        self.assertIn("JPEG exploded", next(data["error"] for _, data, _ in self.events if "error" in data))
        self.assertIsNone(worker.pending)
        self.assertIsNone(worker.vae)

    def test_actual_comfy_packed_av_nested_and_direct_streams_use_attached_vae(self):
        video = torch.full((1, 24, 7, 1, 2), 0.4)
        audio = torch.full((1, 32, 2, 36), -999.0)
        packed, shapes = comfy.utils.pack_latents([video, audio])
        nested = comfy.nested_tensor.NestedTensor([video, audio])
        for source, latent_shapes in ((packed, shapes), (nested, None), (video, None)):
            vae = StubVAE()
            worker = runtime.PreviewWorker("42", self.options(), "run", vae)
            worker.offer(0, source, 4, latent_shapes)
            worker.finish()
            torch.testing.assert_close(vae.inputs[0], video)

    def test_invalid_callback_values_do_not_decode(self):
        vae = StubVAE()
        worker = runtime.PreviewWorker("42", self.options(), "run", vae)
        for invalid in (None, 0.25, torch.tensor(1.0), torch.empty(1, 24, 0, 1, 2), torch.zeros(1, 32, 2, 1, 2)):
            worker.offer(0, invalid, 4)
        worker.finish()
        self.assertFalse(vae.inputs)

    def test_step_interval_retains_final_callback(self):
        worker = runtime.PreviewWorker("42", self.options(every_n_steps=3), "run", StubVAE())
        worker.offer(1, torch.zeros(1, 24, 7, 1, 2), 3)
        self.assertIsNone(worker.thread)
        worker.offer(2, torch.zeros(1, 24, 7, 1, 2), 3)
        worker.finish()
        self.assertEqual([item[1]["step"] for item in self.buffer_events()], [3])

    def test_cost_throttle_skips_decode_until_gap_expires(self):
        clock, vae = {"now": 100.0}, StubVAE()
        decode = vae.decode
        def costly_decode(value):
            result = decode(value)
            clock["now"] += 2.0
            return result
        vae.decode = costly_decode
        worker = runtime.PreviewWorker("42", self.options(max_preview_overhead=25), "run", vae)
        with patch.object(runtime, "time", SimpleNamespace(monotonic=lambda: clock["now"])):
            worker.offer(0, torch.zeros(1, 24, 7, 1, 2), 5)
            self.wait_buffers(1)
            worker.offer(1, torch.ones(1, 24, 7, 1, 2), 5)
            clock["now"] = 107.9
            worker.offer(2, torch.ones(1, 24, 7, 1, 2), 5)
            self.assertEqual(len(vae.inputs), 1)
            clock["now"] = 108.0
            worker.offer(3, torch.full((1, 24, 7, 1, 2), 0.75), 5)
            worker.finish()
        self.assertEqual([float(value[0, 0, 0, 0, 0]) for value in vae.inputs], [0.0, 0.75])

    def test_finished_worker_ignores_late_callbacks(self):
        vae = StubVAE()
        worker = runtime.PreviewWorker("42", self.options(), "run", vae)
        worker.finish()
        worker.offer(0, torch.zeros(1, 24, 7, 1, 2), 4)
        self.assertFalse(vae.inputs)
        self.assertIsNone(worker.vae)
        self.assertIsNone(worker.thread)

    def test_cancel_drops_pending_buffer_and_joins_encoder(self):
        entered, release = threading.Event(), threading.Event()
        encode = runtime.encode_frames
        def gated_encode(images, options):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("JPEG gate not released")
            return encode(images, options)
        worker = runtime.PreviewWorker("42", self.options(), "run", StubVAE())
        with patch.object(runtime, "encode_frames", side_effect=gated_encode):
            worker.offer(0, torch.zeros(1, 24, 7, 1, 2), 4)
            self.assertTrue(entered.wait(3))
            worker.offer(1, torch.ones(1, 24, 7, 1, 2), 4)
            finishing = threading.Thread(target=lambda: worker.finish(cancel=True))
            finishing.start()
            deadline = time.monotonic() + 3
            while not worker.finishing and time.monotonic() < deadline:
                time.sleep(0.005)
            try:
                self.assertTrue(worker.finishing)
                self.assertIsNone(worker.pending)
            finally:
                release.set()
                finishing.join(timeout=3)
        self.assertFalse(finishing.is_alive())
        self.assertEqual([item[1]["step"] for item in self.buffer_events()], [1])
        self.assertIsNone(worker.vae)
        self.assertIsNone(worker.thread)


class OuterSampleContract(RuntimeCase):
    def test_original_callback_arguments_and_finish_survive_sampler_exception(self):
        received = []
        worker = SimpleNamespace(offer=lambda *args: received.append(args), failed=False,
                                 finish=lambda **kwargs: received.append(kwargs))
        callbacks = []
        x0, x = torch.zeros(1, 24, 7, 1, 2), torch.ones(1, 24, 7, 1, 2)
        def original(*args):
            callbacks.append(args)
        def executor(noise, latent, sampler, sigmas, mask, callback, disable, seed, **kwargs):
            callback(0, x0, x, 4)
            raise RuntimeError("sampler stopped")
        wrapper = runtime.OuterSamplePreview("42", self.options(suppress_default_preview=False), StubVAE())
        with patch.object(runtime, "PreviewWorker", return_value=worker):
            with self.assertRaisesRegex(RuntimeError, "sampler stopped"):
                wrapper(executor, None, None, None, None, None, original, False, 9, latent_shapes=["video", "audio"])
        self.assertEqual(callbacks, [(0, x0, x, 4)])
        self.assertEqual(received[0], (0, x0, 4, ["video", "audio"]))
        self.assertEqual(received[-1], {"cancel": True})

    def test_attached_vae_failure_keeps_callback_and_sampler_result(self):
        vae, callbacks = StubVAE(), []
        def decode(value):
            raise RuntimeError("attached decoder failed")
        vae.decode = decode
        x0, x = torch.zeros(1, 24, 7, 1, 2), torch.ones(1, 24, 7, 1, 2)
        def original(*args):
            callbacks.append(args)
        def executor(noise, latent, sampler, sigmas, mask, callback, disable, seed, **kwargs):
            callback(0, x0, x, 4)
            return "sample-result"
        wrapper = runtime.OuterSamplePreview("42", self.options(suppress_default_preview=False), vae)
        with self.assertLogs(runtime.log, level="WARNING"):
            self.assertEqual(wrapper(executor, None, None, None, None, None, original, False, 9), "sample-result")
        self.assertEqual(callbacks, [(0, x0, x, 4)])
        self.assertFalse(self.buffer_events())
        self.assertIs(wrapper.vae, vae)
        self.assertIn("attached decoder failed", next(data["error"] for _, data, _ in self.events if "error" in data))

    def test_native_preview_suppression_is_local_and_restored_after_error(self):
        class NativePreview(runtime.latent_preview.LatentPreviewer):
            def decode_latent_to_preview(self, x0):
                return "image"
        own, other = NativePreview(), NativePreview()
        def callback(step, x0, x, total):
            return own.decode_latent_to_preview_image("JPEG", x0)
        def nested(*args):
            return callback(*args)
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with runtime.suppress_preview(nested, True):
                self.assertIsNone(callback(0, None, None, 1))
                self.assertEqual(other.decode_latent_to_preview_image("JPEG", None)[1], "image")
                raise RuntimeError("stop")
        self.assertEqual(callback(0, None, None, 1)[1], "image")
        self.assertNotIn("decode_latent_to_preview_image", own.__dict__)


class NodeContract(RuntimeCase):
    def model(self):
        class Model:
            def __init__(self, options):
                self.model_options = options
            def clone(self):
                return Model(copy.deepcopy(self.model_options))
        kind = preview_node.comfy.patcher_extension.WrappersMP.OUTER_SAMPLE
        return Model({"transformer_options": {"wrappers": {kind: {
            preview_node.WRAPPER_KEY: ["stale-preview"], "another-package": ["keep-wrapper"],
        }}}})

    def cls(self):
        return SimpleNamespace(hidden=SimpleNamespace(unique_id="internal-id", dynprompt=SimpleNamespace(
            get_display_node_id=lambda value: "visible-id")))

    def test_schema_requires_vae_and_has_no_enable_switch(self):
        schema = preview_node.MiniMaxH3PreviewOverride.GET_SCHEMA()
        inputs = {item.id: item for item in schema.inputs}
        self.assertEqual(inputs["vae"].io_type, "VAE")
        self.assertFalse(inputs["vae"].optional)
        self.assertNotIn("enabled", inputs)
        self.assertNotIn("enabled", runtime.PreviewOptions.__dataclass_fields__)
        self.assertEqual(schema.display_name, "🎯 Preview Override (live)")

    def test_missing_or_full_vae_fails_before_model_clone(self):
        model = self.model()
        with self.assertRaises(TypeError):
            preview_node.execute_preview(self.cls(), model)
        with patch.object(model, "clone", side_effect=AssertionError("must validate first")):
            with self.assertRaisesRegex(ValueError, "H3-TAEHV"):
                preview_node.execute_preview(self.cls(), model, object())

    def test_repeated_nodes_replace_only_own_wrapper_and_keep_connected_vae(self):
        original, first_vae, final_vae = self.model(), StubVAE(), StubVAE()
        kind = preview_node.comfy.patcher_extension.WrappersMP.OUTER_SAMPLE
        first = preview_node.execute_preview(self.cls(), original, first_vae)[0]
        second = preview_node.execute_preview(self.cls(), first, final_vae, preview_fps=12)[0]
        after = second.model_options["transformer_options"]["wrappers"][kind]
        self.assertEqual(after["another-package"], ["keep-wrapper"])
        self.assertEqual(len(after[preview_node.WRAPPER_KEY]), 1)
        wrapper = after[preview_node.WRAPPER_KEY][0]
        self.assertEqual(wrapper.node_id, "visible-id")
        self.assertEqual(wrapper.options.preview_fps, 12)
        self.assertIs(wrapper.vae, final_vae)
        self.assertEqual(original.model_options["transformer_options"]["wrappers"][kind][preview_node.WRAPPER_KEY], ["stale-preview"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
