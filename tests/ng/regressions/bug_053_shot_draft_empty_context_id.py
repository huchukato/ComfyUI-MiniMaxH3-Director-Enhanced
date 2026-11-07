r"""BUG-053: Auto Direct Shot-Draft verwirft Bildbindungen und Sprecher als unbekannte Context-ID bei leerem context_id-Widget.

Wenn ein Benutzer im Director Context-Karten anlegt (z. B. Bildkarte 'Alice'), ist das Widget
context_id standardmäßig leer (""). Im Studio und im Backend-Compiler erhält die Karte dadurch
die deterministische Fallback-ID (z. B. 'image_alice' via context_build.item_from_widgets / h3s_content.contextId).

Wenn im Director Studio bei bestehenden Shots Auto Direct ausgeführt wird, erzeugt die KI
einen Shot-Draft (Format 'h3-director-draft'), der Änderungen für Shots vorschlägt, z. B.
eine Bildbindung an einen Shot oder eine Sprecherzeile für die Figur unter ihrer Fallback-ID:
  {"shot_id": "s1", "fields": {"media": [{"schema_version": 1, "context_id": "image_alice", "role": "context"}]}}

In ng/core/shot_draft.py:
  by_id = {entry["widgets"].get("context_id"): entry for entry in contexts or ()}
Da context_id leer ist (""), enthält by_id nur den Schlüssel "":
  identity = entry["context_id"] if key == "media" else entry["speaker_id"]
  if identity and identity not in by_id and entry not in existing:
      raise ValueError("The draft binds an unknown Context ID: %s." % identity)
Da 'image_alice' nicht in by_id enthalten ist, bricht die Validierung mit ValueError ab:
  "The draft binds an unknown Context ID: image_alice."
Das vorgeschlagene Feld (media oder spoken) wird in parse_draft() komplett verworfen (dropped).
Wenn der Patch keine weiteren Felder enthält, scheitert der gesamte Draft mit:
  "The draft has no usable changes: media of s1: The draft binds an unknown Context ID: image_alice."

Soll:
Wie im restlichen System (context_build.py, h3s_content.js) muss bei leerem context_id
die Fallback-ID f"{media}_{slug(name)}" aufgelöst werden, damit Draft-Vorschläge für Karten
mit Standard-Widgetwerten gültig bleiben.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

shot_draft = module("ng.core.shot_draft")


class ShotDraftEmptyContextId(unittest.TestCase):
    def test_bug_053_draft_media_binding_accepted_when_context_id_is_empty(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Alice",
                    "image": "alice.png",
                    "description": "A brave adventurer",
                    "context_id": "",  # standard default for newly added cards
                    "content_roles": "character",
                    "usage_roles": "reference",
                },
            }
        ]
        records = [
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "text": "Alice enters the castle.",
                "media": [],
                "spoken": [],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "media": [
                            {
                                "schema_version": 1,
                                "context_id": "image_alice",
                                "role": "context",
                            }
                        ]
                    },
                }
            ],
        }

        result = shot_draft.parse_draft(data, records, 10.0, contexts)

        self.assertNotIn("dropped", result, "Draft media patch must not be dropped")
        self.assertEqual(len(result["patches"]), 1)
        media_field = result["patches"][0]["fields"].get("media", [])
        self.assertEqual(len(media_field), 1)
        self.assertEqual(media_field[0]["context_id"], "image_alice")

    def test_bug_053_draft_spoken_line_accepted_when_context_id_is_empty(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Alice",
                    "image": "alice.png",
                    "description": "A brave adventurer",
                    "context_id": "",  # standard default
                    "content_roles": "character",
                    "usage_roles": "reference",
                },
            }
        ]
        records = [
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "text": "Alice speaks.",
                "media": [],
                "spoken": [],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "spoken": [
                            {
                                "schema_version": 1,
                                "text": "Greetings travelers!",
                                "speaker_id": "image_alice",
                                "voice": "a narrator",
                                "language": "English",
                                "delivery": "says",
                            }
                        ]
                    },
                }
            ],
        }

        result = shot_draft.parse_draft(data, records, 10.0, contexts)

        self.assertNotIn("dropped", result, "Draft spoken patch must not be dropped")
        self.assertEqual(len(result["patches"]), 1)
        spoken_field = result["patches"][0]["fields"].get("spoken", [])
        self.assertEqual(len(spoken_field), 1)
        self.assertEqual(spoken_field[0]["speaker_id"], "image_alice")

    def test_control_explicit_context_id_accepted(self):
        """Green control test: When context_id is explicitly set, draft patch succeeds."""
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Alice",
                    "image": "alice.png",
                    "description": "A brave adventurer",
                    "context_id": "image_alice",
                    "content_roles": "character",
                    "usage_roles": "reference",
                },
            }
        ]
        records = [
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "text": "Alice speaks.",
                "media": [],
                "spoken": [],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "media": [
                            {
                                "schema_version": 1,
                                "context_id": "image_alice",
                                "role": "context",
                            }
                        ]
                    },
                }
            ],
        }

        result = shot_draft.parse_draft(data, records, 10.0, contexts)
        self.assertEqual(len(result["patches"]), 1)

    def test_control_truly_unknown_context_id_is_rejected(self):
        """Green control test: An actually unknown context ID is still dropped."""
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Alice",
                    "image": "alice.png",
                    "description": "A brave adventurer",
                    "context_id": "image_alice",
                    "content_roles": "character",
                    "usage_roles": "reference",
                },
            }
        ]
        records = [
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "text": "Alice speaks.",
                "media": [],
                "spoken": [],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "media": [
                            {
                                "schema_version": 1,
                                "context_id": "image_ghost",
                                "role": "context",
                            }
                        ]
                    },
                }
            ],
        }

        with self.assertRaises(ValueError) as ctx:
            shot_draft.parse_draft(data, records, 10.0, contexts)
        self.assertIn("The draft binds an unknown Context ID: image_ghost", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
