"""BUG-074: shot_draft.plain_mentions and split._owner/_keep/parse_split crash with
AttributeError ('NoneType' object has no attribute 'casefold') when context card has name=None.

Where:
- ng/core/shot_draft.py:62 (plain_mentions)
- ng/core/split.py:74 (_owner)
- ng/core/split.py:107 (_keep)
- ng/core/split.py:120, 144, 147, 149 (parse_split)
- ng/core/shot_draft.py:115, 139 (parse_draft)
- ng/core/builder.py:344, 357 (parse_plan)
- ng/nodes/analysis_routes.py:39, 49, 58, 68, 78 (direct_scenes, build_plan)

User workflow:
1. In ComfyUI Director Studio, the user adds one or more Context Cards (Image, Video, Audio, Text).
2. The user leaves the optional 'name' widget blank or unconfigured.
   In JSON payloads from the frontend (POST /ng/direct, POST /ng/build_plan) or LiteGraph
   widget serializations, unconfigured or cleared widgets have null values:
   `{"media": "image", "widgets": {"name": None, "image": "scene.png", "context_id": "img_1"}}`.
3. The user clicks "AI: Split into shots" (direct_scenes) or "Make H3 prompt" (build_plan).
4. The provider generates a valid shot suggestion or plan.
5. The backend attempts to parse the response with parse_direction / parse_split / parse_draft / parse_plan.

What happens (Ist):
1. In shot_draft.py:62:
       names = {entry["widgets"].get("name", "").casefold() for entry in contexts}
   Because "name" is present in widgets with value None, `widgets.get("name", "")` returns None!
   Calling `.casefold()` on None raises `AttributeError: 'NoneType' object has no attribute 'casefold'`.
2. In split.py:74:
       if name and widgets.get("name", "").casefold() == name and widgets.get("context_id"):
   `widgets.get("name", "")` returns None, calling `.casefold()` raises `AttributeError`.
3. In split.py:107:
       names = {entry["widgets"].get("context_id"): entry["widgets"].get("name", "").casefold() for entry in contexts or ()}
   `widgets.get("name", "")` returns None, calling `.casefold()` raises `AttributeError`.
4. In analysis_routes.py:58, 78:
       except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
   `AttributeError` is NOT in the caught tuple!
   The route fails with an unhandled exception, returning HTTP 500 Internal Server Error and
   dumping a crash traceback into the ComfyUI server console.

What should happen (Soll):
When a context card has `name: None` (or null):
- `(widgets.get("name") or "").casefold()` should be used to safely treat None as empty string `""`.
- `plain_mentions`, `_owner`, `_keep`, `parse_split`, `parse_draft`, and `parse_plan` must parse
  valid scene suggestions without raising AttributeError.
- Unnamed context cards should participate cleanly in scene planning without crashing the server.
"""
import json
import pathlib
import sys
import unittest

TESTS_NG = pathlib.Path(__file__).resolve().parent.parent
REPO = TESTS_NG.parent.parent
sys.path.insert(0, str(TESTS_NG))
sys.path.insert(0, str(REPO.parent.parent))

from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()
shot_draft = module("ng.core.shot_draft")
split = module("ng.core.split")
auto_direct = module("ng.core.auto_direct")
builder = module("ng.core.builder")


class Bug074SplitPlainMentionsNoneNameCrash(unittest.TestCase):
    def setUp(self):
        # Context card where name widget value is None (unconfigured/null)
        self.contexts_with_none_name = [
            {
                "media": "image",
                "widgets": {
                    "name": None,
                    "image": "hero.png",
                    "context_id": "img_hero",
                    "usage": "subject",
                    "description": "A brave hero",
                },
            }
        ]
        # Control context card where name widget is empty string or a valid name
        self.contexts_with_empty_name = [
            {
                "media": "image",
                "widgets": {
                    "name": "",
                    "image": "hero.png",
                    "context_id": "img_hero",
                    "usage": "subject",
                    "description": "A brave hero",
                },
            }
        ]
        self.contexts_with_valid_name = [
            {
                "media": "image",
                "widgets": {
                    "name": "Hero",
                    "image": "hero.png",
                    "context_id": "img_hero",
                    "usage": "subject",
                    "description": "A brave hero",
                },
            }
        ]

    # --- RED TESTS (Demonstrate BUG-074 on product code) ---

    def test_plain_mentions_must_not_crash_when_context_name_is_none(self):
        """plain_mentions in shot_draft.py:62 must handle name=None without raising AttributeError."""
        try:
            text, unknown = shot_draft.plain_mentions("The hero walks into the tavern.", self.contexts_with_none_name)
        except AttributeError as error:
            self.fail(f"BUG-074: shot_draft.plain_mentions crashed on name=None: {error}")
        self.assertIn("tavern", text)

    def test_split_owner_and_keep_must_not_crash_when_context_name_is_none(self):
        """split._owner (line 74) and split._keep (line 107) must handle name=None without raising AttributeError."""
        try:
            speaker_id, voice = split._owner("Hero", self.contexts_with_none_name)
        except AttributeError as error:
            self.fail(f"BUG-074: split._owner crashed on name=None: {error}")

        shots = [
            {
                "id": "ai-1",
                "start": 0.0,
                "end": 5.0,
                "text": "Hero speaks",
                "media": [],
                "spoken": [{"schema_version": 1, "text": "Hello", "speaker_id": "", "voice": "Hero", "language": "English", "delivery": "says"}],
                "locked_fields": [],
                "draft": None,
            }
        ]
        try:
            kept = split._keep(shots, "@Hero says: Welcome to the tavern", self.contexts_with_none_name)
        except AttributeError as error:
            self.fail(f"BUG-074: split._keep crashed on name=None: {error}")

    def test_parse_split_and_parse_draft_must_not_crash_when_context_name_is_none(self):
        """parse_split and parse_draft must successfully parse AI suggestions when context cards have name=None."""
        split_data = {
            "shots": [
                {
                    "start_s": 0.0,
                    "end_s": 4.0,
                    "action": "A figure walks slowly through the dense forest.",
                    "camera": "Slow pan left",
                    "lines": [
                        {
                            "speaker": "Narrator",
                            "text": "The journey begins here.",
                            "delivery": "says",
                            "language": "English",
                        }
                    ],
                }
            ],
            "look": "Cinematic 35mm film",
            "soundscape": "Wind rustling through autumn leaves",
            "music": "Subtle orchestral strings",
        }
        try:
            result = split.parse_split(split_data, 4.0, self.contexts_with_none_name, keep="@Hero says: Onward")
        except AttributeError as error:
            self.fail(f"BUG-074: split.parse_split crashed on name=None: {error}")
        self.assertIn("shots", result)

        draft_records = [
            {
                "id": "ai-1",
                "start": 0.0,
                "end": 4.0,
                "text": "A figure walks slowly.",
                "media": [],
                "spoken": [],
            }
        ]
        draft_data = {
            "format": "h3-director-draft",
            "schema_version": 1,
            "patches": [
                {
                    "shot_id": "ai-1",
                    "fields": {
                        "text": "A figure runs quickly through the mist.",
                    },
                }
            ],
        }
        try:
            draft_result = shot_draft.parse_draft(draft_data, draft_records, 4.0, self.contexts_with_none_name)
        except AttributeError as error:
            self.fail(f"BUG-074: shot_draft.parse_draft crashed on name=None: {error}")
        self.assertEqual(len(draft_result["patches"]), 1)

    # --- GREEN CONTROLS (Verify expected behavior on normal input) ---

    def test_control_plain_mentions_and_parse_split_with_empty_or_valid_name(self):
        """Control: plain_mentions and parse_split work properly when name is empty string or valid string."""
        text1, _ = shot_draft.plain_mentions("The hero walks into the tavern.", self.contexts_with_empty_name)
        self.assertIn("tavern", text1)

        text2, _ = shot_draft.plain_mentions("The @Hero walks into the tavern.", self.contexts_with_valid_name)
        self.assertIn("@Hero", text2)

        split_data = {
            "shots": [
                {
                    "start_s": 0.0,
                    "end_s": 4.0,
                    "action": "A figure walks slowly through the dense forest.",
                    "camera": "Slow pan left",
                    "lines": [
                        {
                            "speaker": "Hero",
                            "text": "The journey begins here.",
                            "delivery": "says",
                            "language": "English",
                        }
                    ],
                }
            ]
        }
        result = split.parse_split(split_data, 4.0, self.contexts_with_valid_name)
        self.assertIn("shots", result)
        parsed_shots = json.loads(result["shots"])
        self.assertEqual(len(parsed_shots["shots"]), 1)
        # Verify speaker was resolved to img_hero
        self.assertEqual(parsed_shots["shots"][0]["spoken"][0]["speaker_id"], "img_hero")


if __name__ == "__main__":
    unittest.main()
