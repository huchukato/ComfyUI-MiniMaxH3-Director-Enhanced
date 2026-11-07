"""Control lanes: source/story time, pinned heads, native lazy expansion, file safety and resume invalidation."""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from _pack import module, comfy_available, load_full_pack

ctx = module("ng.core.context")
options = module("ng.core.context_options")
timing = module("ng.core.control_timing")
project = module("ng.core.project")
chunks = module("ng.core.chunks")
HAVE_COMFY = comfy_available()


def card(identity="pose", **values):
    return ctx.ContextItem(identity, identity, "video", identity + ".mp4", usage=("control",), length_s=20,
                           options=options.ContextOptions(control_kind="pose"), **values)


def clip(identity="a", context_id="pose", start=0, end=4, offset=0):
    return dict(schema_version=1, id=identity, context_id=context_id, start=start, end=end, offset=offset, lane="control")


def plan(controls, items=None):
    doc = json.dumps(dict(format="h3-director-shots", schema_version=1, shots=[], control=controls))
    return project.plan_project(ctx.DirectorContext(idea="A walk.", project_seconds=12, width=64, height=64, mode="fl2va",
                                shots_text=doc, items=tuple(items or [card()])), 4, chunks.ContinuityPlan("video_audio"))


class Timing(unittest.TestCase):
    def test_control_options_and_clip_round_trip(self):
        settings = options.ContextOptions(control_kind="depth", control_original="walk.mp4", control_result="depth.mp4")
        self.assertEqual(options.ContextOptions.from_dict(settings.to_dict()), settings)
        record = clip()
        self.assertEqual(timing.ControlClip.from_dict(record, "clip").to_dict(), record)
        with self.assertRaises(ValueError):
            options.ContextOptions.from_dict({"control_kind": "unknown"})

    def test_control_is_not_a_motion_reference_or_disabled_in_fl2va(self):
        p = plan([clip()])
        self.assertFalse(any(i.code in ("reference_disabled", "usage_unknown") for i in p.issues))
        self.assertFalse(any(r.kind == "video" for c in p.compiled for r in c.refs))

    def test_control_source_description_does_not_change_any_part_of_the_story(self):
        for mode in ("fl2va", "ref2va"):
            for kind in ("canny", "pose", "depth", "mask"):
                with self.subTest(mode=mode, kind=kind):
                    control = replace(card(description="A red-coated woman walks beside a blue wall."),
                                      options=options.ContextOptions(control_kind=kind, control_mask="mask.mp4" if kind == "mask" else ""))
                    p = plan([clip(start=1, end=2)], [control])
                    p = project.plan_project(replace(p.context, mode=mode), 4, chunks.ContinuityPlan("video_audio"))
                    self.assertTrue(timing.spans(project.jobs(p)[0]))
                    self.assertFalse(timing.spans(project.jobs(p)[-1]))
                    for part in p.compiled:
                        self.assertNotIn(control.description, part.prompt)
                        self.assertNotIn("Video context pose:", part.prompt)
                    self.assertEqual(p.context.item(control.id).description, control.description)

    def test_explicit_narrative_video_roles_keep_their_description(self):
        for role in ("motion", "camera", "structure", "continue"):
            for roles in ((role,), ("control", role)):
                with self.subTest(roles=roles):
                    video = replace(card(description="An intentional narrative video description."), usage=roles)
                    p = project.plan_project(ctx.DirectorContext(idea="A walk.", project_seconds=12, width=64, height=64,
                                             mode="ref2va", items=(video,)), 4, chunks.ContinuityPlan("video_audio"))
                    self.assertIn(video.description, p.compiled[0].prompt)

    def test_offsets_and_pin_window_keep_their_story_position(self):
        p = plan([clip(start=0, end=12, offset=2)])
        for job in project.jobs(p):
            c, a, b, source = timing.spans(job)[0]
            self.assertEqual(a, job.chunk.story_start_f - job.chunk.head_frames)
            self.assertEqual(b, min(job.chunk.story_end_f, 12 * 24))
            self.assertEqual(source, 48 + a)

    def test_no_delivered_control_means_no_control_even_for_head_only_overlap(self):
        p = plan([])
        end = p.plan.chunks[0].story_end_f / 24
        p = plan([clip(end=end)])
        self.assertTrue(timing.spans(project.jobs(p)[0]))
        self.assertFalse(timing.spans(project.jobs(p)[1]))

    def test_overlap_missing_card_and_invalid_ranges_fail_before_render(self):
        for records in ([clip(), clip("b", start=2)], [clip(context_id="missing")], [clip(end=0)], [clip(), clip()]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                plan(records)
        selected = replace(card(), options=options.ContextOptions(start_s=2, end_s=5))
        with self.assertRaisesRegex(ValueError, "selected source range"):
            plan([clip(offset=0)], [selected])

    def test_a_card_without_its_video_says_so(self):
        # the shipped Control workflow has its card empty until the user picks a video (2026-10-25)
        with self.assertRaisesRegex(ValueError, "'pose' has no video yet"):
            plan([clip()], [replace(card(), source="")])

    def test_partial_coverage_and_short_source_are_visible(self):
        p = plan([clip(start=1, end=2)])
        self.assertIn("control_hold", {i.code for i in p.issues})
        p = plan([clip()], [replace(card(), length_s=1)])
        self.assertIn("control_source_hold", {i.code for i in p.issues})
        self.assertIn("control_unplaced", {i.code for i in plan([]).issues})
        self.assertIn("control_outside_project", {i.code for i in plan([clip(start=20, end=21)]).issues})

    def test_a_clip_to_the_project_end_covers_the_grid_overhang(self):
        # workflow 7 (2026-10-26): a 10 s clip in a 10 s project warned, because the part delivers 10.1 s
        p = plan([clip(end=12)])
        self.assertGreater(p.plan.chunks[-1].story_end_f, 12 * 24)
        self.assertNotIn("control_hold", {i.code for i in p.issues})


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_full_pack().NODE_CLASS_MAPPINGS
        cls.resume = module("ng.adapters.resume")
        cls.media = module("ng.adapters.control_media")

    def test_connector_retains_a_raw_lazy_optional_patch_without_putting_it_in_conditioning_links(self):
        node = self.nodes["NGContextConnector"]
        schema = node.GET_SCHEMA()
        port = schema.inputs[-1]
        self.assertEqual(port.id, "model_patch")
        self.assertTrue(port.optional and port.lazy and port.rawLink)
        packet = node.execute(clip=["clip", 0], vae=["vae", 0], audio_vae=["audio", 0], model_fl2va=["model", 0], model_patch=["patch", 0]).args[0]
        self.assertEqual(packet.model_patch, ["patch", 0])
        self.assertNotIn("model_patch", packet.links())

    def test_internal_node_skips_patch_loader_and_decode_for_uncontrolled_parts(self):
        node = self.nodes["NGControlChunk"]
        job = project.jobs(plan([]))[0]
        self.assertEqual(node.check_lazy_status(chunk=job), [])
        with mock.patch.object(self.media, "prepare", side_effect=AssertionError("must not decode")):
            self.assertEqual(node.execute(model="original", chunk=job).args, ("original",))
        job = project.jobs(plan([clip()]))[0]
        self.assertEqual(node.check_lazy_status(chunk=job), ["model_patch", "vae"])
        self.assertEqual(node.check_lazy_status(chunk=job, strength=0), [])

    def test_frame_composition_holds_first_last_and_gaps_without_shifting_the_clip(self):
        import torch
        p = plan([clip(start=1, end=2), clip("b", start=3, end=4, offset=2)])
        job = project.jobs(p)[0]
        def decode(source, start, seconds, **kw):
            return torch.arange(round(start * 24), round((start + seconds) * 24)).float().view(-1, 1, 1, 1).expand(-1, 64, 64, 3)
        with mock.patch.object(self.media, "input_path", return_value="exists"), mock.patch.object(self.media.minimax_media, "load_video_tensor", side_effect=decode):
            out = self.media.prepare(job).control_video[:, 0, 0, 0]
        self.assertEqual(float(out[0]), 0)
        self.assertEqual(float(out[24]), 0)
        self.assertEqual(float(out[47]), 23)
        self.assertEqual(float(out[48]), 23)
        self.assertEqual(float(out[71]), 23)
        self.assertEqual(float(out[72]), 48)
        self.assertEqual(float(out[-1]), 71)

    def test_graph_inserts_control_before_preview_and_guider(self):
        packets = module("ng.adapters.director_packets")
        inputs = packets.DirectorInputs(["clip", 0], ["vae", 0], ["audio", 0], ["model", 0],
                                        model_patch=["patch", 0], preview_vae=["preview", 0])
        result = packets.DirectorResult(inputs, plan([clip()]), packets.RenderSettings())
        graph, _ = packets.render_project(result)
        nodes = {v["class_type"]: (k, v) for k, v in graph.items()}
        control_id, control = nodes["NGControlChunk"]
        self.assertEqual(control["inputs"]["model_patch"], ["patch", 0])
        self.assertEqual(nodes["NGH3Preview"][1]["inputs"]["model"], [control_id, 0])
        self.assertNotIn("model_patch", nodes["NGChunkConditioning"][1]["inputs"])
        with self.assertRaisesRegex(ValueError, "model_patch"):
            packets.render_project(replace(result, inputs=replace(inputs, model_patch=None)))

    def test_resume_changes_only_from_the_first_affected_part_onward(self):
        jobs = project.jobs(plan([clip(start=5, end=6)]))
        a = [self.resume.part_key(j, {"seed": 7, "control_strength": 1}) for j in jobs]
        b = [self.resume.part_key(j, {"seed": 7, "control_strength": .5}) for j in jobs]
        self.assertEqual(a[0], b[0])
        self.assertNotEqual(a[1], b[1])
        self.assertNotEqual(a[2], b[2])
        with mock.patch.object(self.resume, "_file", return_value=[123, 4]):
            c = [self.resume.part_key(j, {"seed": 7, "control_strength": 1}) for j in jobs]
        self.assertEqual(a[0], c[0])
        self.assertNotEqual(a[1], c[1])

    def test_import_is_contained_unique_and_keeps_source(self):
        files = module("ng.adapters.control_files")
        with tempfile.TemporaryDirectory() as root:
            output, inputs = os.path.join(root, "output"), os.path.join(root, "input")
            os.makedirs(os.path.join(output, "h3-control"))
            os.makedirs(inputs)
            with open(os.path.join(output, "h3-control", "test.mp4"), "wb") as f:
                f.write(b"generated video")
            with mock.patch.object(files.folder_paths, "get_output_directory", return_value=output), mock.patch.object(files.folder_paths, "get_input_directory", return_value=inputs):
                first, second = files.import_video("test.mp4", "h3-control"), files.import_video("test.mp4", "h3-control")
                self.assertNotEqual(first, second)
                for filename, subfolder in (("../test.mp4", "h3-control"), ("test.mp4", "../outside"), ("test.txt", "h3-control")):
                    with self.assertRaises(ValueError):
                        files.import_video(filename, subfolder)
            self.assertTrue(os.path.isfile(os.path.join(output, "h3-control", "test.mp4")))
            with open(os.path.join(inputs, first), "rb") as f:
                self.assertEqual(f.read(), b"generated video")
