"""A card with an empty Context ID gets the same id in Python and in the Studio (tests/ng/js/test_h3s_views.mjs, BUG-003)."""
import unittest

from _pack import module

build = module("ng.core.context_build")

CASES = (
    ("image", {"context_id": "ctx_1", "name": "Mage"}, "ctx_1"),
    ("image", {"context_id": "", "name": "Mage Två"}, "image_mage_tv"),
    ("image", {"context_id": "", "name": "", "image": "people/My Pic.png [input]"}, "image_my_pic"),
    ("text", {"context_id": "", "name": "", "text": "  Hello, world of H3 and more text here"}, "text_hello_world_of_h3_and"),
    ("audio", {"context_id": "", "name": "", "audio": ""}, "audio_audio"),
)


class EmptyContextId(unittest.TestCase):
    def test_python_ids_match_the_studio_rule(self):
        for media, widgets, expected in CASES:
            with self.subTest(widgets=widgets):
                self.assertEqual(build.item_from_widgets(media, widgets).id, expected)


if __name__ == "__main__":
    unittest.main()
