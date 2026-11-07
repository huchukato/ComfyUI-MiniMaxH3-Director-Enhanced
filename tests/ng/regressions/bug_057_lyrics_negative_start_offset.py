"""BUG-057 Regression Test: lyrics.story_lines unclamped start frame with audio offset.

When an audio card or lane clip has an offset (e.g. start_s > 0 or clip offset > 0)
and a lyric line begins before the offset, story_lines computes:
    start = origin + seconds_to_frames(line.start) - offset
Because end_f is clamped with min(end, ...) but start_f is not clamped with max(origin, ...),
start_f becomes negative (or starts before the clip origin).
This causes:
1. StoryLine.start_f < 0 (negative story frame)
2. timing_hints returns negative seconds (e.g. -2.5 s)
3. split_prompt injects invalid negative timestamp ranges (e.g. '-2.5-3.5 s "lyrics"')
   into the AI prompt rules, violating the '0 to N s' video timeline instructions.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

lyrics = module("ng.core.lyrics")
context_build = module("ng.core.context_build")
context_mod = module("ng.core.context")
auto_direct = module("ng.core.auto_direct")


class LyricsNegativeStartOffset(unittest.TestCase):
    def test_bug_057_story_lines_must_not_produce_negative_start_frame(self):
        """A song starting with offset=2.5s must not yield negative start_f for a line starting at 0.0s."""
        opt = {
            "schema_version": 1,
            "start_s": 2.5,
            "lyrics": "[00:00.00] In the dark of the night\n[00:06.00] We saw the fire",
        }
        item = context_build.item_from_widgets(
            "audio",
            {
                "name": "Song",
                "context_id": "audio_song",
                "usage": "lock",
                "audio": "song.wav",
                "context_options": json.dumps(opt),
            },
        )
        ctx = context_mod.DirectorContext(idea="A scene", project_seconds=10.0, items=(item,))
        lines = lyrics.story_lines(ctx)
        self.assertTrue(len(lines) > 0, "story_lines must return the song lines")
        # Under buggy code: lines[0].start_f is -60 (-2.5s * 24fps)
        self.assertGreaterEqual(
            lines[0].start_f,
            0,
            "start_f must be clamped to the story origin (>= 0) and never be negative",
        )

    def test_bug_057_story_lines_must_not_precede_clip_origin_when_clip_starts_after_zero(self):
        """When an audio clip starts at 2.0s with file offset 4.0s, a line at file 3.0s must not start before 2.0s."""
        # 10s project, audio lane clip at start=2.0s, end=8.0s, offset=4.0s
        shots_doc = {
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 10, "text": "Action", "media": [], "spoken": [], "locked_fields": [], "draft": None}],
            "audio": [
                {
                    "id": "clip1",
                    "lane": "lane1",
                    "context_id": "audio_song",
                    "start": 2.0,
                    "end": 8.0,
                    "offset": 4.0,
                    "mode": "lock",
                    "schema_version": 1,
                }
            ],
            "audio_lanes": ["lane1"],
        }
        opt = {
            "schema_version": 1,
            "lyrics": "[00:03.00] Mid-song melody line\n[00:07.00] Ending melody",
        }
        item = context_build.item_from_widgets(
            "audio",
            {
                "name": "Song",
                "context_id": "audio_song",
                "usage": "lock",
                "audio": "song.wav",
                "context_options": json.dumps(opt),
            },
        )
        ctx = context_mod.DirectorContext(idea="A scene", project_seconds=10.0, shots_text=json.dumps(shots_doc), items=(item,))
        lines = lyrics.story_lines(ctx)
        self.assertTrue(len(lines) > 0, "story_lines must find the clip's lines")
        # origin is frame 48 (2.0s). Line starts at file second 3.0s (offset 4.0s -> file second -1.0s relative to clip).
        # Buggy code: start_f = 48 + 72 - 96 = 24 frames (1.0s), which precedes origin (48 frames / 2.0s).
        self.assertGreaterEqual(
            lines[0].start_f,
            48,
            "start_f must be clamped to the clip origin (48 frames = 2.0s) and not precede clip start",
        )

    def test_bug_057_auto_direct_prompt_must_not_contain_negative_timestamp_ranges(self):
        """timing_hints and direction_prompt must not format negative timestamps like '-2.5-3.5 s'."""
        opt = {
            "schema_version": 1,
            "start_s": 2.5,
            "lyrics": "[00:00.00] In the dark of the night\n[00:06.00] We saw the fire",
        }
        contexts = [
            {
                "media": "audio",
                "widgets": {
                    "name": "Song",
                    "context_id": "audio_song",
                    "usage": "lock",
                    "audio": "song.wav",
                    "context_options": json.dumps(opt),
                },
            }
        ]
        hints = auto_direct.timing_hints({"shots": "", "continuity": "none"}, contexts)
        self.assertTrue(len(hints[1]) > 0, "timing_hints must include sung lines")
        # Buggy code produces hints[1][0] = (-2.5, 3.5, 'Song', 'In the dark of the night')
        self.assertGreaterEqual(
            hints[1][0][0],
            0.0,
            "The start time of sung lines in timing_hints must not be negative",
        )
        prompt = auto_direct.direction_prompt("A scene", 10.0, contexts, timing=hints)
        self.assertNotIn(
            "-2.5",
            prompt,
            "direction_prompt must not present negative timestamps to the AI prompt",
        )

    def test_green_control_untrimmed_lyrics_have_zero_start_time(self):
        """Green control: without offset, start_f is exactly 0 and prompt shows 0-N s."""
        opt = {
            "schema_version": 1,
            "start_s": 0.0,
            "lyrics": "[00:00.00] In the dark of the night\n[00:06.00] We saw the fire",
        }
        item = context_build.item_from_widgets(
            "audio",
            {
                "name": "Song",
                "context_id": "audio_song",
                "usage": "lock",
                "audio": "song.wav",
                "context_options": json.dumps(opt),
            },
        )
        ctx = context_mod.DirectorContext(idea="A scene", project_seconds=10.0, items=(item,))
        lines = lyrics.story_lines(ctx)
        self.assertEqual(lines[0].start_f, 0)
        hints = auto_direct.timing_hints(
            {"shots": "", "continuity": "none"},
            [{"media": "audio", "widgets": {"name": "Song", "context_id": "audio_song", "usage": "lock", "audio": "song.wav", "context_options": json.dumps(opt)}}],
        )
        self.assertEqual(hints[1][0][0], 0.0)

    def test_green_control_lines_starting_after_offset_are_strictly_positive(self):
        """Green control: lines starting after the offset naturally have start_f > origin."""
        opt = {
            "schema_version": 1,
            "start_s": 2.0,
            "lyrics": "[00:04.00] Verse begins here\n[00:08.00] Verse continues",
        }
        item = context_build.item_from_widgets(
            "audio",
            {
                "name": "Song",
                "context_id": "audio_song",
                "usage": "lock",
                "audio": "song.wav",
                "context_options": json.dumps(opt),
            },
        )
        ctx = context_mod.DirectorContext(idea="A scene", project_seconds=10.0, items=(item,))
        lines = lyrics.story_lines(ctx)
        # 4.0s - 2.0s = 2.0s = 48 frames
        self.assertEqual(lines[0].start_f, 48)


if __name__ == "__main__":
    unittest.main()
