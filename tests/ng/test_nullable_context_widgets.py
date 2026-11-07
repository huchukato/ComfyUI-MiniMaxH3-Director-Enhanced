"""Context widget nullability through real ComfyUI input preparation, execution and API parsers."""
import asyncio
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":
    sys.path.insert(0, str(REPO / "tests" / "ng"))
from _pack import comfy_available, load_full_pack

class NullableContextWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved_argv = sys.argv[:]
        try:
            sys.argv = [sys.argv[0], "--cpu"]
            if not comfy_available():
                raise unittest.SkipTest("ComfyUI is not importable")
            cls.pack = load_full_pack()
            cls.execution = importlib.import_module("execution")
            cls.io = importlib.import_module("comfy_api.latest._io")
            for short, name in {"build": "ng.core.context_build", "core": "ng.core.context", "split": "ng.core.split",
                                "draft": "ng.core.shot_draft", "preview": "ng.core.preview", "routes": "ng.nodes.analysis_routes",
                                "node_module": "ng.nodes.context_nodes", "legacy": "minimax_media"}.items():
                setattr(cls, short, importlib.import_module(cls.pack.__name__ + "." + name))
            cls.SchemaError = importlib.import_module(cls.pack.__name__ + ".ng.core.issues").SchemaError
        finally:
            sys.argv = saved_argv

    def image_context(self, name):
        return [{"media": "image", "widgets": {"image": "hero.png", "name": name, "context_id": "ctx_image", "description": "A gardener."}}]

    def execute(self, kind, field, value):
        media = kind.replace("NGContext", "").lower()
        node = self.pack.NODE_CLASS_MAPPINGS[kind]
        raw = {media: "hero.png" if media == "image" else "voice.wav", "name": "Hero" if media == "image" else "Voice",
               "description": "", "color": "", "context_id": "ctx_" + media, "preserve": "high",
               "content": "character" if media == "image" else "voice", "usage": "reference" if media == "image" else "voice"}
        if media == "audio":
            raw["speaker"] = ""
        raw[field] = ["source", 0]
        cache = SimpleNamespace(get_cache=lambda source, target: SimpleNamespace(outputs=[[value]]))
        values, missing, v3 = self.execution.get_input_data(raw, node, "context", execution_list=cache)
        self.assertFalse(missing)
        nested = self.io.build_nested_inputs({key: entries[0] for key, entries in values.items()}, v3)
        self.assertEqual(nested[field], value)
        with patch.object(self.node_module.probe, "duration_seconds", return_value=5.0):
            return asyncio.run(self.execution._async_map_node_over_list("audit", "context", node, values, "execute", v3_data=v3))[0].args[0]

    def test_real_runtime_none_links_produce_unset_text(self):
        for field in ("name", "description", "color"):
            item = self.execute("NGContextImage", field, None)
            self.assertEqual(getattr(item, field), "hero" if field == "name" else "")
            self.assertEqual(item.id, "ctx_image")
        self.assertEqual(self.execute("NGContextAudio", "speaker", None).speaker, "")

    def test_blank_and_valid_text_links_are_preserved(self):
        self.assertEqual(self.execute("NGContextImage", "name", "").name, "hero")
        self.assertEqual(self.execute("NGContextImage", "name", "  Alice  ").name, "Alice")
        self.assertEqual(self.execute("NGContextAudio", "speaker", "Alice").speaker, "Alice")
        self.assertEqual(self.execute("NGContextImage", "description", "  A gardener.  ").description, "A gardener.")

    def test_existing_widget_text_coercions_remain_compatible(self):
        for field in ("name", "description", "speaker", "color"):
            for value in (0, False, 42, [], {}):
                with self.subTest(field=field, value=value):
                    item = self.build.item_from_widgets("audio", {"audio": "voice.wav", field: value})
                    self.assertEqual(getattr(item, field), str(value))
        for value in (0, False, 42, [], {}):
            with self.subTest(parser_name=value), self.assertRaisesRegex(self.SchemaError, "expected text"):
                self.draft.plain_mentions("A scene.", self.image_context(value))

    def test_comfy_literal_string_coercion_and_explicit_none_text_are_preserved(self):
        import nodes
        node = self.pack.NODE_CLASS_MAPPINGS["NGContextText"]
        for value in (0, False, 42, "None", "Ålice", ""):
            raw = {"text": "A quiet note.", "name": value, "description": "", "content": "shot", "usage": "rule", "preserve": "high"}
            prompt = {"context": {"class_type": "NGContextText", "inputs": raw}}
            with self.subTest(value=value), patch.dict(nodes.NODE_CLASS_MAPPINGS, {"NGContextText": node}):
                valid, errors, _ = asyncio.run(self.execution.validate_inputs("audit", prompt, "context", {}))
                self.assertTrue(valid, errors)
            self.assertEqual(raw["name"], str(value))
            inputs, missing, v3 = self.execution.get_input_data(raw, node, "context")
            self.assertFalse(missing)
            item = asyncio.run(self.execution._async_map_node_over_list("audit", "context", node, inputs, "execute", v3_data=v3))[0].args[0]
            self.assertEqual(item.name, str(value) if str(value) else "A quiet note.")

    def test_core_models_keep_strict_string_contract(self):
        item = self.build.item_from_widgets("image", {"image": "hero.png"}).to_dict()
        for field in ("name", "description", "speaker", "color"):
            with self.subTest(field=field), self.assertRaisesRegex(self.SchemaError, "expected text"):
                self.core.ContextItem.from_dict({**item, field: None})

    def test_preview_none_description_uses_reference_fallback(self):
        result = self.preview.plan_preview({"director": {"idea": "A portrait.", "project_seconds": 5},
                                       "contexts": [{"media": "image", "widgets": {"image": "hero.png", "description": None}}]})
        self.assertTrue(result["ok"], result)
        self.assertIn("<Subject 1> is the person shown in <Picture 1>.", result["chunks"][0]["prompt"])

    def test_null_name_parser_preserves_dialogue_and_unknown_mentions(self):
        contexts = self.image_context(None)
        self.assertEqual(self.draft.plain_mentions("The @Ghost walks.", contexts), ("The Ghost walks.", ["Ghost"]))
        data = {"shots": [{"start_s": 0, "end_s": 5, "action": "A figure walks.", "lines": []}]}
        parsed = json.loads(self.split.parse_split(data, 5, contexts, "@Hero says: Exact words.")["shots"])
        self.assertEqual(parsed["shots"][0]["spoken"][0]["text"], "Exact words.")
        self.assertEqual(parsed["shots"][0]["spoken"][0]["speaker_id"], "")
        self.assertEqual(parsed["shots"][0]["spoken"][0]["voice"], "Hero")     # spelled as written (BUG-087)

    def test_null_name_route_succeeds_without_broad_exception_handler(self):
        provider = {"schema_version": 2, "provider": "ollama", "base_url": "http://127.0.0.1:11434", "model": "audit-never-called"}
        payload = {"provider": provider, "director": {"idea": "A figure walks.", "project_seconds": 5}, "contexts": self.image_context(None)}
        request = SimpleNamespace(json=AsyncMock(return_value=payload))
        answer = json.dumps({"shots": [{"start_s": 0, "end_s": 5, "action": "A figure walks.", "lines": []}]})
        for route in (self.routes.direct_scenes, self.routes.build_plan):
            with self.subTest(route=route.__name__), patch.object(self.routes, "_api_key", return_value=""), patch.object(self.legacy, "vlm_generate", AsyncMock(return_value=answer)):
                response = asyncio.run(route(request))
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.body)["ok"])

if __name__ == "__main__":
    unittest.main()
