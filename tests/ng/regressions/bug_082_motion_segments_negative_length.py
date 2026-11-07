r"""Regression test for BUG-082: _motion_segments computes negative clip length when start_s > 0 on unprobed video.

Where:
- ng/core/legacy_bridge.py:206-214 (_motion_segments)

Contrast with audio_timing / compile:
- ng/core/audio_timing.py:8-11:
  def source_window(item):
      start = seconds_to_frames(item.options.start_s)
      ends = [value for value in (item.options.end_s, item.length_s) if value > 0]
      return start, max(0, seconds_to_frames(min(ends)) - start) if ends else None
  And legacy_bridge.py:201 sets: "length": available if available is not None else 48
  (When ends is empty, available is None, using 48 frames as a fixed fallback duration without subtracting start).

User workflow:
1. In ComfyUI Director Studio or via Context cards, the user adds a Video card (e.g. 'Dance', dance.mp4)
   with usage=("motion",).
2. The user wants to use a motion segment starting at second 6 (to skip an intro), so they set
   start_s = 6.0 on the card options.
3. The user leaves end_s = 0.0 (the default meaning play until end of video / no end cap).
4. The card is unprobed (length_s == 0.0, which is standard when length probe hasn't run or is unprobed).
5. The user plans the project or triggers Director/Preview.

What happens (Ist):
In `ng/core/legacy_bridge.py:210`:
```python
length = int(round(((item.options.end_s or item.length_s or 5.0) - item.options.start_s) * 24))
```
1. `(item.options.end_s or item.length_s or 5.0)` treats 5.0 as an absolute end timestamp instead of a fallback duration.
2. When end_s == 0.0 and length_s == 0.0, it falls back to 5.0, and then subtracts start_s (6.0):
   5.0 - 6.0 = -1.0 seconds (-24 frames).
3. `_motion_segments` emits:
   `{'type': 'video', 'videoFile': 'dance.mp4', 'fileName': 'Dance', 'length': -24, 'trimStart': 144, ...}`.
4. In `minimax_plan.py:1550`:
   `seconds = max(0.0, float(seg.get("length", 0)) / fps)` clamps -24 to 0.0s, and emits the spurious issue:
   `Issue("planner", "Reference video 'Dance' is 0.0s; H3 wants 2-15s per clip.")`.
5. In `ng/core/compile.py:75`:
   `MediaRef` gets `length_f = -24` (negative frame length).
6. Downstream in `ng/adapters/media.py:26`:
   `seconds = min(15.0, (ref.length_f or 360) / 24.0)` evaluates to -1.0s, passing negative duration to
   video decoders, resulting in MediaError.
7. Similarly, if a user sets inverted bounds (e.g. start_s = 10.0, end_s = 4.0), the absence of `max(0, ...)`
   evaluates to -144 frames.

What should happen (Soll):
1. When neither `end_s` nor `length_s` is specified (> 0), the fallback duration 5.0s (120 frames at 24 fps)
   must be used as the clip duration, rather than an absolute end timestamp from which start_s is subtracted.
2. When an end bound is provided, `length = max(0, int(round((end - start_s) * 24)))`.
3. Under no circumstances may `_motion_segments` produce negative `length` or negative `length_f`.

Run:
    D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe -B tests/ng/regressions/bug_082_motion_segments_negative_length.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NG_TESTS = os.path.dirname(HERE)
if NG_TESTS not in sys.path:
    sys.path.insert(0, NG_TESTS)

from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()

context_mod = module("ng.core.context")
context_options = module("ng.core.context_options")
legacy_bridge = module("ng.core.legacy_bridge")
project_mod = module("ng.core.project")
chunks_mod = module("ng.core.chunks")

VIDEO_PLAN = chunks_mod.ContinuityPlan("video_audio", 22, 24)


class MotionSegmentsNegativeLengthTests(unittest.TestCase):
    def test_green_control_known_duration_with_start_s(self):
        """When length_s is known (30s) and start_s=6.0, length is positive 576 frames (24s)."""
        video = context_mod.ContextItem(
            id="vid_known", name="Dance", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(start_s=6.0, end_s=0.0),
            length_s=30.0
        )
        ctx = context_mod.DirectorContext(idea="A dance scene.", items=(video,))
        segs = legacy_bridge._motion_segments(ctx)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["length"], 576)
        self.assertEqual(segs[0]["trimStart"], 144)

    def test_green_control_explicit_end_greater_than_start(self):
        """When start_s=2.0 and end_s=7.0, length is positive 120 frames (5s)."""
        video = context_mod.ContextItem(
            id="vid_explicit", name="Dance", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(start_s=2.0, end_s=7.0),
            length_s=0.0
        )
        ctx = context_mod.DirectorContext(idea="A dance scene.", items=(video,))
        segs = legacy_bridge._motion_segments(ctx)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["length"], 120)
        self.assertEqual(segs[0]["trimStart"], 48)

    def test_green_control_start_zero_unprobed(self):
        """When start_s=0.0, end_s=0.0, length_s=0.0, length is positive 120 frames (5s fallback)."""
        video = context_mod.ContextItem(
            id="vid_zero", name="Dance", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(start_s=0.0, end_s=0.0),
            length_s=0.0
        )
        ctx = context_mod.DirectorContext(idea="A dance scene.", items=(video,))
        segs = legacy_bridge._motion_segments(ctx)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["length"], 120)

    def test_red_defect_motion_segment_length_must_not_be_negative_when_start_s_exceeds_fallback(self):
        """BUG-082: When start_s=6.0 on unprobed video (end_s=0.0, length_s=0.0), length must not be negative.

        Ist: length = ((0 or 0 or 5.0) - 6.0) * 24 = -24.
        Soll: length must be a valid non-negative frame count (e.g. 120 frames default duration).
        """
        video = context_mod.ContextItem(
            id="vid_unprobed", name="Dance", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(start_s=6.0, end_s=0.0),
            length_s=0.0
        )
        ctx = context_mod.DirectorContext(idea="A dance scene.", items=(video,))
        segs = legacy_bridge._motion_segments(ctx)
        self.assertEqual(len(segs), 1)
        self.assertGreater(segs[0]["length"], 0,
                           "Motion segment length must be positive, not %d" % segs[0]["length"])

    def test_red_defect_compiled_media_ref_must_not_have_negative_length_f(self):
        """BUG-082: Compiled MediaRef for video with start_s=6.0 must not have negative length_f.

        Ist: MediaRef has length_f = -24.
        Soll: length_f must be > 0.
        """
        video = context_mod.ContextItem(
            id="vid_unprobed", name="Dance", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(start_s=6.0, end_s=0.0),
            length_s=0.0
        )
        ctx = context_mod.DirectorContext(idea="A dance scene.", items=(video,))
        plan = project_mod.plan_project(ctx, 5, VIDEO_PLAN)
        jobs = project_mod.jobs(plan)
        video_refs = jobs[0].compiled.of_kind("video")
        self.assertEqual(len(video_refs), 1)
        self.assertGreater(video_refs[0].length_f, 0,
                           "Compiled MediaRef.length_f must be positive, not %d" % video_refs[0].length_f)

    def test_red_defect_inverted_range_must_not_produce_negative_length(self):
        """BUG-082: Inverted bounds (start_s=10.0, end_s=4.0) must not produce negative frame length.

        Ist: length = ((4.0) - 10.0) * 24 = -144 frames.
        Soll: length must be clamped to at least 0 (not negative).
        """
        video = context_mod.ContextItem(
            id="vid_inverted", name="Dance", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(start_s=10.0, end_s=4.0),
            length_s=20.0
        )
        ctx = context_mod.DirectorContext(idea="A dance scene.", items=(video,))
        segs = legacy_bridge._motion_segments(ctx)
        self.assertEqual(len(segs), 1)
        self.assertGreaterEqual(segs[0]["length"], 0,
                                "Motion segment length must not be negative, got %d" % segs[0]["length"])

    def test_red_defect_no_spurious_zero_seconds_warning_for_valid_video(self):
        """BUG-082: A valid video with start_s=6.0 must not trigger 'Reference video is 0.0s'.

        Ist: minimax_plan.py clamps -24 to 0.0s and emits 'Reference video 'Dance' is 0.0s; H3 wants 2-15s per clip.'
        Soll: No false 'is 0.0s' warning should be emitted.
        """
        video = context_mod.ContextItem(
            id="vid_unprobed", name="Dance", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(start_s=6.0, end_s=0.0),
            length_s=0.0
        )
        ctx = context_mod.DirectorContext(idea="A dance scene.", items=(video,))
        plan = project_mod.plan_project(ctx, 5, VIDEO_PLAN)
        issues = [str(i.text) for i in plan.issues]
        has_zero_sec = any("is 0.0s" in t for t in issues)
        self.assertFalse(has_zero_sec,
                         "Plan must not emit false 'is 0.0s' warning for video starting at 6.0s; issues: %r" % issues)


if __name__ == "__main__":
    unittest.main()
