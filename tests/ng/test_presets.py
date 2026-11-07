import json
import os
import tempfile
import unittest

from _pack import module

core = module("ng.core.presets")
build = module("ng.core.context_build")
storage = module("ng.adapters.presets")


class Presets(unittest.TestCase):
    def preset(self, media="image", name="Alice"):
        item = build.item_from_widgets(media, {media: "refs/alice.png", "name": "Alice", "context_id": "ctx-fixed", "color": "#123456",
                                              "content": "character", "usage": "reference", "description": "a woman", "preserve": "high"})
        return core.ContextPreset(name, item)

    def test_roundtrip_preserves_identity_colour_and_source(self):
        preset = self.preset()
        self.assertEqual(core.ContextPreset.from_dict(json.loads(json.dumps(preset.to_dict()))), preset)
        widgets = core.widget_values(preset.item)
        self.assertEqual(build.item_from_widgets("image", {**widgets, "name": "Renamed"}).id, "ctx-fixed")
        self.assertEqual((widgets["color"], widgets["image"]), ("#123456", "refs/alice.png"))

    def test_version_missing_name_unknown_fields_rejected(self):
        for change in ({"schema_version": 2}, {"name": ""}, {"name": "x" * 81}, {"api_key": "secret"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                core.ContextPreset.from_dict({**self.preset().to_dict(), **change})

    def test_save_load_overwrite_and_media_filter(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(storage.listing(root, "image"), [])
            storage.save(root, self.preset().to_dict())
            storage.save(root, self.preset("audio", "Voice").to_dict())
            self.assertEqual(storage.load(root, "Alice"), self.preset())
            self.assertEqual(storage.listing(root, "image"), ["Alice"])
            updated = self.preset().to_dict()
            updated["item"]["description"] = "a changed description"
            storage.save(root, updated)
            self.assertEqual(storage.load(root, "Alice").item.description, "a changed description")
            self.assertEqual(len(os.listdir(root)), 2)

    def test_names_are_labels_and_cannot_control_disk_paths(self):
        with tempfile.TemporaryDirectory() as root:
            preset = self.preset(name="../Alice: café")
            storage.save(root, preset.to_dict())
            self.assertEqual(storage.load(root, preset.name), preset)
            self.assertTrue(all(name.startswith("context_") for name in os.listdir(root)))

    def test_corrupt_preset_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "context_corrupt.json"), "w") as stream:
                stream.write("{broken")
            with self.assertRaises(ValueError):
                storage.listing(root, "image")
