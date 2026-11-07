"""Preset safety, chunk duration and explicit context-name contracts."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _pack import module, load_full_pack, stub_prompt_server

storage = module("ng.adapters.presets")
build = module("ng.core.context_build")
core_presets = module("ng.core.presets")
chunks = module("ng.core.chunks")
frames = module("ng.core.frames")
limits = module("ng.core.limits")
context = module("ng.core.context")
preview = module("ng.core.preview")


def preset(media, name="Maya", source=None, description="original"):
    widgets = {media: source or ("maya." + {"image": "png", "audio": "wav", "video": "mp4", "text": "txt"}[media]),
               "name": media + " card", "context_id": "ctx_" + media, "description": description}
    return core_presets.ContextPreset(name, build.item_from_widgets(media, widgets)).to_dict()


def legacy_file(root, data):
    target = storage._path(root, data["name"])
    Path(target).write_text(json.dumps(data), encoding="utf8")
    return Path(target)


class PresetSafety(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = self.directory.name

    def test_four_media_same_name_are_loadable_without_loss(self):
        for media in ("image", "video", "audio", "text"):
            storage.save(self.root, preset(media))
        for media in ("image", "video", "audio", "text"):
            with self.subTest(media=media):
                self.assertEqual(storage.listing(self.root, media), ["Maya"])
                self.assertEqual(storage.load(self.root, "Maya", media).item.media, media)
        with self.assertRaisesRegex(ValueError, "media type"):
            storage.load(self.root, "Maya")

    def test_same_media_repeated_save_keeps_other_media_content(self):
        storage.save(self.root, preset("image"))
        storage.save(self.root, preset("audio"))
        for index in range(3):
            storage.save(self.root, preset("image", description="image version %d" % index))
        self.assertEqual(storage.load(self.root, "Maya", "image").item.description, "image version 2")
        self.assertEqual(storage.load(self.root, "Maya", "audio").item.description, "original")
        self.assertEqual(storage.listing(self.root, "image"), ["Maya"])

    def test_old_preset_survives_another_medium_save_byte_for_byte(self):
        target = legacy_file(self.root, preset("image"))
        original = target.read_bytes()
        storage.save(self.root, preset("audio"))
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(storage.load(self.root, "Maya", "image").item.media, "image")
        self.assertEqual(storage.load(self.root, "Maya", "audio").item.media, "audio")

    def test_updated_legacy_same_media_has_priority_and_one_list_entry(self):
        target = legacy_file(self.root, preset("image"))
        original = target.read_bytes()
        self.assertEqual(storage.load(self.root, "Maya").item.description, "original")
        storage.save(self.root, preset("image", description="updated"))
        self.assertEqual(storage.listing(self.root, "image"), ["Maya"])
        self.assertEqual(storage.load(self.root, "Maya", "image").item.description, "updated")
        self.assertEqual(storage.load(self.root, "Maya").item.description, "updated")
        self.assertEqual(target.read_bytes(), original)

    def test_failed_atomic_replace_preserves_existing_file_and_no_temp(self):
        storage.save(self.root, preset("image"))
        original = {p.name: p.read_bytes() for p in Path(self.root).iterdir()}
        with patch.object(storage.os, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaisesRegex(OSError, "replace failure"):
                storage.save(self.root, preset("image", description="must not persist"))
        self.assertEqual({p.name: p.read_bytes() for p in Path(self.root).iterdir()}, original)
        self.assertEqual(storage.load(self.root, "Maya").item.description, "original")

    def test_unambiguous_legacy_caller_and_disk_path_labels_remain_usable(self):
        data = preset("text", "../Maya: café")
        storage.save(self.root, data)
        self.assertEqual(storage.load(self.root, data["name"]).item.media, "text")
        self.assertEqual(storage.load(self.root, data["name"], "text").name, data["name"])
        self.assertTrue(all(p.parent == Path(self.root) for p in Path(self.root).iterdir()))
        self.assertTrue(all(p.name.startswith("context_") for p in Path(self.root).iterdir()))

    def test_wrong_media_legacy_load_is_reported(self):
        legacy_file(self.root, preset("image"))
        with self.assertRaisesRegex(ValueError, "media type"):
            storage.load(self.root, "Maya", "audio")


class ChunkLengths(unittest.TestCase):
    def test_all_pin_windows_short_targets_and_long_projects_keep_length(self):
        # 4 seconds is the trained minimum user duration. Some shorter requests
        # cannot satisfy a 17-frame tolerance because H3's first clip is >=107.
        count = 0
        for head in (0, *limits.PIN_VIDEO_WINDOWS):
            for target in (12, 48, 96, 120, 240, 360):
                for total in (*range(96, 3001, 13), 7200, 14400):
                    lengths = chunks.plan_lengths(total, target, head)
                    self.assertLessEqual(abs(sum(lengths) - total), limits.GRID_STEP,
                                         "head=%s target=%s total=%s lengths=%s" % (head, target, total, lengths))
                    for index, length in enumerate(lengths):
                        sampled = length + (head if index else 0)
                        self.assertTrue(frames.on_grid(sampled))
                        self.assertGreaterEqual(sampled, limits.SAMPLED_MIN_FRAMES)
                        self.assertLessEqual(sampled, limits.SAMPLED_MAX_FRAMES)
                    count += 1
        print("checked", count, "duration/target/pin-window combinations")


class DuplicateNameContract(unittest.TestCase):
    def test_paired_automatic_names_get_a_free_name_instead_of_stopping_the_plan(self):
        # Real UI leaves names blank and generates two distinct persistent IDs; matching source stems give the same
        # derived name. Since BUG-067 (2026-10-11) the later card gets a free name, as a copied card does ("Mage 2").
        raw = [{"media": medium, "widgets": {medium: "scene1." + extension, "name": "", "context_id": identity}}
               for medium, extension, identity in (("image", "png", "ctx_image"), ("audio", "wav", "ctx_audio"))]
        items = build.distinct([build.item_from_widgets(entry["media"], entry["widgets"]) for entry in raw])
        self.assertEqual([item.name for item in items], ["scene1", "scene1 2"])
        self.assertEqual([item.id for item in items], ["ctx_image", "ctx_audio"], "real IDs stay")
        context.require_unique(items)
        response = preview.plan_preview({"director": {"idea": "A scene", "project_seconds": 5}, "contexts": raw})
        self.assertTrue(response["ok"], response.get("error"))

    def test_rename_the_audio_card_preserves_both_media_and_speaker(self):
        raw = [{"media": "image", "widgets": {"image": "scene1.png", "name": "", "context_id": "ctx_image"}},
               {"media": "audio", "widgets": {"audio": "scene1.wav", "name": "Scene1 voice", "context_id": "ctx_audio",
                                                "speaker": "ctx_image", "usage": "voice"}}]
        response = preview.plan_preview({"director": {"idea": "@scene1 walks", "project_seconds": 5}, "contexts": raw})
        self.assertTrue(response["ok"], response.get("error"))
        items = [build.item_from_widgets(entry["media"], entry["widgets"]) for entry in raw]
        context.require_unique(items)
        resolved, issues = module("ng.core.project").resolve_speakers(items)
        self.assertEqual(resolved[1].speaker, "ctx_image")
        self.assertFalse(issues)

    def test_explicit_cross_media_casefold_duplicate_is_also_refused(self):
        items = [build.item_from_widgets("image", {"image": "first.png", "name": "Maya", "context_id": "i"}),
                 build.item_from_widgets("audio", {"audio": "voice.wav", "name": "MAYA", "context_id": "a"})]
        with self.assertRaisesRegex(ValueError, "name used twice"):
            context.require_unique(items)


class RealPresetRoutes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        load_full_pack()
        stub_prompt_server()
        self.routes = module("ng.nodes.context_routes")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root_patch = patch.object(self.routes, "preset_root", return_value=self.directory.name)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    async def test_save_list_load_same_name_on_image_and_audio_routes(self):
        for media in ("image", "audio"):
            widgets = {media: "route." + ("png" if media == "image" else "wav"), "name": media + " card", "context_id": media}
            response = await self.routes.write_preset(types.SimpleNamespace(json=AsyncMock(return_value={"media": media, "name": "Maya", "widgets": widgets})))
            self.assertEqual(response.status, 200, response.text)
        for media in ("image", "audio"):
            response = await self.routes.list_presets(types.SimpleNamespace(query={"media": media}))
            self.assertEqual(json.loads(response.text)["names"], ["Maya"])
            response = await self.routes.read_preset(types.SimpleNamespace(query={"media": media, "name": "Maya"}))
            self.assertEqual(response.status, 200, response.text)
            self.assertEqual(json.loads(response.text)["widgets"]["context_id"], media)

    async def test_route_reads_old_legacy_preset_and_refuses_wrong_medium(self):
        legacy_file(self.directory.name, preset("image"))
        good = await self.routes.read_preset(types.SimpleNamespace(query={"media": "image", "name": "Maya"}))
        bad = await self.routes.read_preset(types.SimpleNamespace(query={"media": "audio", "name": "Maya"}))
        self.assertEqual(good.status, 200, good.text)
        self.assertEqual(json.loads(good.text)["widgets"]["context_id"], "ctx_image")
        self.assertEqual(bad.status, 400)
        self.assertIn("media type", json.loads(bad.text)["error"])


def load_tests(loader, tests, pattern):
    # Keep the Bug-Hunter originals unchanged and register only verified cases.
    import importlib.util
    for filename in ("bug_064_chunk_target_inflates_length.py", "bug_065_preset_name_shared_across_media.py"):
        source = Path(__file__).parent / "regressions" / filename
        spec = importlib.util.spec_from_file_location("workflow_fixer_" + source.stem, source)
        regression = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(regression)
        tests.addTests(loader.loadTestsFromModule(regression))
    return tests


if __name__ == "__main__":
    unittest.main(verbosity=2)
