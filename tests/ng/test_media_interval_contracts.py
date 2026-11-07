"""Card ranges, lane file offsets, primary voices and coverage must agree with actual compiled plans."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from _pack import comfy_available, module, stub_prompt_server

comfy_available()
stub_prompt_server()
ctx = module("ng.core.context")
opts = module("ng.core.context_options")
build = module("ng.core.context_build")
timing = module("ng.core.audio_timing")
bridge = module("ng.core.legacy_bridge")
project = module("ng.core.project")
chunks = module("ng.core.chunks")
preview = module("ng.core.preview")


def document(total, clips=(), bindings=()):
    return json.dumps({"format": "h3-director-shots", "schema_version": 1,
                       "shots": [{"id": "s1", "start": 0, "end": total, "text": "A scene.",
                                  "media": list(bindings), "spoken": []}], "audio": list(clips)})


def clip(start, end, offset=1, mode="ref"):
    return dict(schema_version=1, id="clip", context_id="voice", start=start, end=end,
                offset=offset, mode=mode, lane="lane")


def voice(options=None, length=20, role="voice", speaker="figure"):
    return ctx.ContextItem("voice", "Voice", "audio", "voice.wav", usage=(role,), speaker=speaker,
                           length_s=length, options=options or opts.ContextOptions())


def planned(items, total=30, shots="", mode="ref2va"):
    context = ctx.DirectorContext(idea="A scene.", items=tuple(items), shots_text=shots, project_seconds=total,
                                  mode=mode, soundscape="Room tone", music="N/A")
    return project.plan_project(context, 10, chunks.ContinuityPlan("video_audio", 22, 24))


FIGURE = ctx.ContextItem("figure", "Figure", "image", "figure.png", content=("character",), usage=("reference",))


class MediaIntervalContracts(unittest.TestCase):
    def test_known_lane_file_end_limits_coverage_and_preserves_dulling(self):
        sound = voice(opts.ContextOptions(start_s=2, end_s=7), 60, role="lock", speaker="")
        result = planned((sound,), total=60, shots=document(60, [clip(0, 60, offset=10, mode="lock")]))
        self.assertEqual(timing.locked_spans(result.context), [(0, 1200)])
        self.assertIn("audio_dulling", {issue.code for issue in result.issues})
        for chunk, compiled in zip(result.plan.chunks, result.compiled):
            base = chunk.story_start_f - chunk.head_frames
            for ref in compiled.of_kind("lock"):
                self.assertLessEqual(base + ref.start_f + ref.length_f, 1200)

    def test_unknown_lane_file_length_preserves_the_declared_span(self):
        sound = voice(opts.ContextOptions(start_s=2, end_s=7), 0, role="lock", speaker="")
        result = planned((sound,), total=60, shots=document(60, [clip(0, 60, offset=10, mode="lock")]))
        self.assertEqual(timing.locked_spans(result.context), [(0, 1440)])
        self.assertNotIn("audio_dulling", {issue.code for issue in result.issues})
        self.assertTrue(all(compiled.of_kind("lock") for compiled in result.compiled))

    def test_lane_offset_at_or_past_known_file_end_creates_no_coverage(self):
        for offset in (4, 5):
            with self.subTest(offset=offset):
                sound = voice(length=4, role="lock", speaker="")
                result = planned((sound,), total=60, shots=document(60, [clip(0, 60, offset=offset, mode="lock")]))
                self.assertEqual(timing.locked_spans(result.context), [])
                self.assertTrue(all(not compiled.of_kind("lock") for compiled in result.compiled))
                self.assertIn("audio_dulling", {issue.code for issue in result.issues})

    def test_lane_overlap_priority_keeps_positive_pieces_and_their_advanced_offsets(self):
        first = voice(length=6, role="lock", speaker="")
        second = ctx.ContextItem("second", "Second", "audio", "second.wav", usage=("lock",), length_s=20)
        earlier = clip(0, 6, offset=1, mode="lock")
        later = {**clip(4, 10, offset=0, mode="lock"), "id": "later", "context_id": "second"}
        result = planned((first, second), total=20, shots=document(20, [earlier, later]))
        self.assertEqual(timing.locked_spans(result.context), [(0, 120), (144, 240)])
        first_refs = result.compiled[0].of_kind("lock")
        self.assertEqual([(r.ctx_id, r.start_f, r.trim_start_f, r.length_f) for r in first_refs],
                         [("voice", 0, 24, 120), ("second", 144, 48, 96)])

    def test_earlier_reference_clip_still_reserves_its_lane_before_later_lock(self):
        first = voice(length=20, speaker="")
        second = ctx.ContextItem("second", "Second", "audio", "second.wav", usage=("lock",), length_s=5)
        earlier = clip(0, 6, offset=0, mode="ref")
        later = {**clip(4, 10, offset=0, mode="lock"), "id": "later", "context_id": "second"}
        result = planned((first, second), total=20, shots=document(20, [earlier, later]))
        self.assertEqual(timing.locked_spans(result.context), [(144, 216)])
        self.assertEqual([(r.start_f, r.trim_start_f, r.length_f) for r in result.compiled[0].of_kind("lock")], [(144, 48, 72)])

    def test_real_video_node_and_decoder_handle_a_valid_file_without_duration_metadata(self):
        import av
        import folder_paths
        import numpy as np
        nodes = module("ng.nodes.context_nodes")
        probe = module("ng.adapters.probe")
        media = module("ng.adapters.media")
        with tempfile.TemporaryDirectory() as directory:
            source = "duration_unknown.mkv"
            with av.open(str(Path(directory) / source), mode="w", format="matroska", options={"live": "1"}) as container:
                stream = container.add_stream("ffv1", rate=24)
                stream.width = stream.height = 64
                stream.pix_fmt = "yuv420p"
                for index in range(288):
                    frame = av.VideoFrame.from_ndarray(np.full((64, 64, 3), index % 256, dtype=np.uint8), format="rgb24")
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            with patch.object(folder_paths, "get_input_directory", return_value=directory):
                self.assertIn(source, nodes._files(["video"]))
                self.assertEqual(probe.duration_seconds(source), 0)
                (item,) = nodes.NGContextVideo.execute(video=source, name="Move", description="A movement.", content="motion",
                                                     usage="motion", preserve="high", context_id="move",
                                                     context_options=json.dumps(opts.ContextOptions(start_s=6).to_dict())).args
                self.assertEqual(item.length_s, 0)
                ref = planned((item,), total=10).compiled[0].of_kind("video")[0]
                self.assertEqual((ref.trim_start_f, ref.length_f), (144, 120))
                self.assertEqual(tuple(media.load_video(ref).shape), (120, 64, 64, 3))

    def test_primary_voice_reference_repeats_its_whole_lane_window_in_every_touched_part(self):
        selected = opts.ContextOptions(start_s=3, end_s=5)
        result = planned((FIGURE, voice(selected)), shots=document(30, [clip(8, 14)]))
        for chunk, compiled in zip(result.plan.chunks, result.compiled):
            refs = compiled.of_kind("audio")
            lane = [ref for ref in refs if ref.trim_start_f == 24]
            touched = 8 * 24 < chunk.story_end_f and 14 * 24 > chunk.story_start_f - chunk.head_frames
            self.assertEqual([(ref.trim_start_f, ref.length_f) for ref in lane], [(24, 144)] if touched else [])
            self.assertEqual(len(refs), 2 if touched else 0)
            self.assertIn("<Audio 2>", compiled.prompt) if touched else self.assertNotIn("<Audio 2>", compiled.prompt)
        self.assertEqual(result.context.item("voice").options, selected)

    def test_shot_binding_already_has_selected_primary_voice_and_must_not_duplicate_it(self):
        binding = dict(schema_version=1, context_id="voice", role="voice")
        result = planned((FIGURE, voice(opts.ContextOptions(start_s=3, end_s=5))), total=10,
                         shots=document(10, bindings=[binding]))
        refs = result.compiled[0].of_kind("audio")
        self.assertEqual(len(refs), 1)
        self.assertEqual([(r.trim_start_f, r.length_f) for r in refs if r.trim_start_f], [(72, 48)])

    def test_unplaced_primary_voice_has_only_its_subject_slot(self):
        # only where its figure speaks: a voice sample sent to a part without a line was spoken anyway (GUI test 2026-10-25)
        silent = planned((FIGURE, voice()), shots=document(30))
        for compiled in silent.compiled:
            self.assertEqual(compiled.of_kind("audio"), ())
        talking = json.loads(document(30))
        talking["shots"][0]["spoken"] = [{"schema_version": 1, "text": "Hello.", "speaker_id": "figure"}]
        result = planned((FIGURE, voice()), shots=json.dumps(talking))
        self.assertEqual(len(result.compiled[0].of_kind("audio")), 1)
        for compiled in result.compiled:
            self.assertNotIn("<Audio 2>", compiled.prompt)

    def test_primary_voice_copy_and_lock_keep_absolute_file_offsets(self):
        for mode, kind in (("copy", "audio"), ("lock", "lock")):
            with self.subTest(mode=mode):
                result = planned((FIGURE, voice(opts.ContextOptions(start_s=3, end_s=5))), total=10,
                                 shots=document(10, [clip(1, 4, offset=1, mode=mode)]))
                actual = [r for r in result.compiled[0].of_kind(kind) if r.trim_start_f == 24]
                self.assertEqual([(r.start_f, r.trim_start_f, r.length_f) for r in actual], [(24, 24, 72)])

    def test_widgets_and_real_preview_accept_unknown_duration_with_positive_source_start(self):
        widgets = dict(video="duration_unknown.mkv", name="Move", context_id="move", content="motion", usage="motion",
                       preserve="high", context_options=json.dumps(opts.ContextOptions(start_s=6).to_dict()))
        item = build.item_from_widgets("video", widgets)
        result = planned((item,), total=10)
        self.assertEqual([(r.trim_start_f, r.length_f) for r in result.compiled[0].of_kind("video")], [(144, 120)])
        output = preview.plan_preview({"contexts": [{"media": "video", "widgets": widgets}],
                                      "director": {"idea": "A scene.", "mode": "ref2va"}})
        self.assertTrue(output["ok"], output)
        self.assertFalse(any("is 0.0s" in issue["text"] for issue in output["issues"]))

    def test_inverted_explicit_ranges_still_fail_at_the_public_schema(self):
        widgets = dict(video="move.mp4", name="Move", usage="motion", content="motion",
                       context_options=json.dumps(opts.ContextOptions(start_s=10, end_s=4).to_dict()))
        with self.assertRaisesRegex(ValueError, "Source end must be later"):
            build.item_from_widgets("video", widgets)
        output = preview.plan_preview({"contexts": [{"media": "video", "widgets": widgets}]})
        self.assertFalse(output["ok"])
        self.assertIn("Source end must be later", output["error"])

    def test_motion_known_duration_caps_the_requested_end_at_the_file_end(self):
        item = ctx.ContextItem("move", "Move", "video", "move.mp4", usage=("motion",), length_s=8,
                               options=opts.ContextOptions(start_s=3, end_s=11))
        ref = planned((item,), total=10).compiled[0].of_kind("video")[0]
        self.assertEqual((ref.trim_start_f, ref.length_f), (72, 120))

    def test_lock_coverage_matches_the_card_selection_even_without_probed_duration(self):
        for length in (0, 60):
            with self.subTest(length=length):
                sound = voice(opts.ContextOptions(start_s=2, end_s=7), length, role="lock", speaker="")
                result = planned((sound,), total=60)
                self.assertEqual(timing.locked_spans(result.context), [(0, 120)])
                self.assertIn("audio_dulling", {issue.code for issue in result.issues})
                for chunk, compiled in zip(result.plan.chunks, result.compiled):
                    refs = compiled.of_kind("lock")
                    base = chunk.story_start_f - chunk.head_frames
                    expected = max(0, min(chunk.story_end_f, 120) - base)
                    self.assertEqual([(r.trim_start_f, r.length_f) for r in refs], [(48 + base, expected)] if expected else [])

    def test_card_source_selection_beyond_file_end_emits_no_coverage(self):
        sound = voice(opts.ContextOptions(start_s=15), 10, role="lock", speaker="")
        result = planned((sound,), total=60)
        self.assertEqual(timing.locked_spans(result.context), [])
        self.assertTrue(all(not compiled.of_kind("lock") for compiled in result.compiled))
        self.assertIn("audio_dulling", {issue.code for issue in result.issues})

    def test_lock_lane_coverage_ignores_card_range_like_the_compiler_does(self):
        sound = voice(opts.ContextOptions(start_s=2, end_s=7), 60, role="lock", speaker="")
        result = planned((sound,), total=60, shots=document(60, [clip(0, 60, offset=0, mode="lock")]))
        self.assertEqual(timing.locked_spans(result.context), [(0, 1440)])
        self.assertNotIn("audio_dulling", {issue.code for issue in result.issues})
        for chunk, compiled in zip(result.plan.chunks, result.compiled):
            ref = compiled.of_kind("lock")[0]
            self.assertEqual(ref.trim_start_f, chunk.story_start_f - chunk.head_frames)


if __name__ == "__main__":
    unittest.main(verbosity=2)
