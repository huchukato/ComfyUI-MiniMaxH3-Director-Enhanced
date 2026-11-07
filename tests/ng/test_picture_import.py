"""Pictures the Image card's editor made go from output/h3-picture-edit into the input folder (adapters/control_files.py)."""
import os
import tempfile
import unittest
from unittest import mock

from _pack import module


class Import(unittest.TestCase):
    def setUp(self):
        self.files = module("ng.adapters.control_files")
        self.root = tempfile.mkdtemp()
        self.output, self.input = os.path.join(self.root, "output"), os.path.join(self.root, "input")
        os.makedirs(os.path.join(self.output, "h3-picture-edit"))
        os.makedirs(self.input)
        with open(os.path.join(self.output, "h3-picture-edit", "x_sheet_00001_.png"), "wb") as handle:
            handle.write(b"png")
        patcher = mock.patch.multiple(self.files.folder_paths, get_output_directory=lambda: self.output, get_input_directory=lambda: self.input)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_sheet_is_copied_into_the_input_folder_under_its_kind(self):
        name = self.files.import_picture("x_sheet_00001_.png", "h3-picture-edit", "sheet")
        self.assertTrue(name.startswith(os.path.join("h3-picture-edit", "sheet_")))
        with open(os.path.join(self.input, name), "rb") as handle:
            self.assertEqual(handle.read(), b"png")

    def test_only_our_own_pictures_of_known_kinds(self):
        with self.assertRaises(ValueError):
            self.files.import_picture("x_sheet_00001_.png", "h3-picture-edit", "video")
        with self.assertRaises(ValueError):
            self.files.import_picture("../secret.png", "h3-picture-edit", "mask")
        with self.assertRaises(ValueError):
            self.files.import_picture("x_sheet_00001_.png", "elsewhere", "sheet")


if __name__ == "__main__":
    unittest.main()
