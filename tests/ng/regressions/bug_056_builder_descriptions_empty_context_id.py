"""BUG-056: Make H3 prompt builder._descriptions drops the AI's picture descriptions when context_id is empty.

Real flow (Director Studio, "Make H3 prompt"):
1. The user adds an image context card in ComfyUI for a character or place. Its advanced widget
   `context_id` defaults to empty ("") -- this is the standard for every newly added card.
2. The user leaves the card's description empty and starts "Make H3 prompt".
3. The model answers the plan. For every picture card that has NO description the AI writes one
   sentence into `describe` ("A dark gothic stone castle ...", "A battle-hardened warrior ...").
   The Director Studio's buildPrompt() writes these texts onto the cards (h3s_studio.js:
   `plan.descriptions?.[contextId(values(card), media)]`), and the compiler then names the figure
   with that description in EVERY render part ("Describe each character's look once ...").

In ng/core/builder.py, _descriptions() keys its result by the raw widget value:
    if widgets.get("context_id") and not ...description.strip() ...:
        out[widgets["context_id"]] = ...

When context_id is "" the guard `widgets.get("context_id")` is falsy, so the generated
description is never stored and the function returns {} for a project whose cards all use the
default empty context_id. The Studio then writes no description onto any card: the AI's character
look is silently lost, and every render part names the figure without it.

Everywhere else the empty context_id falls back to the deterministic id f"{media}_{slug(name)}"
(context_build.item_from_widgets, shot_draft, split, part_writer). _descriptions must do the same.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

builder = module("ng.core.builder")


class BuilderDescriptionsEmptyContextId(unittest.TestCase):
    def setUp(self):
        self.contexts_empty_id = [
            {
                "media": "image",
                "widgets": {
                    "name": "Castle",
                    "image": "castle.png",
                    "description": "",          # no description yet -> the AI should fill it
                    "context_id": "",           # standard default for user-added cards
                    "content_roles": "location",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            }
        ]
        self.contexts_explicit_id = [
            {
                "media": "image",
                "widgets": {
                    "name": "Castle",
                    "image": "castle.png",
                    "description": "",
                    "context_id": "ctx_castle_explicit",
                    "content_roles": "location",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            }
        ]
        self.answer_data = {
            "describe": {"Castle": "A dark gothic stone castle perched atop an ocean cliff."}
        }

    def test_bug_056_descriptions_kept_when_context_id_is_empty(self):
        descs = builder._descriptions(self.answer_data, self.contexts_empty_id)

        self.assertIn(
            "image_castle",
            descs,
            "_descriptions must key the AI description by the deterministic fallback id "
            "(image_castle) when context_id is empty",
        )
        self.assertEqual(
            descs.get("image_castle"),
            "A dark gothic stone castle perched atop an ocean cliff.",
        )

    def test_control_descriptions_with_explicit_context_id(self):
        descs = builder._descriptions(self.answer_data, self.contexts_explicit_id)

        self.assertEqual(
            descs.get("ctx_castle_explicit"),
            "A dark gothic stone castle perched atop an ocean cliff.",
        )


if __name__ == "__main__":
    unittest.main()
