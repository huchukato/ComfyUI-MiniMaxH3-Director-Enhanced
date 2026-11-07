"""BUG-050 (split._owner): a named character's spoken line loses its speaker binding when the
image card's `context_id` is empty.

Reachable workflow: the user adds an Image context card for a character (name "Mage"), opens the
Director Studio and runs "AI: split into shots". The Studio sends the card's live widgets to the
`/ng/direct` route (ng_read.readPayload -> widgetValues), where `context_id` is the raw widget
value. A user-added card's `context_id` widget defaults to empty (""); it is only filled with a
random id by the node's onConfigure (ng_widgets.newContextId), and the AI payload reads the widget
value as stored, not that injected fallback.

ng/core/split.py::_owner resolves a spoken line's speaker with:

    if name and widgets.get("name", "").casefold() == name and widgets.get("context_id"):
        return widgets["context_id"], "a narrator"

Because `context_id` is "" (falsy), the branch is skipped and `_owner` returns speaker_id="" with a
voice derived from the raw speaker text ("Mage") instead of the character's own voice. The
character's dialogue is therefore not bound to the Subject card in the produced shot document: the
compiler cannot assign the card's voice and reports the line's speaker as unbound.

Every other id-consuming path falls back to the deterministic id "image_<slug(name)>"
(context_build.item_from_widgets, line 28); split._owner must resolve the same fallback when the
stored context_id is empty.

Expected: _owner("Mage", <card with context_id "">) returns ("image_mage", "a narrator").
Actual (bug): it returns ("", "Mage").
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

split = module("ng.core.split")


def _card(name, context_id):
    return {"media": "image", "widgets": {"name": name, "context_id": context_id,
                                          "image": name.lower() + ".png", "usage": "reference"}}


class SplitOwnerEmptyContextId(unittest.TestCase):
    def test_owner_binds_named_speaker_when_context_id_is_empty(self):
        # The Studio AI payload for a configured card carries context_id "".
        speaker_id, voice = split._owner("Mage", [_card("Mage", "")])

        self.assertEqual(
            speaker_id, "image_mage",
            "_owner must fall back to the deterministic id image_<slug(name)> when context_id is empty, "
            "so the character's dialogue stays bound to its Subject card",
        )
        self.assertEqual(
            voice, "a narrator",
            "A named character speaks with its own voice ('a narrator'), not the raw voice label 'Mage'",
        )

    def test_owner_with_at_prefix_and_whitespace(self):
        # Real shots arrive as "@Mage"; _owner strips a leading @ and whitespace.
        speaker_id, voice = split._owner("@Mage", [_card("Mage", "")])
        self.assertEqual(speaker_id, "image_mage")
        self.assertEqual(voice, "a narrator")

    def test_owner_keeps_narrator_unbound(self):
        # A narrator (no matching card, or empty speaker) must stay speaker_id "" with the
        # narrator voice - this is correct behaviour and must not change.
        speaker_id, voice = split._owner("", [_card("Mage", "")])
        self.assertEqual(speaker_id, "")
        self.assertEqual(voice, "a narrator")

    def test_control_owner_with_explicit_context_id(self):
        # When the user has typed a context_id, the stored value is used unchanged (green control).
        speaker_id, voice = split._owner("Mage", [_card("Mage", "ctx_mage")])
        self.assertEqual(speaker_id, "ctx_mage")
        self.assertEqual(voice, "a narrator")


if __name__ == "__main__":
    unittest.main()
