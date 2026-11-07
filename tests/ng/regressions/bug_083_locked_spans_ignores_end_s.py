r"""Regression test for BUG-083: locked_spans ignores item.options.end_s, falsely suppressing audio_dulling and producing inverted spans.

Where:
- ng/core/audio_timing.py:49-60 (`locked_spans`)
- ng/core/project.py:150-154 (`plan_project` audio_dulling suppression)

Contrast with:
- ng/core/audio_timing.py:8-11 (`source_window`):
  def source_window(item):
      start = seconds_to_frames(item.options.start_s)
      ends = [value for value in (item.options.end_s, item.length_s) if value > 0]
      return start, max(0, seconds_to_frames(min(ends)) - start) if ends else None
- ng/core/audio_timing.py:32-46 (`clip_windows`):
  start, end = seconds_to_frames(clip.start), min(seconds_to_frames(clip.end), total)
  if end <= start: continue

User workflow:
1. In ComfyUI Director Studio or via Context cards, the user creates a multi-chunk video project
   (e.g. 60 seconds with 10s chunks = 6 chunks, 5 joins > AUDIO_DULLING_JOINS=4) with continuity 'video_audio'.
2. The user adds an Audio card (e.g. 'Theme', theme.mp3, length_s=60.0) with usage=('lock',).
3. The user wants the audio to play only during the intro (first 5 seconds), so they set end_s = 5.0
   (or start_s = 0.0, end_s = 5.0) on the card options.
4. Downstream, `timed_segments` uses `source_window` and places audio only in Chunk 1 (frames 0..120).
   Chunks 2, 3, 4, 5, and 6 receive zero lock references (`compiled.of_kind('lock') == []`).
5. Because chunks 2..6 form a 50-second unbacked audio chain across 5 joins, the audio loses high
   frequencies across chunk boundaries (`Issue('audio_dulling', ...)`).
6. The user plans the project or triggers Director/Preview.

What happens (Ist):
1. In `ng/core/audio_timing.py:58`:
   ```python
   last = seconds_to_frames(item.length_s - item.options.start_s) if item.length_s > 0 else total
   spans += [(start, min(end, start + last)) for start, end, _ in bound.get(item.id, [(0, total, 0)])]
   ```
   `locked_spans` completely ignores `item.options.end_s`!
2. `last` is computed as `60.0 - 0.0 = 60.0s = 1440 frames`.
3. `locked_spans(ctx)` returns `[(0, 1440)]`, claiming that the locked audio covers all 60 seconds.
4. `covers(locked_spans(ctx), plan.total_frames, limits.FPS)` evaluates to True.
5. In `ng/core/project.py:153`:
   `plan = replace(plan, issues=tuple(i for i in plan.issues if i.code != "audio_dulling"))`
   strips the `audio_dulling` issue from `plan.issues`!
6. The user is never warned about audio dulling, despite chunks 2..6 having no locked audio.
7. Furthermore, when `item.options.start_s > item.length_s` (e.g. start_s=15.0 on a 10.0s file),
   `last` is negative (-120 frames), producing an inverted span `[(0, -120)]` where `end < start`.

What should happen (Soll):
1. `locked_spans` must respect `item.options.end_s` (via `source_window` or `min(ends) - start_s`),
   restricting the span to the actual audio duration `max(0, min(ends) - start)`.
2. For an audio card trimmed to `end_s=5.0`, `locked_spans` must span at most 120 frames (5.0s),
   not 1440 frames (60.0s).
3. `covers` must return False for the 60s project, and `plan.issues` must retain `audio_dulling`.
4. When `start_s > length_s`, `locked_spans` must clamp length to >= 0 and never produce inverted spans (`end < start`).

Run:
    D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe -B tests/ng/regressions/bug_083_locked_spans_ignores_end_s.py
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
audio_timing = module("ng.core.audio_timing")
project_mod = module("ng.core.project")
chunks_mod = module("ng.core.chunks")

CONTINUITY = chunks_mod.ContinuityPlan("video_audio", 22, 24)


class LockedSpansIgnoresEndSTests(unittest.TestCase):
    # -------------------------------------------------------------------------
    # Green Controls: Expected behavior that must always pass
    # -------------------------------------------------------------------------

    def test_green_control_full_audio_covers_project_and_clears_dulling(self):
        """When a locked audio card has length_s=60.0 and no trim (end_s=0.0), it covers the 60s project."""
        audio = context_mod.ContextItem(
            id="audio_full", name="Theme", media="audio", source="theme.mp3",
            usage=("lock",), options=context_options.ContextOptions(start_s=0.0, end_s=0.0),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=60.0)
        spans = audio_timing.locked_spans(ctx)
        self.assertEqual(spans, [(0, 1440)])
        self.assertTrue(audio_timing.covers(spans, 1440, 24))

        plan = project_mod.plan_project(ctx, 10.0, CONTINUITY)
        self.assertNotIn("audio_dulling", [i.code for i in plan.issues],
                         "audio_dulling must be cleared when audio genuinely covers the whole video")

    def test_green_control_unprobed_audio_uses_total_fallback(self):
        """When length_s=0.0 and end_s=0.0, fallback total frames (1440) is used."""
        audio = context_mod.ContextItem(
            id="audio_unprobed", name="Theme", media="audio", source="theme.mp3",
            usage=("lock",), options=context_options.ContextOptions(start_s=0.0, end_s=0.0),
            length_s=0.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=60.0)
        spans = audio_timing.locked_spans(ctx)
        self.assertEqual(spans, [(0, 1440)])

    def test_green_control_empty_audio_retains_audio_dulling(self):
        """When no audio is present in a 60s 6-chunk project, audio_dulling issue is present."""
        ctx = context_mod.DirectorContext(items=(), project_seconds=60.0)
        plan = project_mod.plan_project(ctx, 10.0, CONTINUITY)
        self.assertIn("audio_dulling", [i.code for i in plan.issues])

    def test_green_control_audio_lane_clip_respects_end_time(self):
        """An audio lane clip ending at 5.0s has clip_windows ending at 120 frames, not covering 60s."""
        import json
        shots_doc = json.dumps({
            "format": "h3-director-shots", "schema_version": 1,
            "shots": [{"id": "s1", "start": 0.0, "end": 60.0, "text": "The scene continues.", "media": [], "spoken": []}],
            "audio": [{"schema_version": 1, "id": "c1", "context_id": "theme", "start": 0.0, "end": 5.0, "offset": 0.0, "mode": "lock", "lane": "l1"}]
        })
        audio = context_mod.ContextItem(
            id="theme", name="Theme", media="audio", source="theme.mp3",
            usage=("lock",), length_s=60.0
        )
        ctx = context_mod.DirectorContext(shots_text=shots_doc, items=(audio,), project_seconds=60.0)
        spans = audio_timing.locked_spans(ctx)
        self.assertEqual(spans, [(0, 120)])
        self.assertFalse(audio_timing.covers(spans, 1440, 24))
        plan = project_mod.plan_project(ctx, 10.0, CONTINUITY)
        self.assertIn("audio_dulling", [i.code for i in plan.issues])

    # -------------------------------------------------------------------------
    # Red Defect Tests: Reproduce BUG-083 defect on unmodified codebase
    # -------------------------------------------------------------------------

    def test_red_defect_locked_spans_must_respect_end_s(self):
        """BUG-083: Audio card with end_s=5.0 on a 60.0s file must yield locked_spans ending at 120 frames, not 1440.

        Ist: locked_spans computes last = seconds_to_frames(60.0 - 0.0) = 1440, returning [(0, 1440)].
        Soll: locked_spans must take end_s into account, returning [(0, 120)].
        """
        audio = context_mod.ContextItem(
            id="audio_trimmed", name="Theme", media="audio", source="theme.mp3",
            usage=("lock",), options=context_options.ContextOptions(start_s=0.0, end_s=5.0),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=60.0)
        spans = audio_timing.locked_spans(ctx)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0], (0, 120),
                         "locked_spans must end at 120 frames (5.0s), but got %r because end_s was ignored" % (spans,))

    def test_red_defect_audio_dulling_must_not_be_suppressed_when_locked_audio_trimmed(self):
        """BUG-083: Multi-chunk project (60s, 6 chunks) where audio is trimmed to end_s=5.0 must NOT suppress audio_dulling.

        Ist: covers(locked_spans(ctx), 1440, 24) returns True because locked_spans ignored end_s.
             project.py:153 strips 'audio_dulling' from plan.issues, hiding the audio degradation warning.
        Soll: covers must return False, and plan.issues must contain 'audio_dulling'.
        """
        audio = context_mod.ContextItem(
            id="audio_trimmed", name="Theme", media="audio", source="theme.mp3",
            usage=("lock",), options=context_options.ContextOptions(start_s=0.0, end_s=5.0),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=60.0)
        plan = project_mod.plan_project(ctx, 10.0, CONTINUITY)

        # Confirm that chunks 2..6 actually have no lock audio
        jobs = project_mod.jobs(plan)
        self.assertEqual(len(jobs[0].compiled.of_kind("lock")), 1, "Chunk 1 has lock audio")
        for chunk_idx in range(1, len(jobs)):
            self.assertEqual(len(jobs[chunk_idx].compiled.of_kind("lock")), 0,
                             "Chunk %d must have no lock audio" % (chunk_idx + 1))

        issue_codes = [i.code for i in plan.issues]
        self.assertIn("audio_dulling", issue_codes,
                      "audio_dulling must NOT be suppressed when locked audio ends at 5s in a 60s video; got issues: %r"
                      % issue_codes)

    def test_red_defect_locked_spans_with_start_and_end_range(self):
        """BUG-083: Audio card with start_s=2.0 and end_s=7.0 (duration 5.0s = 120f) on 60.0s file.

        Ist: locked_spans computes last = 60.0 - 2.0 = 58.0s = 1392 frames, returning [(0, 1392)].
        Soll: locked_spans must span at most 120 frames (5.0s available sound duration).
        """
        audio = context_mod.ContextItem(
            id="audio_range", name="Theme", media="audio", source="theme.mp3",
            usage=("lock",), options=context_options.ContextOptions(start_s=2.0, end_s=7.0),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=60.0)
        spans = audio_timing.locked_spans(ctx)
        self.assertEqual(len(spans), 1)
        span_length = spans[0][1] - spans[0][0]
        self.assertEqual(span_length, 120,
                         "locked_spans length must be 120 frames (7.0s - 2.0s), but got %d (span %r)"
                         % (span_length, spans[0]))

    def test_red_defect_start_s_exceeding_length_s_must_not_produce_inverted_span(self):
        """BUG-083: start_s=15.0 on 10.0s audio file must not produce an inverted span (end < start).

        Ist: last = seconds_to_frames(10.0 - 15.0) = -120, producing span (0, -120).
        Soll: duration must be clamped to >= 0, producing no span or a non-negative span where end >= start.
        """
        audio = context_mod.ContextItem(
            id="audio_overflow", name="Theme", media="audio", source="theme.mp3",
            usage=("lock",), options=context_options.ContextOptions(start_s=15.0, end_s=0.0),
            length_s=10.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=30.0)
        spans = audio_timing.locked_spans(ctx)
        for start, end in spans:
            self.assertGreaterEqual(end, start,
                                    "locked_spans must not have inverted end < start, got span (%d, %d)" % (start, end))


if __name__ == "__main__":
    unittest.main()
