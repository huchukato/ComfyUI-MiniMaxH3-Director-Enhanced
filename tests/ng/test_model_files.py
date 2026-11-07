"""The extra models (js/ng/models.json, ng/adapters/model_files.py): chosen file, else the official name, else the patterns."""
import json
import os
import tempfile
import unittest
from unittest import mock

from _pack import comfy_available, module

HAVE_COMFY = comfy_available()


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class ModelFiles(unittest.TestCase):
    def setUp(self):
        self.files = module("ng.adapters.model_files")

    def listed(self, names):
        return mock.patch("folder_paths.get_filename_list", return_value=names)

    def test_the_choice_wins_while_it_is_there(self):
        with self.listed(["my_sam3.safetensors", "sam3.1_multiplex_fp16.safetensors"]):
            self.assertEqual(self.files.find("sam3"), "sam3.1_multiplex_fp16.safetensors", "the official name first")
            self.assertEqual(self.files.find("sam3", "my_sam3.safetensors"), "my_sam3.safetensors")
            self.assertEqual(self.files.find("sam3", "gone.safetensors"), "sam3.1_multiplex_fp16.safetensors")
        with self.listed(["sam3_custom_fp8.safetensors"]):
            self.assertEqual(self.files.find("sam3"), "sam3_custom_fp8.safetensors", "a renamed file still fits a pattern")
        with self.listed([]):
            self.assertIsNone(self.files.find("sam3"))

    def test_qwen_prefers_the_int8_files(self):
        with self.listed(["qwen_image_2.1_bf16.safetensors", "qwen_image_2.1_int8_convrot.safetensors"]):
            self.assertEqual(self.files.find("qwen_image"), "qwen_image_2.1_int8_convrot.safetensors")

    def test_whisper_lives_in_its_own_folder_and_the_larger_model_wins(self):
        with tempfile.TemporaryDirectory() as root, mock.patch("folder_paths.models_dir", root):
            self.assertEqual(self.files.names("whisper"), [])
            os.makedirs(os.path.join(root, "whisper"))
            for name in ("small.pt", "medium.pt", "notes.txt"):
                open(os.path.join(root, "whisper", name), "w").close()
            self.assertEqual(self.files.find("whisper"), "medium.pt")
            self.assertEqual(self.files.find("whisper", "small.pt"), "small.pt")
            lyrics = module("ng.adapters.lyrics_timing")
            self.assertEqual(lyrics.model_file("small.pt"), os.path.join(root, "whisper", "small.pt"))
            self.assertEqual(lyrics.model_file(), os.path.join(root, "whisper", "medium.pt"))
        with tempfile.TemporaryDirectory() as root, mock.patch("folder_paths.models_dir", root):
            with self.assertRaisesRegex(ValueError, r"Whisper needs small\.pt in models/whisper \(https://openaipublic"):
                lyrics.model_file()

    def test_a_folder_comfyui_does_not_know_is_read_from_models(self):
        with tempfile.TemporaryDirectory() as root, mock.patch("folder_paths.models_dir", root),                 mock.patch.dict("folder_paths.folder_names_and_paths", {}, clear=False):
            import folder_paths
            folder_paths.folder_names_and_paths.pop("geometry_estimation", None)
            self.assertEqual(self.files.names("moge"), [])
            os.makedirs(os.path.join(root, "geometry_estimation", "sub"))
            open(os.path.join(root, "geometry_estimation", "moge_2_vitl_normal_fp16.safetensors"), "w").close()
            self.assertEqual(self.files.find("moge"), "moge_2_vitl_normal_fp16.safetensors")

    def test_the_stored_choice_is_read_safely(self):
        self.assertEqual(self.files.chosen('{"sam3": "a.safetensors", "nope": "x", "qwen_vae": 3}'), {"sam3": "a.safetensors"})
        self.assertEqual(self.files.chosen(""), {})
        self.assertEqual(self.files.chosen("{broken"), {})
        self.assertEqual(self.files.chosen("[1, 2]"), {})

    def test_every_entry_finds_its_own_file(self):
        import re
        for purpose, entry in self.files.MODELS.items():
            self.assertTrue(any(re.search(p, entry["file"], re.I) for p in entry["patterns"]), purpose)
            self.assertIn(entry["file"], self.files.missing(purpose))

    def test_place_pictures_use_the_directors_choice(self):
        places = module("ng.adapters.places")
        listing = {"checkpoints": ["sam3.1_multiplex_fp16.safetensors", "mine.safetensors"],
                   "diffusion_models": ["qwen_image_2.1_int8_convrot.safetensors"], "text_encoders": ["qwen3vl_8b_int8_convrot.safetensors"],
                   "vae": ["qwen_image_2.1_vae_bf16.safetensors", "my_vae.safetensors"]}
        with mock.patch("folder_paths.get_filename_list", side_effect=lambda folder: listing.get(folder, [])):
            self.assertEqual(places.qwen_files({"qwen_vae": "my_vae.safetensors"}),
                             {"image": "qwen_image_2.1_int8_convrot.safetensors", "encoder": "qwen3vl_8b_int8_convrot.safetensors",
                              "vae": "my_vae.safetensors"})
            listing["text_encoders"] = []
            self.assertIsNone(places.qwen_files({})["encoder"])

    def test_the_director_hands_its_choice_to_the_render_loop(self):
        render_graph = module("ng.adapters.render_graph")
        settings = {"seed": 1, "steps": 4, "sampler_name": "euler", "scheduler": "simple", "shift_video": 12.0, "shift_audio": 3.0,
                    "models": json.dumps({"sam3": "mine.safetensors"})}
        inputs = dict(chunks=["plan", 0], clip=["clip", 0], vae=["vae", 0], audio_vae=["audio", 0], model_ref2va=["ref", 0])
        graph, _ = render_graph.render_sequence(inputs, settings)
        place = next(node for node in graph.values() if node["class_type"] == "NGPlaceStill")
        self.assertEqual(json.loads(place["inputs"]["models"]), {"sam3": "mine.safetensors"})


if __name__ == "__main__":
    unittest.main()
