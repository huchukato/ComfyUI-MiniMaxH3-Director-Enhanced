r"""Regression test for BUG-087: split._owner binds non-image context cards (audio, text, video) to speaker_id, erasing the voice name into 'a narrator', emitting shot_speaker_unbound, and crashing subsequent AI draft parsing.

Where:
- ng/core/split.py:70-79 (`_owner`)
- ng/core/split.py:81-93 (`_lines`)
- ng/core/split.py:96-118 (`_keep`)
- Downstream impact:
  - ng/core/shot_bindings.py:100-106 (`spoken_text` formats `@voice(A narrator)` instead of `@voice(Hero)` and emits `shot_speaker_unbound`)
  - ng/core/shot_draft.py:109-110 (`parse_draft` rejects dialogue with `ValueError: A spoken speaker must be a Subject image or the narrator.`)

Contrast with:
- ng/core/shot_draft.py:109-110:
  `if key == "spoken" and identity in by_id and by_id[identity]["media"] != "image":`
  `    raise ValueError("A spoken speaker must be a Subject image or the narrator.")`
- js/ng/h3s_side.js:44-47 (`speakers(S)` dropdown only lists image cards with usage reference):
  `const subjects = S.contexts.filter((entry) => entry.media === "image" && entry.usage.includes("reference") && entry.id);`
  `return [["", "Narrator (no character)"], ...subjects.map((entry) => [entry.id, entry.name])];`
- ng/core/subjects.py:38-41 (`subject_groups` only aggregates image cards):
  `images = [item for item in context.by_media("image") if "reference" in item.effective_usage and item.source]`
- ng/core/split.py:71 (docstring):
  `"(speaker_id, voice) for a line: a named Content speaks with its own voice, anyone else is a described narrator."`

User workflow:
1. In ComfyUI Director Studio (or via Python API), the user builds a project with context cards.
   Alongside character reference images, the user adds an Audio card (e.g. background music, theme song, or sound effects named "Hero"),
   a Text card (e.g. character lore, backstory, or script notes named "Hero"), or a Video card (e.g. reference footage named "Hero").
2. The user triggers "Auto Direct" or "Prompt Split" to generate a shot sequence, with dialogue spoken by "@Hero"
   (or specifies "@Hero says: ..." in the keep dialogue prompt).
3. The AI returns shot proposals containing dialogue: `{"speaker": "@Hero", "text": "We attack at dawn."}`.
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
   `_owner` does not check `entry.get("media") == "image"`.
2. It matches the non-image card (Audio, Text, or Video) and assigns `speaker_id = widgets["context_id"]` (e.g. "audio_hero").
3. It forces `voice = "a narrator"`, completely discarding the character's name ("Hero").
4. Downstream in `shot_bindings.spoken_text`:
   `subject = subjects.get(spoken.speaker_id)` is `None` because non-image cards are never in `subject_groups`.
   `spoken_text` falls back to `voice`, which is `"a narrator"`, producing:
   `@voice(A narrator) [English] says: We attack at dawn.`
   The prompt sent to the video generator loses the speaker's name entirely, replacing it with an anonymous narrator.
   Moreover, `spoken_text` emits an error issue:
   `Issue("shot_speaker_unbound", "Speaker 'Hero' has no image Subject; narrator voice is used.")`.
5. Downstream in `shot_draft.parse_draft`:
   When the user later asks the AI to improve or adjust shots (`parse_direction`),
   `shot_draft.py:109-110` validates existing and proposed shots:
   `if key == "spoken" and identity in by_id and by_id[identity]["media"] != "image":`
   `    raise ValueError("A spoken speaker must be a Subject image or the narrator.")`
   The draft parse fails with `ValueError: The draft has no usable changes: spoken of ai-1: A spoken speaker must be a Subject image or the narrator.`.
6. In `_keep`:
   When the user writes `@Hero says: ...`, `_owner` binds `speaker_id` to the audio/text card and forces `voice = "a narrator"`.
7. An Audio card named "Narrator" causes `_owner("Narrator", contexts)` to return `(widgets["context_id"], "a narrator")`,
   preventing the narrator from having `speaker_id = ""` as required.

What should happen (Soll):
1. `_owner` must only match context cards whose media is `"image"` (`entry.get("media") == "image"`).
2. If `speaker` does not match an image card, `_owner` must not assign a `speaker_id` (`speaker_id = ""`).
3. The speaker's name must be preserved in `voice` (`voice = "Hero"`).
4. `spoken_text` must format the line as `@voice(Hero) [English] says: We attack at dawn.`, with 0 issues.
5. Subsequent AI drafts must validate successfully without crashing on `media != "image"`.
6. User's `@Hero says:` in `_keep` must produce `speaker_id = ""` and `voice = "Hero"`.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

split = module("ng.core.split")
auto_direct = module("ng.core.auto_direct")
shot_bindings = module("ng.core.shot_bindings")
shot_document = module("ng.core.shot_document")
chunks_mod = module("ng.core.chunks")
context_mod = module("ng.core.context")


class SplitOwnerNonImageSpeakerRegression(unittest.TestCase):
    def setUp(self):
        self.image_hero_card = {
            "media": "image",
            "widgets": {"name": "Hero", "context_id": "image_hero_id", "usage": "reference"},
        }
        self.audio_hero_card = {
            "media": "audio",
            "widgets": {"name": "Hero", "context_id": "audio_hero_id", "usage": "lock"},
        }
        self.text_scholar_card = {
            "media": "text",
            "widgets": {"name": "Scholar", "context_id": "text_scholar_id", "usage": "character"},
        }
        self.video_rider_card = {
            "media": "video",
            "widgets": {"name": "Rider", "context_id": "video_rider_id", "usage": "motion"},
        }

    # --- Green Control Tests (Expected & Existing Working Behavior) ---

    def test_control_image_card_binds_speaker_id_and_compiles_subject_name(self):
        """When an Image context card matches the speaker name, _owner binds its context_id

        and spoken_text compiles the line with @Hero and zero unbound issues."""
        contexts = [self.image_hero_card]
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
        contexts = [self.image_hero_card]
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
        """When speaker is 'Narrator' and no card matches, speaker_id is empty and voice is narrator."""
        contexts = [self.image_hero_card]
        speaker_id, voice = split._owner("Narrator", contexts)
        self.assertEqual(speaker_id, "")
        self.assertEqual(voice, "Narrator")

    # --- Red Defect Tests (Reproducing BUG-087) ---

    def test_defect_audio_context_card_must_not_bind_speaker_id_or_erase_voice(self):
        """BUG-087: When an Audio context card is named 'Hero', _owner must NOT bind

        its context_id to speaker_id or overwrite voice with 'a narrator'.

        Ist:
        - _owner("@Hero", [audio_card]) returns ('audio_hero_id', 'a narrator')
        - parse_split produces speaker_id='audio_hero_id' and voice='a narrator'
        - spoken_text renders '@voice(A narrator)' instead of '@voice(Hero)'
        - spoken_text emits Issue('shot_speaker_unbound', "Speaker 'Hero' has no image Subject; narrator voice is used.")

        Soll:
        - _owner("@Hero", [audio_card]) returns ('', 'Hero')
        - parse_split produces speaker_id='' and voice='Hero'
        - spoken_text renders '@voice(Hero)'
        - spoken_text emits zero issues
        """
        contexts = [self.audio_hero_card]

        # Check _owner directly:
        speaker_id, voice = split._owner("@Hero", contexts)
        self.assertEqual(
            speaker_id,
            "",
            "Audio context card must not be bound to speaker_id; only image Subject cards can speak",
        )
        self.assertEqual(
            voice,
            "Hero",
            "Speaker voice name 'Hero' must not be erased and replaced with 'a narrator'",
        )

        # Check through parse_split pipeline:
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
        self.assertEqual(spoken["speaker_id"], "", "parse_split must not assign audio context_id to speaker_id")
        self.assertEqual(spoken["voice"], "Hero", "parse_split must retain the speaker name in voice")

        # Check through spoken_text compilation:
        ctx_item = context_mod.ContextItem(
            id="audio_hero_id", name="Hero", media="audio", source="hero_theme.mp3", usage=("lock",)
        )
        d_ctx = context_mod.DirectorContext(items=(ctx_item,), project_seconds=5)
        cshot = chunks_mod.ChunkShot(
            shot_index=1,
            local_start_f=0,
            local_end_f=120,
            text="Hero stands.",
            carried=False,
            continues=False,
            shot_id="ai-1",
            spoken=(shot_document.SpokenLine.from_dict(spoken),),
        )
        text, issues = shot_bindings.spoken_text(cshot, d_ctx)
        self.assertIn("@voice(Hero)", text, "Spoken text must address @voice(Hero), not @voice(A narrator)")
        self.assertEqual(issues, (), "Must not emit shot_speaker_unbound issue when speaker is a described voice")

    def test_defect_text_and_video_cards_must_not_bind_speaker_id(self):
        """BUG-087: Text cards (notes/lore) and Video cards (reference footage)

        sharing names with speakers must not hijack speaker_id or erase voice names.

        Ist:
        - Scholar binds to text_scholar_id with voice 'a narrator'
        - Rider binds to video_rider_id with voice 'a narrator'

        Soll:
        - Both have speaker_id='' and retain their proper voice names ('Scholar', 'Rider')
        """
        contexts = [self.text_scholar_card, self.video_rider_card]

        spk_scholar, voice_scholar = split._owner("@Scholar", contexts)
        self.assertEqual(spk_scholar, "", "Text context card must not be bound to speaker_id")
        self.assertEqual(voice_scholar, "Scholar", "Voice name 'Scholar' must be preserved")

        spk_rider, voice_rider = split._owner("@Rider", contexts)
        self.assertEqual(spk_rider, "", "Video context card must not be bound to speaker_id")
        self.assertEqual(voice_rider, "Rider", "Voice name 'Rider' must be preserved")

        data = {
            "shots": [
                {
                    "start_s": 0,
                    "end_s": 5,
                    "action": "Scholar reads, Rider waits.",
                    "lines": [
                        {"speaker": "@Scholar", "text": "The tome speaks of danger."},
                        {"speaker": "@Rider", "text": "Then we ride immediately."},
                    ],
                }
            ]
        }
        res = split.parse_split(data, 5, contexts)
        shots_data = json.loads(res["shots"])["shots"]
        lines = shots_data[0]["spoken"]

        self.assertEqual(lines[0]["speaker_id"], "")
        self.assertEqual(lines[0]["voice"], "Scholar")
        self.assertEqual(lines[1]["speaker_id"], "")
        self.assertEqual(lines[1]["voice"], "Rider")

    def test_defect_keep_dialogue_with_audio_card_must_not_bind_speaker_id(self):
        """BUG-087: When user provides dialogue in keep (@Hero says: ...),

        an Audio card named 'Hero' must not corrupt speaker_id or set voice to 'a narrator'.

        Ist:
        - _keep binds speaker_id to 'audio_hero_id' and voice to 'a narrator'
        - prompt compiles as '@voice(A narrator) [English] says: Stand your ground!'

        Soll:
        - speaker_id is '', voice is 'Hero'
        - prompt compiles as '@voice(Hero) [English] says: Stand your ground!'
        """
        contexts = [self.audio_hero_card]
        data = {"shots": [{"start_s": 0, "end_s": 5, "action": "Hero stands.", "lines": []}]}
        res = split.parse_split(data, 5, contexts, keep="@Hero says: Stand your ground!")
        shots_data = json.loads(res["shots"])["shots"]
        spoken = shots_data[0]["spoken"][0]

        self.assertEqual(
            spoken["speaker_id"],
            "",
            "_keep must not assign non-image context_id to speaker_id",
        )
        self.assertEqual(
            spoken["voice"],
            "Hero",
            "_keep must preserve the speaker name 'Hero' in voice",
        )

    def test_defect_subsequent_shot_draft_crashes_on_non_image_speaker_id(self):
        """BUG-087: When shots generated by split.parse_split have speaker_id set to a non-image card,

        any subsequent AI draft modification to dialogue fails because shot_draft.py:109-110
        demands that all spoken speaker_ids be Subject images.

        Ist:
        - parse_split writes speaker_id='audio_hero_id'
        - auto_direct.parse_direction invokes parse_draft
        - parse_draft encounters speaker_id='audio_hero_id' with media='audio' != 'image'
        - parse_draft raises ValueError: 'The draft has no usable changes: spoken of ai-1: A spoken speaker must be a Subject image or the narrator.'

        Soll:
        - parse_split produces speaker_id=''
        - subsequent draft parse succeeds and accepts the dialogue update
        """
        contexts = [self.audio_hero_card]
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

        # AI proposes updating the dialogue line text or appending a new line:
        draft = json.dumps(
            {
                "format": "h3-director-draft",
                "schema_version": 1,
                "patches": [
                    {
                        "shot_id": "ai-1",
                        "fields": {
                            "spoken": [
                                {
                                    "schema_version": 1,
                                    "text": "We attack at dawn.",
                                    "speaker_id": "",
                                    "voice": "Hero",
                                    "language": "English",
                                    "delivery": "says",
                                },
                                {
                                    "schema_version": 1,
                                    "text": "Charge!",
                                    "speaker_id": "",
                                    "voice": "Hero",
                                    "language": "English",
                                    "delivery": "says",
                                },
                            ]
                        },
                    }
                ],
            }
        )

        # This call crashes on unmodified code because current_shots has speaker_id='audio_hero_id',
        # and draft proposed line has speaker_id='' or vice versa.
        # Even if the AI repeated the existing speaker_id ('audio_hero_id'):
        draft_with_audio_id = json.dumps(
            {
                "format": "h3-director-draft",
                "schema_version": 1,
                "patches": [
                    {
                        "shot_id": "ai-1",
                        "fields": {
                            "spoken": [
                                {
                                    "schema_version": 1,
                                    "text": "We attack at dawn.",
                                    "speaker_id": "audio_hero_id",
                                    "voice": "a narrator",
                                    "language": "English",
                                    "delivery": "says",
                                },
                                {
                                    "schema_version": 1,
                                    "text": "Charge!",
                                    "speaker_id": "",
                                    "voice": "Hero",
                                    "language": "English",
                                    "delivery": "says",
                                },
                            ]
                        },
                    }
                ],
            }
        )

        # On buggy code, auto_direct.parse_direction with draft_with_audio_id raises ValueError:
        # "The draft has no usable changes: spoken of ai-1: A spoken speaker must be a Subject image or the narrator."
        # Because parse_split generated speaker_id='audio_hero_id', the project is stuck in an un-draftable state.
        try:
            draft_result = auto_direct.parse_direction(
                text=draft_with_audio_id,
                seconds=5,
                contexts=contexts,
                current_shots=res["shots"],
            )
        except ValueError as err:
            self.fail("Subsequent shot draft failed with ValueError because parse_split bound a non-image card: %s" % err)
        self.assertTrue(
            draft_result.get("patches"),
            "Draft parse must succeed and produce patches instead of dropping spoken changes due to non-image speaker_id",
        )


if __name__ == "__main__":
    unittest.main()
