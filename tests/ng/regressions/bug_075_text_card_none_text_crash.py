"""BUG-075: Text context card with text=None crashes AI planning (story in auto_direct.py:43)
with AttributeError ('NoneType' object has no attribute 'strip') and card analysis
(analysis.py:120) with TypeError ('can only concatenate str (not 'NoneType') to str').

Where:
- ng/core/auto_direct.py:43 (story)
- ng/core/auto_direct.py:59 (direction_prompt)
- ng/core/builder.py:231 (plan_prompt)
- ng/adapters/auto_direct.py:19 (direct)
- ng/adapters/builder.py:44 (plan)
- ng/adapters/analysis.py:120 (analyze)
- ng/nodes/analysis_routes.py:39, 49, 58, 68, 78 (direct_scenes, build_plan, analyze_context)

User workflow:
1. In ComfyUI Director Studio, the user adds a Text Context Card (NGContextText).
2. The user sets its usage role to 'scene' (e.g. to direct a specific scene) or leaves it
   as a general note, but has not yet entered any text, or clears the text box.
   In JSON payloads from the frontend (POST /ng/direct, POST /ng/build_plan, POST /ng/analyze)
   or LiteGraph widget serialization, unconfigured or cleared multiline text widgets have
   null values: `{"media": "text", "widgets": {"usage": "scene", "text": None, "name": "Scene 1", "context_id": "txt_1"}}`.
3. The user clicks "AI: Split into shots" (/ng/direct) or "Make H3 prompt" (/ng/build_plan).
   Alternatively, the user clicks "Analyze" on the Text card (/ng/analyze).

What happens (Ist):
1. In ng/core/auto_direct.py:43:
       notes = [entry["widgets"].get("text", "").strip() for entry in contexts
                if entry.get("media") == "text" and "scene" in _roles(entry["widgets"])]
   Because "text" key is present in widgets with value None, `widgets.get("text", "")` returns None!
   Calling `.strip()` on None raises `AttributeError: 'NoneType' object has no attribute 'strip'`.
2. In ng/core/builder.py:231:
       request = story(idea, contexts)
   Calls the same function, raising `AttributeError`.
3. In ng/nodes/analysis_routes.py:58, 78:
       except (ValueError, KeyError, TypeError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as error:
   `AttributeError` is NOT in the caught exception tuple!
   The route fails with an unhandled 500 Internal Server Error, dumping a crash traceback to console.
4. In ng/adapters/analysis.py:120:
       if media == "text":
           prompt += "\\n\\nContext text:\\n" + widgets.get("text", "")
   `widgets.get("text", "")` returns None, raising:
   `TypeError: can only concatenate str (not "NoneType") to str`.

What should happen (Soll):
When a Text context card has `text: None` (or null in JSON):
- `(entry["widgets"].get("text") or "").strip()` should be used in `story` to treat None as empty string.
- `widgets.get("text") or ""` should be used in `analysis.py:120` to avoid TypeError.
- Unfilled Text cards should not crash scene planning or card analysis.
"""
import asyncio
import pathlib
import sys
import unittest

TESTS_NG = pathlib.Path(__file__).resolve().parent.parent
REPO = TESTS_NG.parent.parent
sys.path.insert(0, str(TESTS_NG))
sys.path.insert(0, str(REPO.parent.parent))

from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()
auto_direct = module("ng.core.auto_direct")
builder = module("ng.core.builder")
analysis = module("ng.adapters.analysis")


class Bug075TextCardNoneTextCrash(unittest.TestCase):
    def setUp(self):
        # Text context card where text widget value is None (unconfigured / null)
        self.context_with_none_text_scene = [
            {
                "media": "text",
                "widgets": {
                    "usage": "scene",
                    "text": None,
                    "name": "Scene 1",
                    "context_id": "txt_scene_1",
                },
            }
        ]
        # Text context card with usage_roles JSON string holding 'scene'
        self.context_with_none_text_usage_roles = [
            {
                "media": "text",
                "widgets": {
                    "usage_roles": '["scene"]',
                    "text": None,
                    "name": "Scene 2",
                    "context_id": "txt_scene_2",
                },
            }
        ]
        # Control context cards with empty string and valid text
        self.context_with_empty_text = [
            {
                "media": "text",
                "widgets": {
                    "usage": "scene",
                    "text": "",
                    "name": "Scene 1",
                    "context_id": "txt_scene_1",
                },
            }
        ]
        self.context_with_valid_text = [
            {
                "media": "text",
                "widgets": {
                    "usage": "scene",
                    "text": "A quiet misty morning in the pine forest.",
                    "name": "Scene 1",
                    "context_id": "txt_scene_1",
                },
            }
        ]

    # --- RED TESTS (Demonstrate BUG-075 on real product code) ---

    def test_story_must_not_crash_when_text_widget_is_none(self):
        """auto_direct.story (line 43) must handle text=None on Scene text card without AttributeError."""
        try:
            result = auto_direct.story("A hero arrives.", self.context_with_none_text_scene)
        except AttributeError as error:
            self.fail(f"BUG-075: auto_direct.story crashed on text=None: {error}")
        self.assertEqual(result, "A hero arrives.")

    def test_story_must_not_crash_when_usage_roles_has_scene_and_text_is_none(self):
        """auto_direct.story must handle usage_roles=['scene'] with text=None without AttributeError."""
        try:
            result = auto_direct.story("A hero arrives.", self.context_with_none_text_usage_roles)
        except AttributeError as error:
            self.fail(f"BUG-075: auto_direct.story crashed on usage_roles scene with text=None: {error}")
        self.assertEqual(result, "A hero arrives.")

    def test_direction_prompt_must_not_crash_when_text_widget_is_none(self):
        """auto_direct.direction_prompt (line 59) must build split prompt when text=None without AttributeError."""
        try:
            prompt = auto_direct.direction_prompt("Main idea", 10.0, self.context_with_none_text_scene)
        except AttributeError as error:
            self.fail(f"BUG-075: auto_direct.direction_prompt crashed on text=None: {error}")
        self.assertIn("Main idea", prompt)

    def test_plan_prompt_must_not_crash_when_text_widget_is_none(self):
        """builder.plan_prompt (line 231) must build Make H3 prompt when text=None without AttributeError."""
        quick = {"direction": "auto", "speech": "none", "language": "English"}
        try:
            prompt = builder.plan_prompt(quick, "Main idea", 10.0, self.context_with_none_text_scene)
        except AttributeError as error:
            self.fail(f"BUG-075: builder.plan_prompt crashed on text=None: {error}")
        self.assertIn("Main idea", prompt)

    def test_analysis_must_not_crash_with_typeerror_when_text_widget_is_none(self):
        """analysis.analyze (line 120) must not crash with TypeError on text=None when analyzing Text card."""
        payload = {
            "request": {},
            "provider": {
                "schema_version": 2,
                "provider": "ollama",
                "model": "qwen",
                "base_url": "http://localhost:11434",
            },
            "media": "text",
            "widgets": {
                "text": None,
                "name": "Note 1",
            },
        }
        # In real code, line 120 executes: prompt += "\n\nContext text:\n" + widgets.get("text", "")
        # which raises TypeError: can only concatenate str (not "NoneType") to str.
        try:
            asyncio.run(analysis.analyze(payload))
        except TypeError as error:
            self.fail(f"BUG-075: analysis.analyze crashed with TypeError on text=None: {error}")
        except Exception:
            # Other errors (e.g. connection error to dummy provider) are expected and acceptable
            pass

    # --- GREEN CONTROLS (Verify expected behavior on normal input) ---

    def test_control_story_with_empty_and_valid_text(self):
        """Control: story combines idea and valid Scene note properly when text is a string."""
        empty_res = auto_direct.story("Main idea", self.context_with_empty_text)
        self.assertEqual(empty_res, "Main idea")

        valid_res = auto_direct.story("Main idea", self.context_with_valid_text)
        self.assertEqual(valid_res, "Main idea\n\nA quiet misty morning in the pine forest.")

    def test_control_direction_prompt_with_valid_text(self):
        """Control: direction_prompt incorporates Scene note text when text is a valid string."""
        prompt = auto_direct.direction_prompt("Main idea", 10.0, self.context_with_valid_text)
        self.assertIn("pine forest", prompt)

    def test_control_plan_prompt_with_valid_text(self):
        """Control: plan_prompt incorporates Scene note text when text is a valid string."""
        quick = {"direction": "auto", "speech": "none", "language": "English"}
        prompt = builder.plan_prompt(quick, "Main idea", 10.0, self.context_with_valid_text)
        self.assertIn("pine forest", prompt)


if __name__ == "__main__":
    unittest.main()
