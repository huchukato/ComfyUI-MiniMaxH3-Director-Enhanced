r"""Regression test for BUG-089: split._keep conflates unbound figure voices (speaker_id="") with the narrator, causing 'Narrator says:' to wipe out all uncarded character lines across the project and '@Figure says:' to miss its target shot and duplicate lines at the end.

Where:
- ng/core/split.py:108-118 (`_keep`)
- Downstream impact:
  - Users providing narrator lines in keep wipe out all dialogue of figures that do not possess an Image card.
  - Users providing dialogue for figures without Image cards cannot replace earlier AI proposals; lines duplicate into the last shot.

Contrast with:
- ng/core/split.py:97-98 (docstring):
  `"The user's own lines ("@Mage says: ...", "Narrator says: ...") replace the AI's lines of that speaker, in the shot where the AI first gave that speaker a line, else in the last shot. Returns the user's lines the AI did not have."`
- ng/core/split.py:71-78 (`_owner`):
  `"(speaker_id, voice) for a line: a named Content speaks with its own voice, anyone else is a described narrator."`
  Uncarded figures speak with their own named voice (`speaker_id="", voice="Wizard"`), while narrators speak with voice `"a narrator"` or `"Narrator"`.
- ng/core/shot_bindings.py:101-106:
  `voice = spoken.voice or "a narrator"`
  `speaker = "@" + subject.name if subject else "@voice(%s)" % (voice[:1].upper() + voice[1:])`

User workflow:
1. In ComfyUI Director Studio (or via API), the user creates a project with shots and dialogue.
   The project has figures that do not have dedicated reference Image cards (e.g. described characters,
   background figures, or voices like "@Wizard" and "@Guard").
2. "Auto Direct" or "Prompt Split" generates shots with dialogue:
   - Shot 1: `@Wizard` says "Fireball!" (`speaker_id="", voice="Wizard"`)
   - Shot 2: `@Guard` says "Halt!" (`speaker_id="", voice="Guard"`)
   - Shot 3: `Narrator` says "Night falls." (`speaker_id="", voice="Narrator"`)
3. The user supplies keep dialogue:
   - Scenario A: `Narrator says: The dawn breaks.`
   - Scenario B: `@Wizard says: Lightning bolt!`

What happens (Ist):
1. In `ng/core/split.py:108-118`:
   ```python
   names = {entry["widgets"].get("context_id"): widget_text(entry["widgets"], "name").casefold() for entry in contexts or ()}
   key = lambda line: names.get(line["speaker_id"], "") if line["speaker_id"] else ""
   ```
   `key` resolves only `line["speaker_id"]` via `names`. If `line["speaker_id"]` is empty `""`,
   `key(line)` unconditionally returns `""`.
2. Any figure without an image card has `speaker_id == ""` and `voice == "Wizard"`.
   Their `key(line)` evaluates to `""`.
3. In Scenario A (`Narrator says: ...`, `speaker = ""`):
   - `for shot in shots: shot["spoken"] = [line for line in shot["spoken"] if key(line) != ""]`
     Because `key(line)` is `""` for Wizard, Guard, and Narrator, `key(line) != ""` is False for all of them!
     Wizard's line in Shot 1 is DELETED. Guard's line in Shot 2 is DELETED.
     All dialogue of all uncarded figures in the entire project is wiped out!
   - `target = next((shot for shot in shots if any(key(line) == "" for line in shot["spoken"])), shots[-1])`
     matches Shot 1 (the first shot with any uncarded speaker).
     The Narrator's line is placed into Wizard's shot (Shot 1), while Shot 3 is left empty.
4. In Scenario B (`@Wizard says: Lightning bolt!`, `speaker = "wizard"`):
   - `any(key(line) == "wizard" ...)` is False for all shots because Wizard's line has `key(line) == ""`.
   - `target` falls back to `shots[-1]` (Shot 2).
   - `shot["spoken"] = [line for line in shot["spoken"] if key(line) != "wizard"]` removes nothing
     because `"" != "wizard"` is True.
   - Shot 1 retains Wizard's old line "Fireball!", and Shot 2 gets Wizard's new line "Lightning bolt!" appended.
     Wizard now speaks conflicting lines twice.

What should happen (Soll):
1. `key(line)` must inspect `line.get("voice")` when `line.get("speaker_id")` is empty:
   If `voice` is `"a narrator"` or `"narrator"` (or empty), `key` returns `""` (narrator).
   If `voice` is a named character (e.g. `"wizard"`), `key` returns `"wizard"`.
2. In Scenario A:
   Wizard in Shot 1 and Guard in Shot 2 are retained.
   Only the Narrator's line in Shot 3 is replaced.
3. In Scenario B:
   Wizard's line in Shot 1 is replaced by "Lightning bolt!".
   Shot 2 is left untouched with Guard's line only.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

split = module("ng.core.split")


class SplitKeepUnboundSpeakerKeyRegression(unittest.TestCase):
    def setUp(self):
        self.hero_card = {
            "media": "image",
            "widgets": {"name": "Hero", "context_id": "image_hero_id", "usage": "reference", "image": "hero.png"},
        }

    # --- Green Control Tests (Expected & Existing Working Behavior) ---

    def test_control_carded_subject_keep_replaces_correct_shot(self):
        """When a figure has a reference image card, _keep correctly identifies its shot

        via context_id and replaces only its lines."""
        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 3,
                    "action": "Hero stands.",
                    "lines": [{"speaker": "@Hero", "text": "We attack at dawn."}],
                },
                {
                    "start_s": 3,
                    "end_s": 6,
                    "action": "Narrator speaks.",
                    "lines": [{"speaker": "Narrator", "text": "The armies prepared."}],
                },
            ]
        }
        res = split.parse_split(data, 6, contexts=[self.hero_card], keep="@Hero says: We attack at dusk.")
        shots = json.loads(res["shots"])["shots"]

        # Shot 0 must have Hero's updated line
        self.assertEqual(len(shots[0]["spoken"]), 1)
        self.assertEqual(shots[0]["spoken"][0]["text"], "We attack at dusk.")
        self.assertEqual(shots[0]["spoken"][0]["speaker_id"], "image_hero_id")

        # Shot 1 must retain Narrator's line
        self.assertEqual(len(shots[1]["spoken"]), 1)
        self.assertEqual(shots[1]["spoken"][0]["text"], "The armies prepared.")

    def test_control_narrator_replaces_only_narrator_when_all_figures_carded(self):
        """When all figures have image cards, Narrator keep correctly replaces only the narrator."""
        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 3,
                    "action": "Hero stands.",
                    "lines": [{"speaker": "@Hero", "text": "Victory is ours."}],
                },
                {
                    "start_s": 3,
                    "end_s": 6,
                    "action": "Narrator speaks.",
                    "lines": [{"speaker": "Narrator", "text": "The war was won."}],
                },
            ]
        }
        res = split.parse_split(data, 6, contexts=[self.hero_card], keep="Narrator says: Peace returned to the land.")
        shots = json.loads(res["shots"])["shots"]

        # Hero line preserved
        self.assertEqual(len(shots[0]["spoken"]), 1)
        self.assertEqual(shots[0]["spoken"][0]["text"], "Victory is ours.")

        # Narrator line replaced in Shot 1
        self.assertEqual(len(shots[1]["spoken"]), 1)
        self.assertEqual(shots[1]["spoken"][0]["text"], "Peace returned to the land.")

    def test_control_new_uncarded_figure_appends_to_last_shot(self):
        """When the AI proposed no lines for an uncarded figure, user keep appends it to the last shot."""
        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 3,
                    "action": "Hero stands.",
                    "lines": [{"speaker": "@Hero", "text": "Forward!"}],
                },
                {
                    "start_s": 3,
                    "end_s": 6,
                    "action": "Alchemist arrives.",
                    "lines": [],
                },
            ]
        }
        res = split.parse_split(data, 6, contexts=[self.hero_card], keep="@Alchemist says: Drink this potion.")
        shots = json.loads(res["shots"])["shots"]

        self.assertEqual(len(shots[0]["spoken"]), 1)
        self.assertEqual(shots[0]["spoken"][0]["text"], "Forward!")

        self.assertEqual(len(shots[1]["spoken"]), 1)
        self.assertEqual(shots[1]["spoken"][0]["text"], "Drink this potion.")
        self.assertEqual(shots[1]["spoken"][0]["voice"], "Alchemist")     # spelled as the user wrote it (BUG-087)

    # --- Red Defect Tests (Reproducing BUG-089) ---

    def test_defect_narrator_keep_must_not_purge_uncarded_figures(self):
        """BUG-089: 'Narrator says: ...' in keep must NOT wipe out dialogue of figures

        without image cards (@Wizard, @Guard) across the project.

        Ist:
        - _keep evaluates key(line) == "" for all uncarded figures because speaker_id is ""
        - shot["spoken"] filter removes Wizard and Guard lines (key(line) != "" is False)
        - Narrator line is injected into Shot 0 (Wizard's shot)
        - Shot 1 (Guard) and Shot 2 (Narrator) become empty []

        Soll:
        - Wizard's line in Shot 0 is preserved
        - Guard's line in Shot 1 is preserved
        - Narrator's line in Shot 2 is replaced
        """
        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 3,
                    "action": "Wizard casts a spell.",
                    "lines": [{"speaker": "@Wizard", "text": "Fireball!"}],
                },
                {
                    "start_s": 3,
                    "end_s": 6,
                    "action": "Guard raises shield.",
                    "lines": [{"speaker": "@Guard", "text": "Halt!"}],
                },
                {
                    "start_s": 6,
                    "end_s": 9,
                    "action": "Night falls over castle.",
                    "lines": [{"speaker": "Narrator", "text": "Night falls over the realm."}],
                },
            ]
        }
        res = split.parse_split(data, 9, contexts=[], keep="Narrator says: The dawn breaks over the realm.")
        shots = json.loads(res["shots"])["shots"]

        # Shot 0 must preserve Wizard's line
        self.assertEqual(
            len(shots[0]["spoken"]),
            1,
            "Wizard line in Shot 0 must not be purged when user provides a Narrator line",
        )
        self.assertEqual(
            shots[0]["spoken"][0]["text"],
            "Fireball!",
            "Shot 0 must retain Wizard's dialogue 'Fireball!'",
        )
        self.assertEqual(
            shots[0]["spoken"][0]["voice"],
            "Wizard",
            "Shot 0 speaker voice must remain Wizard",
        )

        # Shot 1 must preserve Guard's line
        self.assertEqual(
            len(shots[1]["spoken"]),
            1,
            "Guard line in Shot 1 must not be purged when user provides a Narrator line",
        )
        self.assertEqual(
            shots[1]["spoken"][0]["text"],
            "Halt!",
            "Shot 1 must retain Guard's dialogue 'Halt!'",
        )

        # Shot 2 must have the updated Narrator line
        self.assertEqual(
            len(shots[2]["spoken"]),
            1,
            "Shot 2 must contain the updated Narrator line",
        )
        self.assertEqual(
            shots[2]["spoken"][0]["text"],
            "The dawn breaks over the realm.",
            "Shot 2 must receive the replaced Narrator dialogue",
        )

    def test_defect_uncarded_figure_keep_must_replace_prior_line_not_duplicate_at_end(self):
        """BUG-089: When user keeps dialogue for an uncarded figure (@Wizard says: ...),

        it must replace the AI's proposal in the figure's first shot, instead of failing
        to match, retaining the old line in Shot 0, and duplicating into Shot 1.

        Ist:
        - key(line) returns "" for Wizard's line in Shot 0
        - key(line) == "wizard" is False, so target defaults to shots[-1] (Shot 1)
        - key(line) != "wizard" is True, so Shot 0's "Fireball!" is never removed
        - Shot 0 keeps "Fireball!", Shot 1 gets "Master spell!" appended alongside Guard
        - Wizard speaks twice in conflicting shots

        Soll:
        - Shot 0's "Fireball!" is replaced with "Master spell!"
        - Shot 1 contains only Guard's line "Halt!"
        """
        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 3,
                    "action": "Wizard speaks.",
                    "lines": [{"speaker": "@Wizard", "text": "Fireball!"}],
                },
                {
                    "start_s": 3,
                    "end_s": 6,
                    "action": "Guard speaks.",
                    "lines": [{"speaker": "@Guard", "text": "Halt!"}],
                },
            ]
        }
        res = split.parse_split(data, 6, contexts=[], keep="@Wizard says: Master spell!")
        shots = json.loads(res["shots"])["shots"]

        # Shot 0 must have Wizard's replaced line:
        self.assertEqual(
            len(shots[0]["spoken"]),
            1,
            "Shot 0 must have exactly 1 spoken line (Wizard's replaced line)",
        )
        self.assertEqual(
            shots[0]["spoken"][0]["text"],
            "Master spell!",
            "Shot 0 must replace 'Fireball!' with 'Master spell!'",
        )

        # Shot 1 must contain ONLY Guard's line:
        self.assertEqual(
            len(shots[1]["spoken"]),
            1,
            "Shot 1 must not have Wizard's line appended; it belongs only to Guard",
        )
        self.assertEqual(
            shots[1]["spoken"][0]["text"],
            "Halt!",
            "Shot 1 must contain only Guard's 'Halt!'",
        )

    def test_defect_mixed_carded_and_uncarded_figures_narrator_keep(self):
        """BUG-089: In a mixed project with a carded figure (@Hero), an uncarded figure (@Wizard),

        and a Narrator, 'Narrator says: ...' must not wipe out @Wizard and steal Shot 1.

        Ist:
        - Hero (carded) is preserved in Shot 0
        - Wizard (uncarded, speaker_id="") is wiped from Shot 1
        - Narrator line is put into Shot 1 (Wizard's shot)
        - Shot 2 (original Narrator shot) is left empty

        Soll:
        - Shot 0 has Hero
        - Shot 1 has Wizard
        - Shot 2 has Narrator
        """
        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 3,
                    "action": "Hero speaks.",
                    "lines": [{"speaker": "@Hero", "text": "I am the hero!"}],
                },
                {
                    "start_s": 3,
                    "end_s": 6,
                    "action": "Wizard speaks.",
                    "lines": [{"speaker": "@Wizard", "text": "I am the wizard!"}],
                },
                {
                    "start_s": 6,
                    "end_s": 9,
                    "action": "Narrator speaks.",
                    "lines": [{"speaker": "Narrator", "text": "And so it began."}],
                },
            ]
        }
        res = split.parse_split(
            data,
            9,
            contexts=[self.hero_card],
            keep="Narrator says: Once upon a time in a far land.",
        )
        shots = json.loads(res["shots"])["shots"]

        # Shot 0: Hero
        self.assertEqual(len(shots[0]["spoken"]), 1)
        self.assertEqual(shots[0]["spoken"][0]["text"], "I am the hero!")

        # Shot 1: Wizard (uncarded) must be preserved!
        self.assertEqual(
            len(shots[1]["spoken"]),
            1,
            "Uncarded Wizard in Shot 1 must not be wiped out by Narrator keep",
        )
        self.assertEqual(
            shots[1]["spoken"][0]["text"],
            "I am the wizard!",
            "Shot 1 must retain Wizard's dialogue 'I am the wizard!'",
        )

        # Shot 2: Narrator must be updated!
        self.assertEqual(
            len(shots[2]["spoken"]),
            1,
            "Shot 2 must retain the Narrator line",
        )
        self.assertEqual(
            shots[2]["spoken"][0]["text"],
            "Once upon a time in a far land.",
            "Shot 2 must contain the updated Narrator dialogue",
        )


if __name__ == "__main__":
    unittest.main()
