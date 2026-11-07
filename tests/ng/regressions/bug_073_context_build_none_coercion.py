"""BUG-073: item_from_widgets coerces None widget values into string "None",
causing spurious speaker_unknown issues and prompt corruption.

Where:
- ng/core/context_build.py:21, 28, 31, 32 (item_from_widgets)
- ng/core/project.py:35-39 (resolve_speakers)
- ng/core/preview.py:21, 52 (plan_preview)

User workflow:
1. In ComfyUI Director Studio, the user adds an Audio Context card (e.g. voice.wav)
   or an Image Context card (e.g. alice.png).
2. The user leaves the optional 'speaker' or 'description' or 'name' fields blank.
   In JSON payloads from the frontend (POST /ng/plan, POST /ng/presets) or optional
   inputs in ComfyUI execution, empty/unconnected widgets arrive as `None` (null):
   `widgets = {"audio": "voice.wav", "speaker": None, "name": None, "description": None}`.
3. Director Studio requests a plan preview via /ng/plan (or executes NGH3Director).

What happens (Ist):
In ng/core/context_build.py:
    line 21: name = str(widgets.get("name", "")).strip()
    line 31: description=str(widgets.get("description", "")).strip()
    line 32: speaker=str(widgets.get("speaker", "")).strip(), color=str(widgets.get("color", ""))
1. `dict.get(key, default)` returns the value associated with `key` when the key exists.
   Because "speaker", "description", "name", "color" exist in `widgets` with value `None`,
   `widgets.get(key, "")` returns `None`.
2. `str(None)` evaluates to the literal 4-character string `"None"`.
3. `item.speaker` becomes `"None"`.
   In `project.py:35-39` (`resolve_speakers`), `speaker` is evaluated as truthy. It searches
   for a context item with the name "None". Since no such item exists, it emits a spurious error:
   `Issue("speaker_unknown", "names 'None' as the speaker, but no context item has that name.")`.
   The user sees a red validation error in the Studio panel for an audio card that has no speaker configured.
4. `item.description` becomes `"None"`.
   In `ng/core/asset_prompt.py` and the compiler, `"None"` is treated as the user's description.
   The compiled prompt generates:
   `<Subject 1> is None, shown in <Picture 1>.`
   instead of the intended fallback:
   `<Subject 1> is the person shown in <Picture 1>.`.
5. `item.name` becomes `"None"`.
   The item receives label `"None"` and ID `"audio_none"` / `"image_none"`, instead of deriving
   its name from the file stem (e.g. "voice" for "voice.wav").

What should happen (Soll):
When a widget value is `None` (null), it should be treated as empty string `""` / absent:
- `item.speaker` must be `""`, and no `speaker_unknown` issue should be emitted.
- `item.description` must be `""`, and prompt compilation must use the standard fallback
  (`<Subject 1> is the person shown in <Picture 1>.`).
- `item.name` must fall back to the filename stem (e.g. "voice" / "alice"), not `"None"`.
- `item.color` must be `""`, not `"None"`.
"""
import os
import pathlib
import sys
import unittest

TESTS_NG = pathlib.Path(__file__).resolve().parent.parent
REPO = TESTS_NG.parent.parent
sys.path.insert(0, str(TESTS_NG))
sys.path.insert(0, str(REPO.parent.parent))

from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()
build = module("ng.core.context_build")
project = module("ng.core.project")
preview = module("ng.core.preview")


class Bug073ContextBuildNoneCoercion(unittest.TestCase):
    def test_bug_073_item_from_widgets_none_coercion_must_not_produce_none_strings(self):
        """None widget values must normalize to empty strings or fallbacks, never the string 'None'."""
        widgets = {
            "audio": "voice.wav",
            "speaker": None,
            "description": None,
            "name": None,
            "color": None,
        }
        item = build.item_from_widgets("audio", widgets)

        self.assertNotEqual(item.speaker, "None",
                            "item.speaker must not be coerced to the literal string 'None'")
        self.assertEqual(item.speaker, "",
                         "item.speaker with None widget value must normalize to empty string")

        self.assertNotEqual(item.description, "None",
                            "item.description must not be coerced to the literal string 'None'")
        self.assertEqual(item.description, "",
                         "item.description with None widget value must normalize to empty string")

        self.assertNotEqual(item.name, "None",
                            "item.name must not be coerced to the literal string 'None'")
        self.assertEqual(item.name, "voice",
                         "item.name must fall back to filename stem 'voice' when name is None")

        self.assertNotEqual(item.id, "audio_none",
                            "item.id must not be 'audio_none'")
        self.assertEqual(item.id, "audio_voice",
                         "item.id must be derived from filename stem")

        self.assertNotEqual(item.color, "None",
                            "item.color must not be the literal string 'None'")
        self.assertEqual(item.color, "")

    def test_bug_073_plan_preview_with_none_speaker_must_not_emit_spurious_speaker_unknown_issue(self):
        """An audio card with speaker: None must not trigger 'speaker_unknown: names None'."""
        payload = {
            "director": {
                "idea": "A quiet monologue.",
                "shots": "[Shot 1] 0-5s Narration.",
                "project_seconds": 5.0,
            },
            "contexts": [
                {
                    "media": "audio",
                    "widgets": {
                        "audio": "voice.wav",
                        "name": "Narration",
                        "speaker": None,
                    },
                }
            ],
        }
        res = preview.plan_preview(payload)
        self.assertTrue(res.get("ok"), "plan_preview must succeed: %s" % res.get("error"))

        speaker_issues = [
            issue for issue in res.get("issues", [])
            if issue.get("code") == "speaker_unknown"
        ]
        self.assertEqual(speaker_issues, [],
                         "Must not emit spurious speaker_unknown issue for speaker=None: %s" % speaker_issues)

    def test_bug_073_plan_preview_with_none_description_must_not_corrupt_prompt(self):
        """An image card with description: None must not generate '<Subject 1> is None, shown in Picture'."""
        payload = {
            "director": {
                "idea": "Alice stands in a garden.",
                "shots": "[Shot 1] 0-5s A portrait.",
                "project_seconds": 5.0,
            },
            "contexts": [
                {
                    "media": "image",
                    "widgets": {
                        "image": "alice.png",
                        "name": "Alice",
                        "description": None,
                    },
                }
            ],
        }
        res = preview.plan_preview(payload)
        self.assertTrue(res.get("ok"), "plan_preview must succeed: %s" % res.get("error"))

        chunks = res.get("chunks", [])
        self.assertGreater(len(chunks), 0, "Must produce at least one chunk")
        prompt = chunks[0].get("prompt", "")

        self.assertNotIn("<Subject 1> is None, shown in", prompt,
                         "Prompt must not contain '<Subject 1> is None, shown in': %s" % prompt)
        self.assertIn("<Subject 1> is the person shown in <Picture 1>.", prompt,
                      "Prompt must use the standard fallback for unspecified description: %s" % prompt)

    def test_control_normal_empty_strings_produce_expected_clean_state(self):
        """Green control: When widgets contain empty strings '', behavior is clean."""
        widgets = {
            "audio": "voice.wav",
            "speaker": "",
            "description": "",
            "name": "",
            "color": "",
        }
        item = build.item_from_widgets("audio", widgets)
        self.assertEqual(item.speaker, "")
        self.assertEqual(item.description, "")
        self.assertEqual(item.name, "voice")
        self.assertEqual(item.id, "audio_voice")
        self.assertEqual(item.color, "")

        payload = {
            "director": {
                "idea": "Alice stands in a garden.",
                "shots": "[Shot 1] 0-5s A portrait.",
                "project_seconds": 5.0,
            },
            "contexts": [
                {
                    "media": "image",
                    "widgets": {
                        "image": "alice.png",
                        "name": "Alice",
                        "description": "",
                    },
                },
                {
                    "media": "audio",
                    "widgets": {
                        "audio": "voice.wav",
                        "name": "Narration",
                        "speaker": "",
                    },
                },
            ],
        }
        res = preview.plan_preview(payload)
        self.assertTrue(res.get("ok"))
        speaker_issues = [i for i in res.get("issues", []) if i.get("code") == "speaker_unknown"]
        self.assertEqual(speaker_issues, [])
        prompt = res["chunks"][0]["prompt"]
        self.assertIn("<Subject 1> is the person shown in <Picture 1>.", prompt)

    def test_control_explicit_values_are_preserved(self):
        """Green control: When widgets contain explicit valid values, they are preserved."""
        widgets = {
            "audio": "voice.wav",
            "speaker": "Alice",
            "description": "Voice of Alice",
            "name": "HeroVoice",
            "color": "#ff0000",
        }
        item = build.item_from_widgets("audio", widgets)
        self.assertEqual(item.speaker, "Alice")
        self.assertEqual(item.description, "Voice of Alice")
        self.assertEqual(item.name, "HeroVoice")
        self.assertEqual(item.id, "audio_herovoice")
        self.assertEqual(item.color, "#ff0000")


if __name__ == "__main__":
    unittest.main()
