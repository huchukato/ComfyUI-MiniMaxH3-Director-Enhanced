r"""Regression test for BUG-084: split._keep ignores non-'says' deliveries and corrupts language tags.

Where:
- ng/core/split.py:96-118 (`_keep`)
- ng/core/split.py:121-161 (`parse_split`)
- ng/core/auto_direct.py:68-75 (`parse_direction`)

Contrast with:
- ng/core/split.py:13:
  DELIVERIES = ("says", "sings", "whispers", "shouts", "murmurs")
- ng/core/split.py:43-45 (`split_prompt`):
  "delivery is one of %s." % ", ".join(DELIVERIES)
- ng/core/split.py:87-88 (`_lines`):
  delivery = fields.read_str(line, "delivery", here, "says").strip().lower()
  language = " ".join(DELIMITERS.sub(" ", fields.read_str(line, "language", here, "English")).split()) or "English"
- ng/core/shot_bindings.py:106 (`spoken_text`):
  lines.append("%s [%s] %s: %s" % (speaker, spoken.language or "English", spoken.delivery or "says", s))
- minimax_plan.py:867-869 (`DIALOGUE_RE`):
  r"^@(?:ref(?P<slot>\d+)|voice\((?P<voice>[^)]*)\)|audio(?P<audio>\d+))\s*(?:\[(?P<lang>[^\]]+)\])?\s*(?P<delivery>[^:]*):\s*(?P<line>.+)$"

User workflow:
1. In ComfyUI Director Studio or via Auto Direct API (`/director/direct`), the user triggers "AI: split into shots".
2. The user has pre-written spoken dialogue or lyrics they want to preserve from the Scene / Prompt / keep field, e.g.:
   - `@Mage whispers: Settle your spirit.` (delivery other than "says")
   - `@Mage [German] says: Willkommen zurueck.` (explicit language tag)
   - `@Mage [Japanese] whispers: Konnichiwa.` (language tag + non-says delivery)
   - `Narrator [French] says: Il etait une fois.` (narrator with language tag)
3. Auto Direct calls `parse_direction(answer, seconds, contexts, current, keep=..., sung=...)`.
4. Downstream, `_keep(shots, keep, contexts)` is executed to replace the AI's generated lines for those speakers
   with the user's explicit lines.

What happens (Ist):
1. In `ng/core/split.py:101`:
   ```python
   found = re.match(r"^\s*(@?)([^:]+?)\s+says:\s*(.+)$", line)
   ```
   The regex hardcodes `\s+says:\s*`!
2. When the user specifies any delivery other than "says" (e.g. `sings:`, `whispers:`, `shouts:`, `murmurs:`),
   `re.match` fails completely.
   The user's line is discarded (`_keep` returns `[]`), `kept_dialogue` is omitted from the result,
   and the AI's hallucinated lines for that speaker remain in the shots unmodified.
3. When the user includes a language tag (e.g. `@Mage [German] says: ...`), `group(2)` captures `"Mage [German]"`.
   - `name.casefold()` becomes `"mage [german]"`.
   - `_owner("Mage [German]", contexts)` fails to match the context card `"Mage"`, returning `("", "mage german")`.
   - `key(line) == speaker` (`"mage" == "mage [german]"`) evaluates to False, so the AI's lines in Shot 0 are NOT removed.
   - The user's line is appended to the LAST shot (`shots[-1]`) with `speaker_id=""`, `voice="mage german"`,
     and `language="English"`.
   - The Subject connection to `@Mage` is lost, the voice is corrupted to `"mage german"`, the language tag is ignored,
     and both the old AI line and the corrupted user line exist simultaneously.
4. For `Narrator [French] says: ...`:
   `name.casefold() == "narrator"` evaluates to False (`"narrator [french]" != "narrator"`).
   `_owner` returns `("", "narrator french")`, corrupting the narrator's voice and hardcoding `"English"`.

What should happen (Soll):
1. `_keep` should recognize all supported deliveries (`says`, `sings`, `whispers`, `shouts`, `murmurs`)
   and any optional bracketed language tag `[<language>]` before the delivery.
2. The user's lines with non-default deliveries (`whispers`, `sings`, etc.) should replace the AI's lines for that speaker,
   preserving `delivery` in the shot's `spoken` entry and including the text in `result["kept_dialogue"]`.
3. Language tags in `[<language>]` should be parsed into the `language` field of the `spoken` entry,
   leaving the speaker name clean so context lookup (`speaker_id`) succeeds and `voice` is not mangled.
4. Narrator lines with language tags (`Narrator [German] says: ...`) should remain narrator lines (`speaker_id=""`,
   `voice="a narrator"`, `language="German"`).

Run:
    D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe -B tests/ng/regressions/bug_084_split_keep_dialogue_delivery_and_language.py
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NG_TESTS = os.path.dirname(HERE)
if NG_TESTS not in sys.path:
    sys.path.insert(0, NG_TESTS)

from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()

split_mod = module("ng.core.split")
auto_direct = module("ng.core.auto_direct")

MAGE = {"media": "image", "widgets": {"name": "Mage", "context_id": "ctx_mage"}}


def shots_of(result):
    data = json.loads(result["shots"])
    return data["shots"]


class SplitKeepDialogueDeliveryAndLanguageTests(unittest.TestCase):
    def setUp(self):
        self.ai_answer = {
            "look": "A mysterious library at midnight.",
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 4,
                    "action": "The mage reads an ancient tome.",
                    "camera": "Slow dolly",
                    "lines": [{"speaker": "Mage", "delivery": "says", "language": "English", "text": "AI generated greeting."}]
                },
                {
                    "start_s": 4,
                    "end_s": 8,
                    "action": "The mage looks at the shadows.",
                    "camera": "Close-up",
                    "lines": []
                }
            ],
            "soundscape": "Wind howling outside",
            "music": "N/A"
        }

    # -------------------------------------------------------------------------
    # Green Controls: Expected behavior that must always pass on unmodified code
    # -------------------------------------------------------------------------

    def test_green_control_standard_says_replaces_ai_dialogue(self):
        """Standard '@Speaker says: text' replaces AI lines and maps speaker_id correctly."""
        keep = "@Mage says: Welcome back.\nNarrator says: Long ago."
        result = auto_direct.parse_direction(json.dumps(self.ai_answer), 8, [MAGE], keep=keep)
        shots = shots_of(result)

        # Mage line replaced in shot 0
        self.assertEqual([l["text"] for l in shots[0]["spoken"]], ["Welcome back."])
        self.assertEqual(shots[0]["spoken"][0]["speaker_id"], "ctx_mage")
        self.assertEqual(shots[0]["spoken"][0]["voice"], "a narrator")
        self.assertEqual(shots[0]["spoken"][0]["delivery"], "says")
        self.assertEqual(shots[0]["spoken"][0]["language"], "English")

        # Narrator placed in last shot
        self.assertEqual(len(shots[1]["spoken"]), 1)
        self.assertEqual(shots[1]["spoken"][0]["text"], "Long ago.")
        self.assertEqual(shots[1]["spoken"][0]["speaker_id"], "")
        self.assertEqual(shots[1]["spoken"][0]["voice"], "a narrator")

        # kept_dialogue reported
        self.assertEqual(result.get("kept_dialogue"), ["Welcome back.", "Long ago."])

    def test_green_control_empty_keep_retains_ai_dialogue(self):
        """Empty or None keep leaves AI-generated dialogue untouched."""
        result = auto_direct.parse_direction(json.dumps(self.ai_answer), 8, [MAGE], keep="")
        shots = shots_of(result)
        self.assertEqual([l["text"] for l in shots[0]["spoken"]], ["AI generated greeting."])
        self.assertNotIn("kept_dialogue", result)

    def test_green_control_unrelated_text_without_dialogue_syntax_ignored(self):
        """Prose or comments without '<Speaker> says:' are safely ignored."""
        keep = "Just some notes about lighting and scenery.\nNo dialogue here."
        result = auto_direct.parse_direction(json.dumps(self.ai_answer), 8, [MAGE], keep=keep)
        shots = shots_of(result)
        self.assertEqual([l["text"] for l in shots[0]["spoken"]], ["AI generated greeting."])
        self.assertNotIn("kept_dialogue", result)

    # -------------------------------------------------------------------------
    # Red Defect Tests: Failing on unmodified code due to BUG-084
    # -------------------------------------------------------------------------

    def test_red_defect_keep_dialogue_with_custom_delivery_is_dropped(self):
        """BUG-084: When user specifies delivery other than 'says' (e.g. 'whispers', 'sings', 'shouts'),
        _keep regex strictly expects 'says:', discarding user lines and leaving AI lines unreplaced.
        """
        keep = "@Mage whispers: Settle your spirit."
        result = auto_direct.parse_direction(json.dumps(self.ai_answer), 8, [MAGE], keep=keep)
        shots = shots_of(result)

        # The AI's generated line must be replaced by the user's line
        self.assertEqual([l["text"] for l in shots[0]["spoken"]], ["Settle your spirit."],
                         "User's dialogue with delivery 'whispers' must replace AI line, not be dropped")
        self.assertEqual(shots[0]["spoken"][0]["speaker_id"], "ctx_mage")
        self.assertEqual(shots[0]["spoken"][0]["delivery"], "whispers",
                         "Preserved line must keep the user's specified delivery 'whispers'")
        self.assertEqual(result.get("kept_dialogue"), ["Settle your spirit."],
                         "kept_dialogue must include user lines with non-says deliveries")

    def test_red_defect_keep_dialogue_with_language_tag_mangles_speaker_and_voice(self):
        """BUG-084: When dialogue has a language tag like '@Mage [German] says:', _keep captures
        'Mage [German]' as the name, failing context lookup, wiping speaker_id to '', corrupting
        voice to 'mage german', ignoring 'German' (forcing 'English'), and failing to replace AI line.
        """
        keep = "@Mage [German] says: Willkommen zurueck."
        result = auto_direct.parse_direction(json.dumps(self.ai_answer), 8, [MAGE], keep=keep)
        shots = shots_of(result)

        # Shot 0 AI line must be replaced (not duplicated into Shot 1)
        self.assertEqual([l["text"] for l in shots[0]["spoken"]], ["Willkommen zurueck."],
                         "User line with language tag must replace AI line in shot 0")
        self.assertEqual(shots[0]["spoken"][0]["speaker_id"], "ctx_mage",
                         "Speaker ID must resolve to ctx_mage, not be wiped to empty string")
        self.assertEqual(shots[0]["spoken"][0]["voice"], "a narrator",
                         "Voice must be 'a narrator', not corrupted to 'mage german'")
        self.assertEqual(shots[0]["spoken"][0]["language"], "German",
                         "Language must be preserved as 'German', not coerced to 'English'")
        self.assertEqual(shots[1]["spoken"], [],
                         "Corrupted line must not be dumped into the last shot")

    def test_red_defect_narrator_with_language_tag_mangles_voice_and_language(self):
        """BUG-084: When narrator line has a language tag 'Narrator [French] says:', _keep fails
        the 'narrator' equality check, treats it as a named speaker with voice 'narrator french',
        and coerces language to 'English'.
        """
        keep = "Narrator [French] says: Il etait une fois."
        result = auto_direct.parse_direction(json.dumps(self.ai_answer), 8, [MAGE], keep=keep)
        shots = shots_of(result)

        self.assertEqual(len(shots[1]["spoken"]), 1)
        spoken = shots[1]["spoken"][0]
        self.assertEqual(spoken["text"], "Il etait une fois.")
        self.assertEqual(spoken["speaker_id"], "")
        self.assertEqual(spoken["voice"], "a narrator",
                         "Narrator voice must remain 'a narrator', not 'narrator french'")
        self.assertEqual(spoken["language"], "French",
                         "Language must be preserved as 'French', not forced to 'English'")

    def test_red_defect_delivery_and_language_combined(self):
        """BUG-084: When user specifies both language tag and non-says delivery
        (e.g. '@Mage [Japanese] whispers: Konnichiwa.'), regex fails completely and drops the line.
        """
        keep = "@Mage [Japanese] whispers: Konnichiwa."
        result = auto_direct.parse_direction(json.dumps(self.ai_answer), 8, [MAGE], keep=keep)
        shots = shots_of(result)

        self.assertEqual([l["text"] for l in shots[0]["spoken"]], ["Konnichiwa."],
                         "Line with both language tag and custom delivery must replace AI line")
        spoken = shots[0]["spoken"][0]
        self.assertEqual(spoken["speaker_id"], "ctx_mage")
        self.assertEqual(spoken["voice"], "a narrator")
        self.assertEqual(spoken["language"], "Japanese")
        self.assertEqual(spoken["delivery"], "whispers")
        self.assertEqual(result.get("kept_dialogue"), ["Konnichiwa."])


if __name__ == "__main__":
    unittest.main()
