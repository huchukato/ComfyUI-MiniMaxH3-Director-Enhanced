"""Unset text at real STRING-link and HTTP widget boundaries; valid text is preserved."""
import asyncio
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/ng"))
from _pack import comfy_available, load_full_pack


class NullableTextCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved_argv = sys.argv[:]
        try:
            sys.argv = [sys.argv[0], "--cpu"]
            if not comfy_available():
                raise unittest.SkipTest("ComfyUI unavailable")
            cls.pack = load_full_pack()
            cls.execution = importlib.import_module("execution")
            for short, name in {"build": "ng.core.context_build", "core": "ng.core.context", "auto": "ng.core.auto_direct",
                                "builder": "ng.core.builder", "routes": "ng.nodes.analysis_routes", "legacy": "minimax_media"}.items():
                setattr(cls, short, importlib.import_module(cls.pack.__name__ + "." + name))
        finally:
            sys.argv = saved_argv

    @staticmethod
    def contexts(text):
        return [{"media": "text", "widgets": {"text": text, "name": "Scene 1", "context_id": "scene1", "usage": "scene"}}]

    def linked_text(self, value):
        node = self.pack.NODE_CLASS_MAPPINGS["NGContextText"]
        raw = {"text": ["source", 0], "name": "Scene 1", "description": "", "content": "scene", "usage": "scene", "preserve": "high", "context_id": "scene1"}
        cache = SimpleNamespace(get_cache=lambda source, target: SimpleNamespace(outputs=[[value]]))
        values, missing, v3 = self.execution.get_input_data(raw, node, "text_card", execution_list=cache)
        self.assertFalse(missing)
        self.assertEqual(values["text"], [value])
        return asyncio.run(self.execution._async_map_node_over_list("audit075", "text_card", node, values, "execute", v3_data=v3))[0].args[0]

    def test_linked_none_becomes_empty_note_and_valid_links_are_preserved(self):
        self.assertEqual(self.linked_text(None).source, "")
        for value in ("", "None", "  Ålice [walks].\n", "A forest."):
            with self.subTest(value=value):
                self.assertEqual(self.linked_text(value).source, value)
                self.assertEqual(self.linked_text(value).id, "scene1")

    def test_widget_builder_preserves_existing_non_null_string_coercion(self):
        for value in (0, False, 42, [], {}):
            with self.subTest(value=value):
                self.assertEqual(self.build.item_from_widgets("text", {"text": value}).source, str(value))

    def test_story_and_plan_none_are_empty_valid_text_remains(self):
        for value, expected in ((None, "Main idea"), ("", "Main idea"), ("  ", "Main idea"), ("None", "Main idea\n\nNone"), ("  A forest.  ", "Main idea\n\nA forest.")):
            with self.subTest(value=value):
                contexts = self.contexts(value)
                self.assertEqual(self.auto.story("Main idea", contexts), expected)
                quick = {"direction": "auto", "speech": "none", "language": "English"}
                self.assertIn("Main idea", self.builder.plan_prompt(quick, "Main idea", 5, contexts))
        missing = self.contexts("")
        del missing[0]["widgets"]["text"]
        self.assertEqual(self.auto.story("Main idea", missing), "Main idea")

    def test_null_text_real_routes_return_success_and_transport_gets_empty_text(self):
        provider = {"schema_version": 2, "provider": "ollama", "base_url": "http://127.0.0.1:11434", "model": "audit-never-called"}
        payload = {"provider": provider, "director": {"idea": "A figure walks.", "project_seconds": 5}, "contexts": self.contexts(None)}
        shot_answer = json.dumps({"shots": [{"start_s": 0, "end_s": 5, "action": "A figure walks.", "lines": []}]})
        for route in (self.routes.direct_scenes, self.routes.build_plan):
            with self.subTest(route=route.__name__), patch.object(self.routes, "_api_key", return_value=""), patch.object(self.legacy, "vlm_generate", AsyncMock(return_value=shot_answer)) as transport:
                response = asyncio.run(route(SimpleNamespace(json=AsyncMock(return_value=payload))))
                self.assertEqual(response.status, 200, response.text)
                self.assertTrue(json.loads(response.text)["ok"])
                transport.assert_awaited_once()
        answer = '{"description":"No note text","content":"scene","usage":"scene","why":"Empty text"}'
        for text in (None, "", "None", "  Exact note.  "):
            body = {"provider": provider, "media": "text", "widgets": {"text": text}}
            with self.subTest(text=text), patch.object(self.routes, "_api_key", return_value=""), patch.object(self.legacy, "vlm_generate", AsyncMock(return_value=answer)) as transport:
                response = asyncio.run(self.routes.analyze_context(SimpleNamespace(json=AsyncMock(return_value=body))))
                self.assertEqual(response.status, 200, response.text)
                self.assertTrue(transport.call_args.args[1].endswith("Context text:\n" + ("" if text is None else text)))

    def test_invalid_api_text_gets_schema_error_without_losing_core_contract(self):
        for value in (0, False, 42, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "context.widgets.text.*expected text"):
                self.auto.story("Main idea", self.contexts(value))
        item = self.build.item_from_widgets("text", {"text": "A note"}).to_dict()
        with self.assertRaisesRegex(ValueError, "source.*expected text"):
            self.core.ContextItem.from_dict({**item, "source": None})


if __name__ == "__main__":
    unittest.main()
