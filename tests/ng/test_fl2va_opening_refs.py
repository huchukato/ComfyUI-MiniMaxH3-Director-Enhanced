"""A part that continues a shot opened on its own First frame picture gets that picture as a reference (FL2VA minute
2026-10-20: the text-only part after a push-in made a different dress), and every continued part names the camera."""
import json
import unittest

from _pack import module

ctx, project, chunks = module("ng.core.context"), module("ng.core.project"), module("ng.core.chunks")
shot_share = module("ng.core.shot_share")
OPEN = ctx.ContextItem("open", "Profile", "image", "profile.png", usage=("first_frame",), content=("character",), description="An elf.")


def plan(media, seconds=20, text="The elf sings, the camera holds."):
    shots = [{"id": "a", "start": 0, "end": seconds, "text": text, "media": media}]
    context = ctx.DirectorContext(shots_text=json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": shots}),
                                  items=(OPEN,), project_seconds=seconds, width=768, height=1152, mode="fl2va",
                                  music="N/A", soundscape="Quiet.")
    return project.plan_project(context, 10, chunks.ContinuityPlan("video_audio"))


class OpeningReference(unittest.TestCase):
    def test_the_continued_part_gets_the_opening_picture_as_a_reference(self):
        result = plan([{"schema_version": 1, "context_id": "open", "role": "first_frame"}])
        self.assertEqual(len(result.compiled), 2)
        self.assertEqual([(r.kind, r.ctx_id) for r in result.compiled[0].refs], [("first_frame", "open")])
        second = result.compiled[1]
        self.assertEqual([(r.kind, r.ctx_id) for r in second.refs], [("picture", "open")])
        self.assertIn("<Picture 1> is the opening frame of this shot", second.prompt)

    def test_a_shot_without_its_own_opening_picture_adds_nothing(self):
        result = plan([])
        self.assertFalse([r for c in result.compiled for r in c.refs if r.kind == "picture"])


class CameraLine(unittest.TestCase):
    """A continued part names the camera: without a line it went on pushing in or cut away (FL2VA minute 2026-10-20)."""

    def test_a_removed_move_is_replaced_by_keeping_the_framing(self):
        second = plan([], text="The elf sings softly. The camera pushes in slowly.").compiled[1].prompt
        self.assertNotIn("pushes in", second)
        self.assertIn(shot_share.KEEP_FRAMING, second)
        self.assertIn("pushes in", plan([], text="The elf sings softly. The camera pushes in slowly.").compiled[0].prompt)

    def test_a_camera_line_of_the_user_stays_alone(self):
        first, second = (c.prompt for c in plan([], text="The elf sings softly. The camera holds a stable side view.").compiled)
        self.assertIn("The camera holds a stable side view.", second)
        self.assertNotIn(shot_share.KEEP_FRAMING, second)
        # how the shot is filmed holds for all of it: shared by length, the line went to the second part only
        self.assertIn("The camera holds a stable side view.", first)

    def test_an_action_toward_the_camera_is_no_camera_line(self):
        second = plan([], text="The elf walks away. Then she walks toward the camera.").compiled[1].prompt
        self.assertIn(shot_share.KEEP_FRAMING, second)


if __name__ == "__main__":
    unittest.main()
