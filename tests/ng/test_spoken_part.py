"""A spoken line of a shot that starts in the last two seconds of a render part is said in the next part (night test
2026-10-20: a line of a shot starting 0.3 s before the part's end was spoken from 1.3 s on, over the shot before). Since the
Ref2VA minute (2026-10-20) the part edge moves first, so the shot gets its two seconds (core/boundaries.py); the line moves
only where the edge cannot."""
import json
import unittest

from _pack import module

ctx, project, chunks = module("ng.core.context"), module("ng.core.project"), module("ng.core.chunks")
shot_share = module("ng.core.shot_share")
LUNA = ctx.ContextItem("luna", "Luna", "image", "luna.png", usage=("reference",), content=("character",), description="A woman.")


def plan(second_start):
    line = {"schema_version": 1, "text": "The moon is bright tonight.", "speaker_id": "luna", "voice": "a calm young woman",
            "language": "English", "delivery": "says"}
    shots = [{"id": "a", "start": 0, "end": second_start, "text": "@Luna walks.", "media": [{"schema_version": 1, "context_id": "luna", "role": "context"}]},
             {"id": "b", "start": second_start, "end": 15, "text": "@Luna stops.", "spoken": [line],
              "media": [{"schema_version": 1, "context_id": "luna", "role": "context"}]}]
    context = ctx.DirectorContext(shots_text=json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": shots}),
                                  items=(LUNA,), project_seconds=15, width=1280, height=704, music="N/A", soundscape="Quiet.")
    return project.plan_project(context, 0, chunks.ContinuityPlan("video_audio"))


class SpokenPart(unittest.TestCase):
    def test_a_shot_starting_late_in_a_part_moves_the_part_edge_and_speaks_where_it_starts(self):
        result = plan(7)                     # 7.0 s lay 0.3 s before the edge of a 7.29 s first part
        self.assertEqual(len(result.plan.chunks), 2)
        offset = 7 * 24 - result.plan.chunks[0].story_end_f
        self.assertTrue(offset <= -48 or offset >= 60, "the shot starts 2 s before the edge or 2.5 s after it, not at it")
        speaking = 0 if offset < 0 else 1
        self.assertIn("bright tonight", result.compiled[speaking].prompt)
        self.assertNotIn("bright tonight", result.compiled[1 - speaking].prompt)
        self.assertNotIn("has no spoken line", " ".join(i.text for i in result.issues))

    def test_a_line_of_a_shot_starting_late_in_a_part_moves_to_the_next(self):
        late = chunks.ChunkShot(1, 200, 238, "", carried=False, continues=True, shot_start_f=168)
        part = chunks.Chunk(0, 0, 175, 0, shots=(late,))
        nxt = chunks.Chunk(1, 175, 185, 22, shots=(chunks.ChunkShot(1, 0, 207, "", carried=True, continues=False, shot_start_f=168),))
        self.assertFalse(shot_share.lines_here(late, part))      # 7 frames of the shot in this part
        self.assertTrue(shot_share.lines_here(nxt.shots[0], nxt))

    def test_a_line_of_a_shot_with_room_stays_where_it_starts(self):
        result = plan(3)
        self.assertIn("bright tonight", result.compiled[0].prompt)
        self.assertNotIn("bright tonight", result.compiled[1].prompt)


if __name__ == "__main__":
    unittest.main()
