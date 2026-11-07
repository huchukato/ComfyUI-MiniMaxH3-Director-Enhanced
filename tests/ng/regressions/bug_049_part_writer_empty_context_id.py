"""BUG-049: part_writer._shown and _pictures lose reference images when context_id is empty.

When a user connects an Image context card in ComfyUI, the widget context_id defaults to empty ("").
In the compiled plan (plan_preview / context_build.py), the image is identified by its deterministic
fallback id, e.g. "image_alice".

In ng/adapters/part_writer.py:
- _shown builds:
    files = {entry["widgets"].get("context_id"): entry["widgets"].get("image")
             for entry in contexts if entry.get("media") == "image"}
  When context_id is "", files maps "" -> "alice.png".
  facts["pictures"] contains [("<Picture 1>", "image_alice")].
  files.get("image_alice") returns None.
  images("image", "") raises OSError/ValueError, which is caught and silently skipped.
  As a result, shown and data are empty ([]), and vlm_generate receives NO reference images
  when writing the part prompt with a vision model.

In ng/core/part_writer.py:
- _pictures fallback for parts without explicit picture labels checks:
    if entry.get("media") == "image" and entry["widgets"].get("image") and entry["widgets"].get("context_id")
  Because context_id is "", all image cards without an explicit context_id are discarded.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
adapter = module("ng.adapters.part_writer")
core = module("ng.core.part_writer")


class PartWriterEmptyContextId(unittest.TestCase):
    def setUp(self):
        self.contexts_empty_id = [
            {
                "media": "image",
                "widgets": {
                    "name": "Alice",
                    "context_id": "",  # standard default for user cards
                    "image": "alice.png",
                    "usage": "reference",
                    "content": "character",
                },
            }
        ]
        self.contexts_explicit_id = [
            {
                "media": "image",
                "widgets": {
                    "name": "Alice",
                    "context_id": "ctx_alice_explicit",
                    "image": "alice.png",
                    "usage": "reference",
                    "content": "character",
                },
            }
        ]

    def fake_images(self, media, source):
        if source == "alice.png":
            return [b"fake_jpeg_bytes"]
        raise OSError(f"File not found: {source}")

    def test_bug_049_shown_must_include_images_when_context_id_is_empty(self):
        facts = {"pictures": [("<Picture 1>", "image_alice")]}
        with patch.object(adapter, "images", side_effect=self.fake_images):
            shown, data = adapter._shown(facts, self.contexts_empty_id)

        self.assertEqual(
            shown,
            [("<Picture 1>", "image_alice")],
            "_shown must resolve image files by fallback context ID when context_id is empty",
        )
        self.assertEqual(
            len(data),
            1,
            "_shown must load image data for reference pictures when context_id is empty",
        )

    def test_bug_049_pictures_fallback_must_include_cards_when_context_id_is_empty(self):
        chunk = {"prompt_labels": {}}
        pics = core._pictures(chunk, self.contexts_empty_id)

        self.assertTrue(
            len(pics) > 0,
            "_pictures fallback must not discard image cards whose context_id is empty",
        )
        self.assertEqual(pics[0][1], "image_alice")

    def test_control_shown_with_explicit_context_id(self):
        facts = {"pictures": [("<Picture 1>", "ctx_alice_explicit")]}
        with patch.object(adapter, "images", side_effect=self.fake_images):
            shown, data = adapter._shown(facts, self.contexts_explicit_id)

        self.assertEqual(shown, [("<Picture 1>", "ctx_alice_explicit")])
        self.assertEqual(len(data), 1)

    def test_control_pictures_with_explicit_context_id(self):
        chunk = {"prompt_labels": {}}
        pics = core._pictures(chunk, self.contexts_explicit_id)

        self.assertEqual(pics, [("", "ctx_alice_explicit")])


if __name__ == "__main__":
    unittest.main()
