r"""Regression test for BUG-077: Live Preview Runtime emits German UI status and error strings.

In minimax_preview_runtime.py:
1. Lines 75-76: require_taehv raises ValueError with German text:
     "Live Preview benötigt den angeschlossenen H3-TAEHV-VAE aus taeh3.safetensors; ein vollständiger Video-VAE ist nicht unterstützt."
2. Line 131: PreviewWorker.offer sends WebSocket event minimax_h3_preview with:
     {"status": "TAEHV aktualisiert…", "step": ..., "total_steps": ...}
3. Line 166: PreviewWorker.run sends failure WebSocket event with:
     {"status": "TAEHV-Vorschau nicht verfügbar", "error": ...}

In js/minimax_preview_player.js:186-187, onStatus(text, detail) assigns:
     left.textContent = text
which renders these strings directly into span.mmx-preview-step on the ComfyUI node DOM.
This violates USR-004 ("The entire NG interface is English").

Run:
    D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe -B tests/ng/regressions/bug_077_preview_runtime_german_strings.py
"""
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
NG_TESTS = os.path.dirname(HERE)
if NG_TESTS not in sys.path:
    sys.path.insert(0, NG_TESTS)

from _pack import module

runtime = module("minimax_preview_runtime")
import torch


class StubTAEHV:
    def __init__(self):
        self.first_stage_model = runtime.TAEHV.__new__(runtime.TAEHV)
        self.first_stage_model.latent_channels = 24
        self.first_stage_model.patch_size = 2

    def decode(self, x):
        return torch.zeros((1, 5, 8, 16, 3))


class TestBug077PreviewRuntimeGermanStrings(unittest.TestCase):
    def setUp(self):
        self.events = []

        class FakePromptServer:
            client_id = "test-client"

            def send_sync(inner_self, event, data, sid=None):
                self.events.append((event, dict(data)))

        self.server_patch = patch.object(runtime.server.PromptServer, "instance", FakePromptServer(), create=True)
        self.server_patch.start()
        self.addCleanup(self.server_patch.stop)

    def test_control_valid_taehv_returns_cleanly_without_error(self):
        valid = StubTAEHV()
        result = runtime.require_taehv(valid)
        self.assertIs(result, valid)

    def test_control_preview_options_and_playback_labels_are_english(self):
        opts = runtime.PreviewOptions.from_values({})
        self.assertEqual(opts.preview_fps, 24.0)
        self.assertEqual(opts.jpeg_quality, 90)

    def test_bug_077_require_taehv_error_message_must_be_in_english(self):
        with self.assertRaises(ValueError) as ctx:
            runtime.require_taehv(None)

        msg = str(ctx.exception)
        # Must not contain German words:
        self.assertNotIn("benötigt", msg, "Error message must be in English, but contains German 'benötigt'")
        self.assertNotIn("angeschlossenen", msg, "Error message must be in English, but contains German 'angeschlossenen'")
        self.assertNotIn("vollständiger", msg, "Error message must be in English, but contains German 'vollständiger'")
        self.assertNotIn("unterstützt", msg, "Error message must be in English, but contains German 'unterstützt'")

    def test_bug_077_worker_offer_status_must_be_in_english(self):
        vae = StubTAEHV()
        options = runtime.PreviewOptions.from_values({"max_preview_overhead": 0})
        worker = runtime.PreviewWorker("node_1", options, "run_1", vae)

        # Trigger preview offer
        latent = torch.zeros((1, 24, 7, 2, 2))
        worker.offer(0, latent, 4)
        worker.finish()

        status_events = [e[1] for e in self.events if "status" in e[1]]
        self.assertTrue(len(status_events) > 0, "PreviewWorker should have sent status event")
        status_text = status_events[0]["status"]

        # In product code, status_text is 'TAEHV aktualisiert…'
        self.assertNotIn(
            "aktualisiert",
            status_text,
            "UI status text displayed in span.mmx-preview-step must be in English, but got German '%s'" % status_text,
        )

    def test_bug_077_worker_failure_status_must_be_in_english(self):
        vae = StubTAEHV()
        options = runtime.PreviewOptions.from_values({"max_preview_overhead": 0})
        worker = runtime.PreviewWorker("node_1", options, "run_1", vae)

        # Mock encode_frames to fail so the worker's run() exception handler fires
        with patch.object(runtime, "encode_frames", side_effect=RuntimeError("encoding failed")):
            latent = torch.zeros((1, 24, 7, 2, 2))
            worker.offer(0, latent, 4)
            worker.finish()

        failure_events = [e[1] for e in self.events if "error" in e[1]]
        self.assertTrue(len(failure_events) > 0, "PreviewWorker should have sent error status event")
        failure_status = failure_events[0].get("status", "")

        # In product code, failure_status is 'TAEHV-Vorschau nicht verfügbar'
        self.assertNotIn(
            "Vorschau",
            failure_status,
            "UI failure status text displayed in span.mmx-preview-step must be in English, but got German '%s'"
            % failure_status,
        )
        self.assertNotIn(
            "verfügbar",
            failure_status,
            "UI failure status text displayed in span.mmx-preview-step must be in English, but got German '%s'"
            % failure_status,
        )


if __name__ == "__main__":
    unittest.main()
