import os
import tempfile
import unittest
from unittest.mock import patch

from _pack import module, comfy_available


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class InputPaths(unittest.TestCase):
    def test_subfolders_and_legacy_workspace(self):
        paths = module("ng.adapters.paths")
        with tempfile.TemporaryDirectory() as root, patch.object(paths.folder_paths, "get_input_directory", return_value=root):
            os.makedirs(os.path.join(root, "refs"))
            path = os.path.join(root, "refs", "alice.png")
            with open(path, "wb") as stream:
                stream.write(b"image")
            self.assertEqual(paths.input_path("refs/alice.png [input]"), path)
            self.assertEqual(paths.input_path("refs\\alice.png"), path)
            self.assertIsNone(paths.input_path("missing.png"))
            os.makedirs(os.path.join(root, "whatdreamscost"))
            other = os.path.join(root, "whatdreamscost", "voice.wav")
            with open(other, "wb") as stream:
                stream.write(b"audio")
            self.assertEqual(paths.input_path("voice.wav"), other)

    def test_traversal_and_absolute_names_are_rejected(self):
        paths = module("ng.adapters.paths")
        for source in ("../secret.txt", "refs/../../secret.txt", "C:\\secret.txt", "C:secret.txt", "/etc/passwd", "\\\\host\\secret.txt"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "inside"):
                paths.input_path(source)

    def test_symlink_escape_is_rejected(self):
        paths = module("ng.adapters.paths")
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            with open(os.path.join(outside, "secret.txt"), "w") as stream:
                stream.write("secret")
            try:
                os.symlink(outside, os.path.join(root, "link"), target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            with patch.object(paths.folder_paths, "get_input_directory", return_value=root), self.assertRaisesRegex(ValueError, "inside"):
                paths.input_path("link/secret.txt")
