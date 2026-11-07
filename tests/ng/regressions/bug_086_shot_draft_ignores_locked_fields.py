r"""Regression test for BUG-086: shot_draft.parse_draft ignores record['locked_fields'], allowing AI to modify locked timing, text, media, and spoken properties.

Where:
- ng/core/shot_draft.py:126-144 (`parse_draft`)
- ng/core/shot_draft.py:85-114 (`_field_value`)
- ng/core/auto_direct.py:68-75 (`parse_direction`)

Contrast with:
- ng/core/shot_draft.py:35 (`draft_prompt`):
  "Use existing Shot IDs; never add, delete or reorder Shots. Respect locked_fields."
- ng/core/shot_draft.py:27-28 (`draft_prompt` payload):
  shots = [{key: r.get(key, [] if key in ("media", "spoken", "locked_fields") else "")
            for key in ("id", "start", "end", "text", "media", "spoken", "locked_fields")} for r in records]
- ng/core/shot_document.py:13:
  LOCK_FIELDS = ("timing", "text", "media", "spoken")
- ng/core/shot_document.py:4:
  "Drafts and locks are editing metadata; only active text, media and spoken lines compile."
- ng/core/shot_document.py:173-176:
  locks = fields.read_texts(record, "locked_fields", path)
  if any(value not in LOCK_FIELDS for value in locks):
      raise SchemaError(path + ".locked_fields", "expected timing, text, media or spoken")
- js/ng/h3s_ai.js:89-91:
  // A stored text lock (locked_fields) still protects a shot from AI text, even without a lock control in the Studio.
  const open = new Map(S.shots.filter((shot) => !(shot.locked_fields || []).includes("text")).map((shot) => [shot.id, shot.text]));
  const texts = (suggestion.patches || []).filter((patch) => open.has(patch.shot_id) && typeof patch.fields?.text === "string" && patch.fields.text.trim());
- js/ng/h3s_studio.js:245:
  if (text === undefined || !shot || shot.text !== S.suggestionBase[id] || (shot.locked_fields || []).includes("text")) { render(); return; }

User workflow:
1. In ComfyUI Director Studio (or via the Director Python API), the user builds a project with shots.
2. The user explicitly locks one or more fields on a shot (e.g. `locked_fields = ["timing"]`, `["text"]`, `["media"]`, or `["spoken"]`)
   to protect curated cuts, prompt text, character bindings, or dialogue lines from being overwritten.
3. The user requests AI suggestions (or invokes Auto Direct / "Improve Shots").
4. The backend generates a draft prompt transmitting the shot list and its `locked_fields`, instructing the AI: "Respect locked_fields."
5. An AI model returns an ID-addressed draft proposal (`format: "h3-director-draft"`), proposing changes to fields.
6. The backend validates the AI proposal via `shot_draft.parse_draft` (called directly or through `auto_direct.parse_direction`).

What happens (Ist):
1. In `ng/core/shot_draft.py:138-144`:
   ```python
   kept = {}
   for key, value in changes.items():
       try:
           kept[key] = _field_value(key, value, by_id[identity], seconds, contexts)
       except ValueError as error:
           dropped.append("%s of %s: %s" % (key, identity, error))
       if kept:
           validated.append(dict(shot_id=identity, fields=kept))
   ```
2. `parse_draft` iterates through proposed changes in the patch. It checks `set(changes) - set(LOCK_FIELDS)`, but completely
   ignores whether `key in by_id[identity].get("locked_fields", [])`!
3. Neither `parse_draft` nor `_field_value` performs any check against `record.get("locked_fields", [])`.
4. As a result:
   - If the AI proposes a new `timing` for a shot with `locked_fields=["timing"]`, `timing` is accepted and placed in `kept`!
   - If the AI proposes a new `text` for a shot with `locked_fields=["text"]`, `text` is accepted and placed in `kept`!
   - If the AI proposes new `media` bindings for a shot with `locked_fields=["media"]`, `media` is accepted and placed in `kept`!
   - If the AI proposes new `spoken` dialogue for a shot with `locked_fields=["spoken"]`, `spoken` is accepted and placed in `kept`!
5. `dropped` does NOT record that the field is locked (it remains `None` or omits the locked field).
6. If a patch contains only locked fields, `parse_draft` validates it as a usable patch instead of dropping it and raising
   `ValueError("The draft has no usable changes...")`.
7. Downstream consumers (API routes, Director nodes, Auto Direct, or external integrations) receive patches modifying the
   user's locked fields.
8. In `js/ng/h3s_ai.js:89-91`, the client had to implement a bespoke workaround (`!(shot.locked_fields || []).includes("text")`),
   which only covers `text` in `suggest()`, leaving `timing`, `media`, and `spoken` unprotected everywhere else!

What should happen (Soll):
1. `parse_draft` must respect `record.get("locked_fields", [])`:
   - If a proposed field `key` is present in `record.get("locked_fields", [])`, the modification must NOT be accepted in `kept`.
   - The locked field must be registered in `dropped` (e.g. `"%s of %s: field is locked"`).
   - If all proposed fields for a shot are locked or invalid, the shot must not appear in `result["patches"]`.
   - If all proposed fields across all patches are locked or invalid (and there is no soundscape/music), `parse_draft`
     must raise `ValueError("The draft has no usable changes: ...")`.
   - Unlocked fields in the same patch or in other patches must continue to be validated and kept normally.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

shot_draft = module("ng.core.shot_draft")
auto_direct = module("ng.core.auto_direct")


class ShotDraftLockedFieldsRegression(unittest.TestCase):
    def setUp(self):
        self.contexts = [
            {"media": "image", "widgets": {"name": "Hero", "context_id": "hero_id", "usage": "reference"}},
            {"media": "image", "widgets": {"name": "Villain", "context_id": "villain_id", "usage": "reference"}},
        ]

    # --- Green Control Tests (Expected & Existing Behavior) ---

    def test_control_unlocked_fields_are_validated_and_accepted(self):
        """When fields are unlocked, valid proposals for text, media, and spoken are accepted. Timing never is: the shot
        times are the user's (decision 2026-10-13), the AI writes text that fits them."""
        records = [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "Hero stands in the rain.",
                "media": [],
                "spoken": [],
                "locked_fields": [],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "timing": {"start": 0.0, "end": 4.0},
                        "text": "Hero walks through the rain.",
                        "media": [{"schema_version": 1, "context_id": "hero_id", "role": "reference"}],
                        "spoken": [
                            {"schema_version": 1, "text": "It begins.", "speaker_id": "hero_id", "voice": "Hero", "language": "English", "delivery": "says"}
                        ],
                    },
                }
            ],
        }
        result = shot_draft.parse_draft(data, records, 10.0, self.contexts)
        self.assertEqual(len(result["patches"]), 1)
        patch = result["patches"][0]
        self.assertEqual(patch["shot_id"], "s1")
        self.assertNotIn("timing", patch["fields"])
        self.assertEqual(patch["fields"]["text"], "Hero walks through the rain.")
        self.assertEqual(len(patch["fields"]["media"]), 1)
        self.assertEqual(len(patch["fields"]["spoken"]), 1)
        self.assertEqual(result.get("dropped"), ["timing of s1: shot times stay as set"])

    def test_control_invalid_field_value_is_dropped_while_valid_are_kept(self):
        """When an unlocked field has an invalid value, that field is dropped while valid fields stay."""
        records = [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "Hero stands in the rain.",
                "media": [],
                "spoken": [],
                "locked_fields": [],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "timing": {"start": 0.0, "end": 99.0},  # Invalid: exceeds seconds (10.0)
                        "text": "Hero looks around.",           # Valid
                    },
                }
            ],
        }
        result = shot_draft.parse_draft(data, records, 10.0, self.contexts)
        self.assertEqual(len(result["patches"]), 1)
        self.assertNotIn("timing", result["patches"][0]["fields"])
        self.assertEqual(result["patches"][0]["fields"]["text"], "Hero looks around.")
        self.assertIsNotNone(result.get("dropped"))
        self.assertTrue(any("timing" in d and "s1" in d for d in result["dropped"]))

    def test_control_draft_prompt_serializes_locked_fields_and_instructs_to_respect_them(self):
        """draft_prompt correctly serializes locked_fields and specifies 'Respect locked_fields.'"""
        records = [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "Hero stands.",
                "media": [],
                "spoken": [],
                "locked_fields": ["timing", "text"],
            }
        ]
        prompt = shot_draft.draft_prompt("An epic journey", 10.0, [], records)
        self.assertIn("Respect locked_fields.", prompt)
        self.assertIn('"locked_fields": ["timing", "text"]', prompt)

    # --- Red Defect Tests (Failing on Unmodified Code) ---

    def test_defect_locked_timing_field_must_be_dropped(self):
        """A draft patch proposing timing for a shot with locked_fields=['timing'] must be dropped, not accepted."""
        records = [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "Original shot prose.",
                "media": [],
                "spoken": [],
                "locked_fields": ["timing"],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "timing": {"start": 0.0, "end": 2.5},
                        "text": "Updated shot prose.",
                    },
                }
            ],
        }
        result = shot_draft.parse_draft(data, records, 10.0, self.contexts)
        patch = result["patches"][0]
        # Defect: parse_draft currently accepts locked timing into kept fields
        self.assertNotIn(
            "timing",
            patch["fields"],
            "BUG-086: parse_draft accepted locked 'timing' field into patch fields instead of dropping it",
        )
        self.assertTrue(
            any("timing" in d and "s1" in d for d in result.get("dropped") or []),
            "BUG-086: parse_draft did not record locked timing modification in dropped list",
        )

    def test_defect_locked_text_field_must_be_dropped(self):
        """A draft patch proposing text for a shot with locked_fields=['text'] must be dropped, not accepted."""
        records = [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "Locked user prompt prose.",
                "media": [],
                "spoken": [],
                "locked_fields": ["text"],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "media": [{"schema_version": 1, "context_id": "hero_id", "role": "reference"}],
                        "text": "AI altered prompt prose.",
                    },
                }
            ],
        }
        result = shot_draft.parse_draft(data, records, 10.0, self.contexts)
        patch = result["patches"][0]
        # Defect: parse_draft currently accepts locked text into kept fields
        self.assertNotIn(
            "text",
            patch["fields"],
            "BUG-086: parse_draft accepted locked 'text' field into patch fields instead of dropping it",
        )
        self.assertTrue(
            any("text" in d and "s1" in d for d in result.get("dropped") or []),
            "BUG-086: parse_draft did not record locked text modification in dropped list",
        )

    def test_defect_locked_media_and_spoken_fields_must_be_dropped(self):
        """A draft patch proposing media or spoken for a shot with locked_fields=['media', 'spoken'] must be dropped."""
        records = [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "Action description.",
                "media": [],
                "spoken": [],
                "locked_fields": ["media", "spoken"],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "text": "New action description.",
                        "media": [{"schema_version": 1, "context_id": "hero_id", "role": "reference"}],
                        "spoken": [
                            {"schema_version": 1, "text": "New dialogue", "speaker_id": "hero_id", "voice": "Hero", "language": "English", "delivery": "says"}
                        ],
                    },
                }
            ],
        }
        result = shot_draft.parse_draft(data, records, 10.0, self.contexts)
        patch = result["patches"][0]
        # Defect: parse_draft currently accepts locked media and spoken into kept fields
        self.assertNotIn(
            "media",
            patch["fields"],
            "BUG-086: parse_draft accepted locked 'media' field into patch fields instead of dropping it",
        )
        self.assertNotIn(
            "spoken",
            patch["fields"],
            "BUG-086: parse_draft accepted locked 'spoken' field into patch fields instead of dropping it",
        )
        self.assertTrue(
            any("media" in d and "s1" in d for d in result.get("dropped") or []),
            "BUG-086: parse_draft did not record locked media modification in dropped list",
        )
        self.assertTrue(
            any("spoken" in d and "s1" in d for d in result.get("dropped") or []),
            "BUG-086: parse_draft did not record locked spoken modification in dropped list",
        )

    def test_defect_all_proposed_fields_locked_must_raise_no_usable_changes(self):
        """When all proposed fields across a draft are locked, parse_draft must drop them and raise ValueError."""
        records = [
            {
                "id": "s1",
                "start": 0.0,
                "end": 5.0,
                "text": "Curated shot.",
                "media": [],
                "spoken": [],
                "locked_fields": ["timing", "text"],
            }
        ]
        data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "s1",
                    "fields": {
                        "timing": {"start": 0.0, "end": 2.5},
                        "text": "AI proposed rewrite.",
                    },
                }
            ],
        }
        # Defect: parse_draft currently accepts both locked fields and succeeds without error
        with self.assertRaises(
            ValueError,
            msg="BUG-086: parse_draft must raise ValueError('The draft has no usable changes...') when all proposed fields are locked",
        ):
            shot_draft.parse_draft(data, records, 10.0, self.contexts)


if __name__ == "__main__":
    unittest.main()
