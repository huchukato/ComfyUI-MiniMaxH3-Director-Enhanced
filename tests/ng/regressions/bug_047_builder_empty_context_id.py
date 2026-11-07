"""BUG-047: _bind and _descriptions lose all picture bindings and descriptions when context_id is empty.

When a user adds an image card in ComfyUI (e.g. for a place or figure view), the widget
context_id defaults to empty (""). It is an optional, advanced widget.

In ng/core/builder.py:
- _bind builds:
    ids = {entry["widgets"].get("name"): entry["widgets"].get("context_id") for entry in contexts}
  and then checks:
    shot["media"] += [...] for name in sorted(names) if ids.get(name)
  Because ids.get(name) is "", the check evaluates to False, and all media bindings (uses)
  for views/places are discarded.
- _descriptions checks:
    if widgets.get("context_id") and not ...:
        out[widgets["context_id"]] = ...
  Because widgets.get("context_id") is "", the generated descriptions for the cards are
  never returned (out is empty {}).

Everywhere else in the system (e.g. item_from_widgets in context_build.py or contextId in JS),
an empty context_id falls back to the deterministic ID f"{media}_{slug(name)}".
builder._bind and builder._descriptions must do the same.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

builder = module("ng.core.builder")


class BuilderEmptyContextId(unittest.TestCase):
    def test_bug_047_bind_preserves_uses_when_context_id_is_empty(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Castle",
                    "image": "castle.png",
                    "description": "",
                    "context_id": "",  # standard default for user cards
                    "content_roles": "",
                    "usage_roles": "place",
                },
            }
        ]
        result = {
            "shots": json.dumps(
                {
                    "shots": [
                        {
                            "id": "s1",
                            "name": "Shot 1",
                            "start": 0,
                            "end": 5,
                            "action": "We see the castle.",
                            "media": [],
                            "spoken": [],
                        }
                    ]
                }
            )
        }
        uses = [{"Castle"}]

        bound = builder._bind(result, contexts, uses)
        data = json.loads(bound["shots"])
        shot_media = data["shots"][0]["media"]

        self.assertTrue(
            len(shot_media) > 0,
            "_bind must not drop shot media bindings when context_id is empty",
        )
        self.assertEqual(shot_media[0].get("context_id"), "image_castle")

    def test_bug_047_descriptions_preserved_when_context_id_is_empty(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Castle",
                    "image": "castle.png",
                    "description": "",
                    "context_id": "",  # standard default
                    "content_roles": "",
                    "usage_roles": "place",
                },
            }
        ]
        answer_data = {
            "describe": {
                "Castle": "A dark gothic stone castle perched atop an ocean cliff."
            }
        }

        descs = builder._descriptions(answer_data, contexts)
        self.assertIn(
            "image_castle",
            descs,
            "_descriptions must return the generated description keyed by fallback id when context_id is empty",
        )
        self.assertEqual(
            descs.get("image_castle"),
            "A dark gothic stone castle perched atop an ocean cliff.",
        )

    def test_control_bind_with_explicit_context_id(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Castle",
                    "image": "castle.png",
                    "description": "",
                    "context_id": "ctx_castle_explicit",
                    "content_roles": "",
                    "usage_roles": "place",
                },
            }
        ]
        result = {
            "shots": json.dumps(
                {
                    "shots": [
                        {
                            "id": "s1",
                            "name": "Shot 1",
                            "start": 0,
                            "end": 5,
                            "action": "We see the castle.",
                            "media": [],
                            "spoken": [],
                        }
                    ]
                }
            )
        }
        uses = [{"Castle"}]

        bound = builder._bind(result, contexts, uses)
        data = json.loads(bound["shots"])
        self.assertEqual(
            data["shots"][0]["media"][0]["context_id"], "ctx_castle_explicit"
        )

    def test_control_descriptions_with_explicit_context_id(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Castle",
                    "image": "castle.png",
                    "description": "",
                    "context_id": "ctx_castle_explicit",
                    "content_roles": "",
                    "usage_roles": "place",
                },
            }
        ]
        answer_data = {
            "describe": {
                "Castle": "A dark gothic stone castle perched atop an ocean cliff."
            }
        }

        descs = builder._descriptions(answer_data, contexts)
        self.assertEqual(
            descs.get("ctx_castle_explicit"),
            "A dark gothic stone castle perched atop an ocean cliff.",
        )


if __name__ == "__main__":
    unittest.main()
