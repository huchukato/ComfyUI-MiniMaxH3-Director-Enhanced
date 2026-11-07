"""BUG-065: a preset saved on an audio card silently replaces the image preset with the same name.

User flow: on an image card (a character) save the preset "Maya". On the audio card for her voice save the preset "Maya" too.
The panel lists presets per media type ("Saved presets" shows only the cards of this type) and promises only that "Saving the
same name again replaces it". The file name is derived from the name alone, so the audio save overwrites the image preset:
the image list no longer offers "Maya" and the picture preset is gone.

Expected: presets of different media types never replace each other (the route already refuses to load a preset into a card of
another media type, so the types are separate namespaces from the user's point of view).

Run: python -B tests/ng/regressions/bug_065_preset_name_shared_across_media.py
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _pack import module  # noqa: E402

presets = module("ng.adapters.presets")
context_build = module("ng.core.context_build")
core_presets = module("ng.core.presets")


def save_like_route(root, media, name, widgets):
    """What POST /ng/presets does: item_from_widgets -> ContextPreset -> presets.save."""
    item = context_build.item_from_widgets(media, widgets)
    preset = core_presets.ContextPreset.from_dict({"schema_version": 1, "name": name, "item": item.to_dict()})
    presets.save(root, preset.to_dict())


IMAGE = {"image": "maya.png", "name": "Maya", "content": "character", "usage": "reference", "preserve": "high"}
AUDIO = {"audio": "maya_voice.wav", "name": "Maya voice", "content": "voice", "usage": "reference", "preserve": "high"}


class PresetNamespaces(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_control_different_names_keep_both(self):
        save_like_route(self.root, "image", "Maya", IMAGE)
        save_like_route(self.root, "audio", "Maya voice", AUDIO)
        self.assertEqual(presets.listing(self.root, "image"), ["Maya"])
        self.assertEqual(presets.listing(self.root, "audio"), ["Maya voice"])

    def test_control_same_media_same_name_replaces(self):
        save_like_route(self.root, "image", "Maya", IMAGE)
        save_like_route(self.root, "image", "Maya", {**IMAGE, "image": "maya2.png"})
        self.assertEqual(presets.listing(self.root, "image"), ["Maya"])

    def test_bug_065_same_name_on_another_media_keeps_the_image_preset(self):
        save_like_route(self.root, "image", "Maya", IMAGE)
        save_like_route(self.root, "audio", "Maya", AUDIO)
        self.assertEqual(presets.listing(self.root, "image"), ["Maya"],
                         "saving the audio preset 'Maya' removed the image preset 'Maya'")
        self.assertEqual(presets.listing(self.root, "audio"), ["Maya"])


if __name__ == "__main__":
    unittest.main()
