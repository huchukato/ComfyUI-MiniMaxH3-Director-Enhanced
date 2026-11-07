r"""Regression test for BUG-088: split._owner binds non-reference frame image cards (first_frame, last_frame, keyframe, storyboard) to speaker_id, erasing the voice name into 'a narrator', emitting shot_speaker_unbound and desynchronizing Studio UI.

Where:
- ng/core/split.py:70-79 (`_owner`)
- ng/core/split.py:81-93 (`_lines`)
- ng/core/split.py:96-118 (`_keep`)
- Downstream impact:
  - ng/core/shot_bindings.py:100-106 (`spoken_text` formats `@voice(A narrator)` instead of `@voice(Alice)` and emits `shot_speaker_unbound`)
  - js/ng/h3s_side.js:44-47 (`speakers(S)` dropdown only lists `entry.usage.includes("reference")`, so non-reference frame cards do not exist in the dropdown, desynchronizing UI)

Contrast with:
- ng/core/builder.py:291-297 (`_bind` in builder explicitly recognizes and corrects this for `parse_plan`):
  `# A figure seen only as a first/last frame is no reference Subject; its lines are spoken by a voice with its name.`
  `frames = {ids.get(name): name for name, (sort, _) in kinds(contexts).items() if sort == "frame" and ids.get(name)}`
  `for shot, names in zip(data["shots"], uses):`
  `    ...`
  `    for line in shot["spoken"]:`
  `        if line["speaker_id"] in frames:`
  `            line.update(speaker_id="", voice=frames[line["speaker_id"]])`
- ng/core/subjects.py:38-41 (`subject_groups` only aggregates reference image cards):
  `images = [item for item in context.by_media("image") if "reference" in item.effective_usage and item.source]`
- js/ng/h3s_side.js:44-47 (`speakers(S)` dropdown only lists image cards with usage reference):
  `const subjects = S.contexts.filter((entry) => entry.media === "image" && entry.usage.includes("reference") && entry.id);`
  `return [["", "Narrator (no character)"], ...subjects.map((entry) => [entry.id, entry.name])];`
- ng/core/split.py:71 (docstring):
  `"(speaker_id, voice) for a line: a named Content speaks with its own voice, anyone else is a described narrator."`

User workflow:
1. In ComfyUI Director Studio (or via Python API), the user builds a project with context cards.
   The user specifies an initial character look or closing pose as an image card with usage role
   `first_frame`, `last_frame`, `keyframe`, or `storyboard` (e.g. "First frame: Alice", "Last frame: Bob").
2. The user triggers "Auto Direct" or "Prompt Split" to generate a shot sequence, with dialogue spoken by "@Alice"
   (or specifies "@Alice says: ..." in the keep dialogue prompt).
3. The AI returns shot proposals containing dialogue: `{"speaker": "@Alice", "text": "Welcome to wonderland."}`.
4. `split.parse_split` parses the AI response via `_lines` and `_owner`.

What happens (Ist):
1. In `ng/core/split.py:70-76`:
   ```python
   def _owner(speaker, contexts):
       name = speaker.strip().lstrip("@").casefold()
       for entry in contexts or ():
           widgets = entry.get("widgets", {})
           if name and widget_text(widgets, "name").casefold() == name and widgets.get("context_id"):
               return widgets["context_id"], "a narrator"
   ```
   `_owner` checks only that the card's name matches and that `context_id` is present.
   It does NOT check whether the card has usage `"reference"`.
2. It matches the non-reference frame image card (`first_frame`, `last_frame`, `keyframe`, `storyboard`)
   and assigns `speaker_id = widgets["context_id"]` (e.g. "img_alice_first_frame").
3. It forces `voice = "a narrator"`, completely discarding the character's name ("Alice").
4. Downstream in `shot_bindings.spoken_text`:
   `subject = subjects.get(spoken.speaker_id)` is `None` because non-reference frame cards are never in `subject_groups`.
   `spoken_text` falls back to `voice`, which is `"a narrator"`, producing:
   `@voice(A narrator) [English] says: Welcome to wonderland.`
   The prompt sent to the video generator loses the speaker's name entirely, replacing it with an anonymous narrator.
   Moreover, `spoken_text` emits an error issue:
   `Issue("shot_speaker_unbound", "Speaker 'Alice' has no image Subject; narrator voice is used.")`.
5. In the Studio UI (`js/ng/h3s_side.js:44-47`), `speakers(S)` filters for `entry.usage.includes("reference")`.
   Non-reference frame cards are absent from the dropdown, causing UI desynchronization where the bound speaker
   cannot be displayed or selected in the editor.
6. In `_keep`:
   When the user writes `@Alice says: Hold the gate!`, `_owner` binds `img_alice_first_frame` and degrades voice to `"a narrator"`.

What should happen (Soll):
1. `_owner` must only bind image cards that have `"reference"` in their usage roles (multi-view reference Subjects).
2. If an image card is a non-reference frame anchor (`first_frame`, `last_frame`, `keyframe`, `storyboard`),
   `_owner` must return `("", "Alice")` — matching the developer intent documented in `builder.py:291-297`.
3. `parse_split` produces `speaker_id=""` and `voice="Alice"`.
4. `spoken_text` must format the line as `@voice(Alice) [English] says: Welcome to wonderland.`, with 0 issues.
5. User's `@Alice says:` in `_keep` must produce `speaker_id = ""` and `voice = "Alice"`.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

split = module("ng.core.split")
shot_bindings = module("ng.core.shot_bindings")
shot_document = module("ng.core.shot_document")
chunks_mod = module("ng.core.chunks")
context_mod = module("ng.core.context")


class SplitOwnerNonReferenceFrameSpeakerRegression(unittest.TestCase):
    def setUp(self):
        self.ref_hero_card = {
            "media": "image",
            "widgets": {"name": "Hero", "context_id": "image_hero_id", "usage": "reference", "image": "hero.png"},
        }
        self.first_frame_alice_card = {
            "media": "image",
            "widgets": {"name": "Alice", "context_id": "image_alice_ff_id", "usage": "first_frame", "image": "alice.png"},
        }
        self.last_frame_bob_card = {
            "media": "image",
            "widgets": {"name": "Bob", "context_id": "image_bob_lf_id", "usage": "last_frame", "image": "bob.png"},
        }
        self.keyframe_charlie_card = {
            "media": "image",
            "widgets": {"name": "Charlie", "context_id": "image_charlie_kf_id", "usage": "keyframe", "image": "charlie.png"},
        }
        self.storyboard_diana_card = {
            "media": "image",
            "widgets": {"name": "Diana", "context_id": "image_diana_sb_id", "usage": "storyboard", "image": "diana.png"},
        }

    # --- Green Control Tests (Expected & Existing Working Behavior) ---

    def test_control_reference_image_card_binds_speaker_id_and_compiles_subject_name(self):
        """When an Image context card has usage 'reference', _owner binds its context_id

        and spoken_text compiles the line with @Hero and zero unbound issues."""
        contexts = [self.ref_hero_card]
        speaker_id, voice = split._owner("@Hero", contexts)
        self.assertEqual(speaker_id, "image_hero_id")

        ctx_item = context_mod.ContextItem(
            id="image_hero_id", name="Hero", media="image", source="hero.png", usage=("reference",)
        )
        d_ctx = context_mod.DirectorContext(items=(ctx_item,), project_seconds=5)

        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 5,
                    "action": "Hero stands.",
                    "lines": [{"speaker": "@Hero", "text": "We attack at dawn."}],
                }
            ]
        }
        res = split.parse_split(data, 5, contexts)
        shots_data = json.loads(res["shots"])["shots"]
        spoken = shots_data[0]["spoken"][0]
        self.assertEqual(spoken["speaker_id"], "image_hero_id")

        spoken_lines = (shot_document.SpokenLine.from_dict(spoken),)
        cshot = chunks_mod.ChunkShot(
            shot_index=1,
            local_start_f=0,
            local_end_f=120,
            text="Hero stands.",
            carried=False,
            continues=False,
            shot_id="ai-1",
            spoken=spoken_lines,
        )
        text, issues = shot_bindings.spoken_text(cshot, d_ctx)
        self.assertIn("@Hero [English] says: We attack at dawn.", text)
        self.assertEqual(issues, ())

    def test_control_unbound_speaker_uses_voice_description_and_retains_name(self):
        """When a speaker name does not match any card, _owner returns speaker_id=''

        and voice='Wizard', compiling as @voice(Wizard) with zero issues."""
        contexts = [self.ref_hero_card]
        speaker_id, voice = split._owner("@Wizard", contexts)
        self.assertEqual(speaker_id, "")
        self.assertEqual(voice, "Wizard")

        d_ctx = context_mod.DirectorContext(items=(), project_seconds=5)
        spoken_line = shot_document.SpokenLine(
            text="Magic flows.", speaker_id="", voice="Wizard", language="English", delivery="says"
        )
        cshot = chunks_mod.ChunkShot(
            shot_index=1,
            local_start_f=0,
            local_end_f=120,
            text="Wizard casts.",
            carried=False,
            continues=False,
            shot_id="ai-1",
            spoken=(spoken_line,),
        )
        text, issues = shot_bindings.spoken_text(cshot, d_ctx)
        self.assertIn("@voice(Wizard) [English] says: Magic flows.", text)
        self.assertEqual(issues, ())

    def test_control_explicit_narrator_without_card_produces_empty_speaker_id(self):
        """When speaker is 'Narrator' and no card matches, speaker_id is empty and voice is Narrator."""
        contexts = [self.ref_hero_card]
        speaker_id, voice = split._owner("Narrator", contexts)
        self.assertEqual(speaker_id, "")
        self.assertEqual(voice, "Narrator")

    # --- Red Defect Tests (Reproducing BUG-088) ---

    def test_defect_first_frame_image_card_must_not_bind_speaker_id_or_erase_voice(self):
        """BUG-088: When an Image context card has usage 'first_frame', _owner must NOT bind

        its context_id to speaker_id or overwrite voice with 'a narrator'.

        Ist:
        - _owner("@Alice", [first_frame_card]) returns ('image_alice_ff_id', 'a narrator')
        - parse_split produces speaker_id='image_alice_ff_id' and voice='a narrator'
        - spoken_text renders '@voice(A narrator)' instead of '@voice(Alice)'
        - spoken_text emits Issue('shot_speaker_unbound', "Speaker 'Alice' has no image Subject; narrator voice is used.")

        Soll:
        - _owner("@Alice", [first_frame_card]) returns ('', 'Alice')
        - parse_split produces speaker_id='' and voice='Alice'
        - spoken_text renders '@voice(Alice)'
        - spoken_text emits zero issues
        """
        contexts = [self.first_frame_alice_card]

        # Check _owner directly:
        speaker_id, voice = split._owner("@Alice", contexts)
        self.assertEqual(
            speaker_id,
            "",
            "First frame image card must not be bound to speaker_id; only reference Subject cards can speak",
        )
        self.assertEqual(
            voice,
            "Alice",
            "Speaker voice name 'Alice' must not be erased and replaced with 'a narrator'",
        )

        # Check through parse_split pipeline:
        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 5,
                    "action": "Alice speaks.",
                    "lines": [{"speaker": "@Alice", "text": "Welcome to wonderland."}],
                }
            ]
        }
        res = split.parse_split(data, 5, contexts)
        shots_data = json.loads(res["shots"])["shots"]
        spoken = shots_data[0]["spoken"][0]
        self.assertEqual(spoken["speaker_id"], "", "parse_split must not assign first_frame context_id to speaker_id")
        self.assertEqual(spoken["voice"], "Alice", "parse_split must retain the speaker name in voice")

        # Check through spoken_text compilation:
        ctx_item = context_mod.ContextItem(
            id="image_alice_ff_id", name="Alice", media="image", source="alice.png", usage=("first_frame",)
        )
        d_ctx = context_mod.DirectorContext(items=(ctx_item,), project_seconds=5)
        cshot = chunks_mod.ChunkShot(
            shot_index=1,
            local_start_f=0,
            local_end_f=120,
            text="Alice speaks.",
            carried=False,
            continues=False,
            shot_id="ai-1",
            spoken=(shot_document.SpokenLine.from_dict(spoken),),
        )
        text, issues = shot_bindings.spoken_text(cshot, d_ctx)
        self.assertIn("@voice(Alice)", text, "Spoken text must address @voice(Alice), not @voice(A narrator)")
        self.assertEqual(issues, (), "Must not emit shot_speaker_unbound issue when speaker is a described voice")

    def test_defect_last_frame_image_card_must_not_bind_speaker_id_or_erase_voice(self):
        """BUG-088: When an Image context card has usage 'last_frame', _owner must NOT bind

        its context_id to speaker_id or overwrite voice with 'a narrator'.

        Ist:
        - _owner("@Bob", [last_frame_card]) returns ('image_bob_lf_id', 'a narrator')
        - parse_split produces speaker_id='image_bob_lf_id' and voice='a narrator'
        - spoken_text renders '@voice(A narrator)' instead of '@voice(Bob)'
        - spoken_text emits Issue('shot_speaker_unbound', "Speaker 'Bob' has no image Subject; narrator voice is used.")

        Soll:
        - _owner("@Bob", [last_frame_card]) returns ('', 'Bob')
        - parse_split produces speaker_id='' and voice='Bob'
        - spoken_text renders '@voice(Bob)'
        - spoken_text emits zero issues
        """
        contexts = [self.last_frame_bob_card]

        speaker_id, voice = split._owner("@Bob", contexts)
        self.assertEqual(
            speaker_id,
            "",
            "Last frame image card must not be bound to speaker_id",
        )
        self.assertEqual(
            voice,
            "Bob",
            "Speaker voice name 'Bob' must not be erased and replaced with 'a narrator'",
        )

        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 5,
                    "action": "Bob waves farewell.",
                    "lines": [{"speaker": "@Bob", "text": "Goodbye for now."}],
                }
            ]
        }
        res = split.parse_split(data, 5, contexts)
        shots_data = json.loads(res["shots"])["shots"]
        spoken = shots_data[0]["spoken"][0]
        self.assertEqual(spoken["speaker_id"], "", "parse_split must not assign last_frame context_id to speaker_id")
        self.assertEqual(spoken["voice"], "Bob", "parse_split must retain the speaker name in voice")

        ctx_item = context_mod.ContextItem(
            id="image_bob_lf_id", name="Bob", media="image", source="bob.png", usage=("last_frame",)
        )
        d_ctx = context_mod.DirectorContext(items=(ctx_item,), project_seconds=5)
        cshot = chunks_mod.ChunkShot(
            shot_index=1,
            local_start_f=0,
            local_end_f=120,
            text="Bob waves farewell.",
            carried=False,
            continues=False,
            shot_id="ai-1",
            spoken=(shot_document.SpokenLine.from_dict(spoken),),
        )
        text, issues = shot_bindings.spoken_text(cshot, d_ctx)
        self.assertIn("@voice(Bob)", text, "Spoken text must address @voice(Bob), not @voice(A narrator)")
        self.assertEqual(issues, (), "Must not emit shot_speaker_unbound issue when speaker is a described voice")

    def test_defect_keyframe_and_storyboard_image_cards_must_not_bind_speaker_id(self):
        """BUG-088: Intermediate anchor cards (keyframe, storyboard) must not hijack speaker_id.

        Ist:
        - Charlie binds to image_charlie_kf_id with voice 'a narrator'
        - Diana binds to image_diana_sb_id with voice 'a narrator'

        Soll:
        - Both have speaker_id='' and retain their proper voice names ('Charlie', 'Diana')
        """
        contexts = [self.keyframe_charlie_card, self.storyboard_diana_card]

        spk_charlie, voice_charlie = split._owner("@Charlie", contexts)
        self.assertEqual(spk_charlie, "", "Keyframe image card must not be bound to speaker_id")
        self.assertEqual(voice_charlie, "Charlie", "Voice name 'Charlie' must be preserved")

        spk_diana, voice_diana = split._owner("@Diana", contexts)
        self.assertEqual(spk_diana, "", "Storyboard image card must not be bound to speaker_id")
        self.assertEqual(voice_diana, "Diana", "Voice name 'Diana' must be preserved")

        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 5,
                    "action": "Charlie speaks, Diana answers.",
                    "lines": [
                        {"speaker": "@Charlie", "text": "Look at the stars."},
                        {"speaker": "@Diana", "text": "They shine brightly."},
                    ],
                }
            ]
        }
        res = split.parse_split(data, 5, contexts)
        shots_data = json.loads(res["shots"])["shots"]
        lines = shots_data[0]["spoken"]

        self.assertEqual(lines[0]["speaker_id"], "")
        self.assertEqual(lines[0]["voice"], "Charlie")
        self.assertEqual(lines[1]["speaker_id"], "")
        self.assertEqual(lines[1]["voice"], "Diana")

    def test_defect_keep_dialogue_with_first_frame_card_must_not_bind_speaker_id(self):
        """BUG-088: When user provides dialogue in keep (@Alice says: ...),

        a first_frame card named 'Alice' must not corrupt speaker_id or set voice to 'a narrator'.

        Ist:
        - _keep binds speaker_id to 'image_alice_ff_id' and voice to 'a narrator'
        - prompt compiles as '@voice(A narrator) [English] says: Hold the gate!'

        Soll:
        - speaker_id is '', voice is 'Alice'
        - prompt compiles as '@voice(Alice) [English] says: Hold the gate!'
        """
        contexts = [self.first_frame_alice_card]
        data = {"shots": [{"start_s": 0, "end_s": 5, "action": "Alice stands.", "lines": []}]}
        res = split.parse_split(data, 5, contexts, keep="@Alice says: Hold the gate!")
        shots_data = json.loads(res["shots"])["shots"]
        spoken = shots_data[0]["spoken"][0]

        self.assertEqual(
            spoken["speaker_id"],
            "",
            "_keep must not assign non-reference frame context_id to speaker_id",
        )
        self.assertEqual(
            spoken["voice"],
            "Alice",
            "_keep must preserve the speaker name 'Alice' in voice",
        )

        ctx_item = context_mod.ContextItem(
            id="image_alice_ff_id", name="Alice", media="image", source="alice.png", usage=("first_frame",)
        )
        d_ctx = context_mod.DirectorContext(items=(ctx_item,), project_seconds=5)
        cshot = chunks_mod.ChunkShot(
            shot_index=1,
            local_start_f=0,
            local_end_f=120,
            text="Alice stands.",
            carried=False,
            continues=False,
            shot_id="ai-1",
            spoken=(shot_document.SpokenLine.from_dict(spoken),),
        )
        text, issues = shot_bindings.spoken_text(cshot, d_ctx)
        self.assertIn("@voice(Alice)", text, "Spoken text must address @voice(Alice), not @voice(A narrator)")
        self.assertEqual(issues, (), "Must not emit shot_speaker_unbound issue")


if __name__ == "__main__":
    unittest.main()
