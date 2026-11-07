"""Inpaint cards: source/mask pairs keep their file time, shape and resume identity."""
import json
import sys
import unittest
from dataclasses import replace
from unittest import mock

from _pack import module, comfy_available, load_full_pack

ctx = module("ng.core.context")
opts = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def mask_card(**changes):
    return ctx.ContextItem("source", "Walk", "video", "source.mp4", usage=("control",), length_s=20,
                           options=opts.ContextOptions(control_kind="mask", control_mask="mask.mp4", **changes))


def plan(items, entries=None):
    controls = entries if entries is not None else [dict(schema_version=1, id="mask", context_id="source", start=5, end=6, offset=2)]
    doc = json.dumps(dict(format="h3-director-shots", schema_version=1, shots=[], control=controls))
    context = ctx.DirectorContext(idea="Walk", project_seconds=12, width=64, height=64, shots_text=doc, items=tuple(items))
    return project.plan_project(context, 4, chunks.ContinuityPlan("video_audio"))


class MaskOptions(unittest.TestCase):
    def test_mask_settings_round_trip_and_validate(self):
        options = mask_card(mask_prompt="red ball", mask_shape="outline", mask_grow=8).options
        self.assertEqual(opts.ContextOptions.from_dict(options.to_dict()), options)
        for changes in ({"mask_shape": "ellipse"}, {"mask_grow": -1}, {"mask_grow": 1.5}, {"mask_grow": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                opts.ContextOptions.from_dict({**options.to_dict(), **changes})

    def test_placed_masks_require_a_mask_for_the_current_source(self):
        card = mask_card()
        for options in (replace(card.options, control_mask=""), replace(card.options, control_result="old-source.mp4")):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "mask"):
                plan([replace(card, options=options)])
        self.assertTrue(plan([replace(card, options=replace(card.options, control_mask=""))], []).issues)


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class MaskRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_full_pack().NODE_CLASS_MAPPINGS
        cls.media = module("ng.adapters.control_media")
        cls.resume = module("ng.adapters.resume")

    def decode(self, filename, start, seconds, **kw):
        import torch
        count = round(seconds * 24)
        if filename == "mask.mp4":
            out = torch.zeros(count, 64, 64, 3)
            out[:, 20:24, 30:34] = 1
            return out
        return torch.arange(round(start * 24), round(start * 24) + count).float().view(-1, 1, 1, 1).expand(-1, 64, 64, 3)

    def prepared(self, p, index=1):
        with mock.patch.object(self.media, "input_path", return_value="exists"), \
                mock.patch.object(self.media.probe, "duration_seconds", return_value=20), \
                mock.patch.object(self.media.minimax_media, "load_video_tensor", side_effect=self.decode) as read:
            out = self.media.prepare(project.jobs(p)[index])
            return out, read.call_args_list

    def test_source_and_mask_use_the_same_offset_and_both_hold_at_part_edges(self):
        p = plan([mask_card(mask_grow=0)])
        out, reads = self.prepared(p)
        self.assertIsNone(out.control_video, "pure inpaint uses native zero hint, not an encoded black control video")
        self.assertEqual(reads[0].args[1:3], reads[1].args[1:3])
        self.assertEqual(reads[0].args[1], 2)
        self.assertEqual(float(out.source_video[0, 0, 0, 0]), 48)
        self.assertEqual(float(out.source_video[-1, 0, 0, 0]), 71)
        self.assertEqual(tuple(out.mask.shape), tuple(out.source_video.shape[:3]))
        self.assertEqual(float(out.mask[0].sum()), 16)
        self.assertEqual(float(out.mask[-1].sum()), 16)

    def test_selected_source_end_bounds_the_mask_as_well(self):
        p = plan([mask_card(start_s=2, end_s=2.5, mask_grow=0)])
        out, reads = self.prepared(p)
        self.assertEqual([c.args[2] for c in reads], [.5, .5])
        self.assertEqual(float(out.source_video[-1, 0, 0, 0]), 59)

    def test_mixed_control_has_no_visible_black_background_outside_the_inpaint_clip(self):
        mask = mask_card(mask_grow=0)
        edge = replace(mask, id="edges", name="Edges", source="canny.mp4", options=opts.ContextOptions())
        controls = [dict(schema_version=1, id="a", context_id="source", start=0, end=1, offset=0),
                    dict(schema_version=1, id="b", context_id="edges", start=2, end=4, offset=3)]
        out, _ = self.prepared(plan([mask, edge], controls), 0)
        self.assertEqual(float(out.mask[0].sum()), 16)
        self.assertEqual(float(out.mask[47].sum()), 16, "gap holds preceding mask")
        self.assertEqual(float(out.mask[48].min()), 1, "all pixels regenerate outside an inpaint clip; zero source stays hidden")
        self.assertEqual(float(out.control_video[48, 0, 0, 0]), 72)
        self.assertEqual(float(out.source_video[48].sum()), 0)

    def test_internal_node_passes_masks_and_sources_to_the_native_apply(self):
        node = self.nodes["NGControlChunk"]
        job = project.jobs(plan([mask_card()]))[1]
        native = mock.Mock()
        native.MiniMaxH3FunControlNetApply.execute.return_value.args = ("patched",)
        frames = self.media.ControlFrames(None, "hole", "source")
        node_module = sys.modules[node.__module__]
        with mock.patch.object(node_module.control_media, "prepare", return_value=frames), mock.patch.object(node_module, "core", return_value=native):
            self.assertEqual(node.execute("model", job, "patch", "vae").args, ("patched",))
        call = native.MiniMaxH3FunControlNetApply.execute.call_args.kwargs
        self.assertEqual((call["control_video"], call["mask"], call["source_video"]), (None, "hole", "source"))

    def test_resume_tracks_mask_file_shape_and_grow_only_from_the_affected_part(self):
        base = mask_card()
        jobs = project.jobs(plan([base]))
        original = [self.resume.part_key(j, {}) for j in jobs]
        for options in (replace(base.options, control_mask="different.mp4"), replace(base.options, mask_shape="outline"), replace(base.options, mask_grow=8)):
            changed = [self.resume.part_key(j, {}) for j in project.jobs(plan([replace(base, options=options)]))]
            self.assertEqual(original[0], changed[0])
            self.assertNotEqual(original[1], changed[1])
            self.assertNotEqual(original[2], changed[2])
        with mock.patch.object(self.resume, "_file", side_effect=lambda name: [123, 4] if name == "mask.mp4" else None):
            changed = [self.resume.part_key(j, {}) for j in jobs]
        self.assertEqual(original[0], changed[0])
        self.assertNotEqual(original[1], changed[1])

    def test_context_cache_fingerprint_includes_mask_bytes(self):
        node = self.nodes["NGContextVideo"]
        probe = sys.modules[node.__module__].probe
        with mock.patch.object(probe, "file_stamp", side_effect=lambda name: "mask-a" if name == "mask.mp4" else "source"):
            first = node.fingerprint_inputs("source.mp4", json.dumps(mask_card().options.to_dict()))
        with mock.patch.object(probe, "file_stamp", side_effect=lambda name: "mask-b" if name == "mask.mp4" else "source"):
            second = node.fingerprint_inputs("source.mp4", json.dumps(mask_card().options.to_dict()))
        self.assertNotEqual(first, second)
