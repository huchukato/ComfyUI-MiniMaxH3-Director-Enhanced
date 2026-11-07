"""BUG-050: split._owner and _keep unbind character dialogue lines when context_id is empty.

When a user adds a character image card in ComfyUI (e.g. named "Mage"), widget context_id defaults
to empty ("").

In ng/core/split.py:
- _owner checks:
    if name and widgets.get("name", "").casefold() == name and widgets.get("context_id"):
        return widgets["context_id"], "a narrator"
  Because widgets.get("context_id") is "", the check evaluates to False.
  _owner returns speaker_id = "" and voice = "Mage".
  As a result, dialogue lines spoken by the character are stripped of their speaker binding:
  they are not recognized as spoken by the character card, and the compiled plan warns
  of unbound speakers (or leaves the character's audio voice unassigned).

- _keep maps:
    names = {entry["widgets"].get("context_id"): entry["widgets"].get("name", "").casefold() for entry in contexts or ()}
    key = lambda line: names.get(line["speaker_id"], "") if line["speaker_id"] else ""
  Because context_id is "", names has no valid key for the character.
  Target shot search `any(key(line) == speaker for line in shot["spoken"])` never matches.
  The user's own dialogue lines ("@Mage says: ...") are dumped into the last shot of the project (shots[-1])
  instead of the shot where Mage speaks, and with speaker_id = "".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

split = module("ng.core.split")


class SplitEmptyContextId(unittest.TestCase):
    def setUp(self):
        self.contexts_empty_id = [
            {
                "media": "image",
                "widgets": {
                    "name": "Mage",
                    "context_id": "",  # standard default for user cards
                    "image": "mage.png",
                    "usage": "reference",
                    "content": "character",
                },
            }
        ]
        self.contexts_explicit_id = [
            {
                "media": "image",
                "widgets": {
                    "name": "Mage",
                    "context_id": "ctx_mage_explicit",
                    "image": "mage.png",
                    "usage": "reference",
                    "content": "character",
                },
            }
        ]

    def test_bug_050_owner_must_resolve_speaker_when_context_id_is_empty(self):
        speaker_id, voice = split._owner("Mage", self.contexts_empty_id)

        self.assertEqual(
            speaker_id,
            "image_mage",
            "_owner must resolve speaker_id to the character's fallback context ID when context_id is empty",
        )
        self.assertEqual(
            voice,
            "a narrator",
            "A named character content speaks with its own voice ('a narrator'), not as a raw voice label",
        )

    def test_bug_050_keep_must_place_dialogue_in_character_shot_when_context_id_is_empty(self):
        shots = [
            {
                "id": "s1",
                "spoken": [
                    {
                        "schema_version": 1,
                        "text": "Hello world.",
                        "speaker_id": "image_mage",
                        "voice": "a narrator",
                        "language": "English",
                        "delivery": "says",
                    }
                ],
            },
            {
                "id": "s2",
                "spoken": [],
            },
        ]
        keep = "@Mage says: Behold my magic power!"

        split._keep(shots, keep, self.contexts_empty_id)

        # The user's line for Mage must replace the line in Shot 1, not be dumped in Shot 2
        self.assertEqual(
            len(shots[0]["spoken"]),
            1,
            "Shot 1 where Mage speaks must receive Mage's dialogue line",
        )
        self.assertEqual(
            shots[0]["spoken"][0]["text"],
            "Behold my magic power!",
        )
        self.assertEqual(
            shots[0]["spoken"][0]["speaker_id"],
            "image_mage",
            "Preserved dialogue line must have speaker_id set to character's fallback ID",
        )
        self.assertEqual(
            len(shots[1]["spoken"]),
            0,
            "Shot 2 must remain empty when Mage speaks in Shot 1",
        )

    def test_control_owner_with_explicit_context_id(self):
        speaker_id, voice = split._owner("Mage", self.contexts_explicit_id)

        self.assertEqual(speaker_id, "ctx_mage_explicit")
        self.assertEqual(voice, "a narrator")

    def test_control_keep_with_explicit_context_id(self):
        shots = [
            {
                "id": "s1",
                "spoken": [
                    {
                        "schema_version": 1,
                        "text": "Hello world.",
                        "speaker_id": "ctx_mage_explicit",
                        "voice": "a narrator",
                        "language": "English",
                        "delivery": "says",
                    }
                ],
            },
            {
                "id": "s2",
                "spoken": [],
            },
        ]
        keep = "@Mage says: Behold my magic power!"

        split._keep(shots, keep, self.contexts_explicit_id)

        self.assertEqual(len(shots[0]["spoken"]), 1)
        self.assertEqual(shots[0]["spoken"][0]["text"], "Behold my magic power!")
        self.assertEqual(shots[0]["spoken"][0]["speaker_id"], "ctx_mage_explicit")
        self.assertEqual(len(shots[1]["spoken"]), 0)


if __name__ == "__main__":
    unittest.main()
