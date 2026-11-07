"""New native widget fields must not make an older saved workflow unqueueable."""
import os
import shutil
import subprocess
import unittest
from _pack import REPO, comfy_available, load_full_pack

@unittest.skipUnless(shutil.which("node"), "node is not installed; provider workflow restore was NOT checked")
class ProviderWorkflowCompatibility(unittest.TestCase):
    def test_old_and_current_native_widget_layouts_keep_their_meanings(self):
        result = subprocess.run([shutil.which("node"), os.path.join(REPO, "tests/ng/js/test_ng_provider_restore.mjs")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
    def test_legacy_disk_provider_arguments_keep_lazy_native_loading(self):
        nodes = load_full_pack().NODE_CLASS_MAPPINGS
        provider = nodes["NGAIProvider"].execute(source="local", clip=None, local_backend="disk",
                   local_model="qwen3vl_4b_bf16.safetensors", provider="ollama").args[0]
        self.assertIsNone(provider.clip)
        self.assertEqual(provider.local_model, "qwen3vl_4b_bf16.safetensors")
        self.assertEqual(provider.local_type, "stable_diffusion")
