r"""Regression test for BUG-085: lyrics._spans ignores item.options.end_s and length_s, injecting ghost singing lines into unbacked silent chunks.

Where:
- ng/core/lyrics.py:126-138 (`_spans`)
- ng/core/lyrics.py:151-165 (`story_lines`)
- ng/core/lyrics.py:168-175 (`sung_lines`)
- ng/core/legacy_bridge.py:252-265 (`_add_sung_lines`)

Contrast with:
- ng/core/lyrics.py:127:
  def _spans(context, item):
      \"\"\"(story start f, story end f, file frame at story start) where this card plays its own signal.\"\"\"
- ng/core/audio_timing.py:8-11 (`source_window`):
  def source_window(item):
      start = seconds_to_frames(item.options.start_s)
      ends = [value for value in (item.options.end_s, item.length_s) if value > 0]
      return start, max(0, seconds_to_frames(min(ends)) - start) if ends else None
- ng/core/audio_timing.py:128-129 (`timed_segments`):
  first = max(origin, window_start)
  last = min(end, chunk.story_end_f, origin + available - offset if available is not None else end)
- ng/core/audio_timing.py:49-60 (`locked_spans` in BUG-083)

User workflow:
1. In ComfyUI Director Studio or via Context cards, the user creates a multi-chunk video project
   (e.g. 20s with 10s chunks = 2 chunks, or 60s with 10s chunks = 6 chunks).
2. The user adds an Audio card with a song (`lyrics` filled with timestamped LRC lines, `usage=('lock',)`).
3. The user wants the song to play only during the intro (first 5 seconds, e.g. `start_s = 0.0, end_s = 5.0`),
   or the audio file itself is physically only 5 seconds long (`length_s = 5.0`).
4. Downstream, `audio_timing.timed_segments` uses `source_window` and places audio only in Chunk 1 (frames 0..120).
   Chunks 2..N receive zero lock references (`compiled.of_kind('lock') == []`).
5. The user plans the project (`plan_project`).

What happens (Ist):
1. In `ng/core/lyrics.py:137`:
   ```python
   return [(0, seconds_to_frames(context.project_seconds), source)]
   ```
   `_spans` completely ignores `item.options.end_s` and `item.length_s`!
   It returns `[(0, 480, 0)]` for the whole 20s project (or `[(0, 1440, 0)]` for 60s).
2. In `lyrics.py:151-165`, `story_lines` evaluates every line in the LRC against `end = 480` (or `1440`).
   Lyric lines that occur after the song has finished playing (e.g. at 12.0s) are included in `story_lines`.
3. In `lyrics.py:168-175`, `sung_lines(context, chunk2)` returns these lines for Chunk 2.
4. In `legacy_bridge.py:252-265`, `_add_sung_lines` injects:
   `[Shot 1] the singer (S1) sings, <d>[English] Ghost verse in chunk 2</d>`
   into `compiled.prompt` of Chunk 2!
5. Chunk 2 has zero audio tracks (`compiled.of_kind('lock') == []`), but its prompt explicitly orders the model
   to generate singing and lip-syncing over dead silence.
6. Furthermore, for a lyric line that starts before `end_s` and ends after `end_s` (e.g. start=2.0s, end=8.0s when `end_s=5.0`),
   `StoryLine.end_f` is clamped to `min(end, origin + seconds_to_frames(line.end) - offset)`. Because `end` is 480,
   `end_f` extends to 192 frames (8.0s) instead of being bounded by the audio cutoff at 120 frames (5.0s).

What should happen (Soll):
1. `_spans` must respect `item.options.end_s` and `item.length_s` (via `source_window` or available frames `max(0, min(ends) - start)`),
   bounding the span to the actual audio duration `min(project_frames, available)`.
2. For an audio card trimmed to `end_s = 5.0` (or `length_s = 5.0`), `_spans` must return `[(0, 120, 0)]`,
   not the full project duration `[(0, 480, 0)]`.
3. `story_lines` must not emit lines that occur after the audio signal has ended.
4. Chunks where the audio is no longer playing (such as Chunk 2) must receive `sung_lines = []`
   and must not contain `<d>... lyrics ...</d>` singing instructions in `compiled.prompt`.
5. Lines that overlap `end_s` must have `end_f` clamped to the audio cut-off `min(end, origin + available)`.

Run:
    D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe -B tests/ng/regressions/bug_085_lyrics_spans_ignores_end_s_and_file_length.py
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

lyrics = module("ng.core.lyrics")
project = module("ng.core.project")
context_mod = module("ng.core.context")
options_mod = module("ng.core.context_options")
chunks_mod = module("ng.core.chunks")

CONTINUITY = chunks_mod.ContinuityPlan("video_audio", 22, 24)


class LyricsSpansIgnoresEndSAndLengthSTests(unittest.TestCase):
    # -------------------------------------------------------------------------
    # Green Controls: Expected behavior that must always pass on unmodified code
    # -------------------------------------------------------------------------

    def test_green_control_full_song_covering_project_includes_all_lines(self):
        """When an audio card covers the whole project duration without trim, lyrics are placed in chunks."""
        lrc = "[00:01.00] Intro verse\n[00:12.00] Second verse"
        audio = context_mod.ContextItem(
            id="song1", name="Song", media="audio", source="song.mp3",
            usage=("lock",),
            options=options_mod.ContextOptions(lyrics=lrc),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=20.0)
        plan = project.plan_project(ctx, 10.0, CONTINUITY)

        self.assertIn("Intro verse", plan.compiled[0].prompt)
        self.assertIn("Second verse", plan.compiled[1].prompt)
        self.assertEqual(len(plan.compiled[0].of_kind("lock")), 1)
        self.assertEqual(len(plan.compiled[1].of_kind("lock")), 1)

    def test_green_control_lyrics_within_trimmed_interval_present_in_chunk_1(self):
        """Lyrics that are genuinely within the trimmed interval are properly included in Chunk 1."""
        lrc = "[00:01.00] Intro line\n[00:03.00] Still in intro"
        audio = context_mod.ContextItem(
            id="song1", name="Song", media="audio", source="song.mp3",
            usage=("lock",),
            options=options_mod.ContextOptions(start_s=0.0, end_s=5.0, lyrics=lrc),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=20.0)
        plan = project.plan_project(ctx, 10.0, CONTINUITY)

        self.assertIn("Intro line", plan.compiled[0].prompt)
        self.assertIn("Still in intro", plan.compiled[0].prompt)

    def test_green_control_audio_lane_clip_limits_lyrics_span(self):
        """When an audio card is placed on an audio lane with a specific clip range, clip_windows limits the span."""
        audio = context_mod.ContextItem(
            id="song1", name="Song", media="audio", source="song.mp3",
            usage=("voice",),
            options=options_mod.ContextOptions(lyrics="[00:01.00] Line one\n[00:08.00] Line two"),
            length_s=60.0
        )
        # Create project with lane clip from 0 to 5s
        shots_doc = (
            '{"format":"h3-director-shots","schema_version":1,"shots":['
            '{"id":"s1","start":0,"end":20,"text":"Action.","media":[],"spoken":[],"locked_fields":[],"draft":null}],'
            '"audio":[{"schema_version":1,"id":"c1","context_id":"song1","start":0.0,"end":5.0,"offset":0.0,"mode":"lock","lane":"l1"}]}'
        )
        ctx = context_mod.DirectorContext(items=(audio,), shots_text=shots_doc, project_seconds=20.0)
        spans = lyrics._spans(ctx, audio)
        self.assertEqual(spans, [(0, 120, 0)], "clip_windows must properly restrict the lane span to 120 frames")

    # -------------------------------------------------------------------------
    # Red Defect Tests: Failing on unmodified code due to BUG-085
    # -------------------------------------------------------------------------

    def test_red_defect_spans_must_respect_end_s(self):
        """BUG-085: _spans returns [(0, total, source)] ignoring end_s.
        For a 20s project (480 frames) with end_s=5.0 (120 frames), _spans must return [(0, 120, 0)], not [(0, 480, 0)].
        """
        audio = context_mod.ContextItem(
            id="song1", name="Song", media="audio", source="song.mp3",
            usage=("lock",),
            options=options_mod.ContextOptions(start_s=0.0, end_s=5.0),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=20.0)
        spans = lyrics._spans(ctx, audio)

        self.assertEqual(spans, [(0, 120, 0)],
                         "_spans must respect item.options.end_s and limit audio coverage to 120 frames (5.0s)")

    def test_red_defect_spans_must_respect_length_s(self):
        """BUG-085: _spans returns [(0, total, source)] ignoring length_s.
        When an untrimmed audio file is only 5.0s long (120 frames) in a 20s project,
        _spans must return [(0, 120, 0)], not [(0, 480, 0)].
        """
        audio = context_mod.ContextItem(
            id="song1", name="ShortSong", media="audio", source="short.mp3",
            usage=("lock",),
            options=options_mod.ContextOptions(),
            length_s=5.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=20.0)
        spans = lyrics._spans(ctx, audio)

        self.assertEqual(spans, [(0, 120, 0)],
                         "_spans must respect item.length_s and limit audio coverage to the file's 120 frames")

    def test_red_defect_no_ghost_lyrics_in_unbacked_chunk_prompt(self):
        """BUG-085: When a locked song is trimmed to 5.0s in a 20s project (2x 10s chunks),
        Chunk 2 has no locked audio (of_kind('lock') == []).
        lyrics._spans must not cause Chunk 2's prompt to contain ghost singing instructions (<d>...</d>).
        """
        lrc = "[00:01.00] Intro line\n[00:12.00] Ghost line in chunk 2"
        audio = context_mod.ContextItem(
            id="song1", name="Song", media="audio", source="song.mp3",
            usage=("lock",),
            options=options_mod.ContextOptions(start_s=0.0, end_s=5.0, lyrics=lrc),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=20.0)
        plan = project.plan_project(ctx, 10.0, CONTINUITY)

        # Chunk 2 has zero audio locks
        self.assertEqual(len(plan.compiled[1].of_kind("lock")), 0,
                         "Chunk 2 has no locked audio track")
        # Chunk 2 prompt must NOT command the model to sing a ghost line over silence
        self.assertNotIn("Ghost line in chunk 2", plan.compiled[1].prompt,
                         "Chunk 2 prompt must not contain ghost singing line when audio stopped at 5.0s")

    def test_red_defect_story_line_end_f_clamped_to_audio_end(self):
        """BUG-085: When a lyric line starts at 2.0s (48 frames) and ends at 8.0s (192 frames),
        but the audio card is trimmed to end_s = 5.0s (120 frames),
        StoryLine.end_f must be clamped to the audio cut-off (120 frames), not extend into silence.
        """
        lrc = "[00:02.00] Boundary crossing line\n[00:08.00]"
        audio = context_mod.ContextItem(
            id="song1", name="Song", media="audio", source="song.mp3",
            usage=("lock",),
            options=options_mod.ContextOptions(start_s=0.0, end_s=5.0, lyrics=lrc),
            length_s=60.0
        )
        ctx = context_mod.DirectorContext(items=(audio,), project_seconds=20.0)
        lines = lyrics.story_lines(ctx)

        self.assertEqual(len(lines), 1)
        self.assertLessEqual(lines[0].end_f, 120,
                             "Lyric line end_f must be clamped to audio boundary (120 frames), not extend to 192")


if __name__ == "__main__":
    unittest.main()
