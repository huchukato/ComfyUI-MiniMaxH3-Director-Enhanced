"""BUG-058 (candidate): shot_draft lets the AI re-add an already-serialized media binding whose
Context ID resolves to no connected card.

Not a duplicate of the empty-context_id family (BUG-047/049/050/052/053/056/057): those are proven
with a binding whose context_id is empty ("" or None) and the fix is "fall back to media_<slug>".
Here the binding carries a REAL, NON-EMPTY id (a card that used to be connected) that is simply no
longer in `contexts`. That stale id does not resolve through item_from_widgets (which injects the
deterministic id ONLY when the widget value is empty), so the two conditions are disjoint.

User path (Stufe A/B):
 1. Add a Character image card "Mage"; shot 1 binds it. Save. Shots JSON serialises
    shot 1.media = [{context_id: "mage_ref", role: "context"}].
 2. Reopen, delete/disconnect the "Mage" card (binding stays in saved JSON).
 3. Ask AI to improve shots. ng/adapters/auto_direct.py builds the request from
    readContexts(director): the connected contexts no longer contain "mage_ref".

What the draft path does (auto_direct.parse_direction -> shot_draft.parse_draft -> _field_value,
shot_draft.py line 103):
    if identity and identity not in by_id and entry not in existing:
        raise ValueError("The draft binds an unknown Context ID: %s." % identity)
Because entry already equals the shot's stored `existing` binding, `entry not in existing` is False,
so the unknown id is NOT refused and the stale binding is accepted unchanged.

Downstream shot_bindings.scoped_context (shot_bindings.py 53-57) resolves that binding, gets
context.item("mage_ref") is None, and emits "shot_context_unknown". The AI may keep a binding the
user can no longer re-target and the compiler reports as disconnected.

Expected (Soll): a stale, unresolvable binding echoed by the AI should be rejected like a
brand-new unknown binding (Stufe F: data-invariant violation; the identical contract is already
enforced for spoken lines via `parsed[:len(existing)] != existing`).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

shot_draft = module("ng.core.shot_draft")

class ShotDraftStaleBinding(unittest.TestCase):
    STALE_ID = "mage_ref"

    def _records(self):
        return [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "A mage conjures a flame.",
                # Serialised binding pointing at a card that is no longer connected.
                "media": [{"schema_version": 1, "context_id": self.STALE_ID, "role": "context"}],
                "spoken": [],
                "locked_fields": [],
            }
        ]

    def _contexts(self):
        # readContexts() after the "Mage" image card was deleted.
        return [
            {
                "media": "text",
                "widgets": {"name": "Scene note", "context_id": "text_scene",
                            "text": "A mage conjures a flame."},
            }
        ]

    def _draft_echo(self):
        # The AI proposes a text change and echoes the shot's own media back unchanged.
        return {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "text": "A robed mage conjures a bright flame.",
                        "media": [{"schema_version": 1, "context_id": self.STALE_ID, "role": "context"}],
                    },
                }
            ],
        }

    def test_bug_058_stale_media_binding_refused(self):
        # Refused per field, as every bad field of a draft is: the good text of the same patch stays (shot_draft keeps
        # the fields that pass and lists the dropped ones with their reason).
        result = shot_draft.parse_draft(self._draft_echo(), self._records(), seconds=10.0, contexts=self._contexts())
        fields_ = result["patches"][0]["fields"]
        self.assertNotIn("media", fields_, "A media binding whose Context ID resolves to no connected card must be refused, "
                                           "even when the AI echoes the shot's own already-serialized binding.")
        self.assertEqual(fields_["text"], "A robed mage conjures a bright flame.")
        self.assertTrue(any(self.STALE_ID in note for note in result["dropped"]), result.get("dropped"))

    def test_bug_058_control_new_binding_against_connected_card(self):
        # Same shape, but the binding names a connected image card with a valid role: accepted.
        contexts = [
            {
                "media": "image",
                "widgets": {"name": "Mage", "context_id": "image_mage", "image": "mage.png",
                            "content": "character", "usage": "reference"},
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {"media": [{"schema_version": 1, "context_id": "image_mage", "role": "context"}]},
                }
            ],
        }
        result = shot_draft.parse_draft(data, self._records(), seconds=10.0, contexts=contexts)
        self.assertTrue(result["patches"], "A media binding to a connected card must be accepted.")
        self.assertEqual(result["patches"][0]["fields"]["media"][0]["context_id"], "image_mage")


if __name__ == "__main__":
    unittest.main()

