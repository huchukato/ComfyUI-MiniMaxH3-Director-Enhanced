"""The Director's Pictures output: one still per shot (core/stills.py; user 2026-10-19 after the picture tests)."""
import json
import unittest

from _pack import module

ctx, stills, turbo = module("ng.core.context"), module("ng.core.stills"), module("ng.core.turbo_profiles")
options = module("ng.core.context_options")


def doc(*records):
    return json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": list(records)})


def shot(n, text, media=()):
    return {"id": "s%d" % n, "start": 5 * (n - 1), "end": 5 * n, "text": text, "media": list(media)}


LUNA = ctx.ContextItem("luna", "Luna", "image", "luna.png", usage=("reference",), content=("character",), description="A woman.")
ROOM = ctx.ContextItem("room", "Room", "image", "room.png", usage=("first_frame",), content=("environment",), description="A bedroom.")
SONG = ctx.ContextItem("song", "Song", "audio", "song.wav", usage=("lock",), content=("music",))


def plan(shots_text="", items=(), idea="", mode="auto"):
    context = ctx.DirectorContext(idea=idea, shots_text=shots_text, items=tuple(items), project_seconds=10, mode=mode, width=1024,
                                  height=576, music="N/A", soundscape="Quiet.")
    return stills.plan_stills(context)


class Planning(unittest.TestCase):
    def test_every_shot_is_one_still_of_its_own(self):
        result = plan(doc(shot(1, "A lighthouse at dawn."), shot(2, "A storm over the sea.")))
        self.assertEqual(result.output, "images")
        self.assertEqual(len(result.plan.chunks), 2)
        self.assertEqual([c.head_frames for c in result.plan.chunks], [0, 0], "no picture is pinned to the one before")
        self.assertEqual([c.story_start_f for c in result.plan.chunks], [0, 120], "each picture under its shot on the timeline")
        self.assertEqual([s.shot_id for s in result.stills], ["s1", "s2"])
        self.assertIn("lighthouse", result.compiled[0].prompt)
        self.assertNotIn("lighthouse", result.compiled[1].prompt)

    def test_text_alone_is_text_to_image_with_the_frame_model(self):
        result = plan(doc(shot(1, "A lighthouse at dawn.")))
        self.assertEqual(result.compiled[0].mode, "t2va", "the FL2VA model without pictures")
        self.assertEqual(result.compiled[0].refs, ())
        self.assertEqual(result.stills[0].source, "")

    def test_cards_on_a_shot_become_picture_references(self):
        result = plan(doc(shot(1, "@Luna on a beach.", [{"schema_version": 1, "context_id": "luna", "role": "context"}])), [LUNA])
        self.assertEqual(result.compiled[0].mode, "ref2va")
        self.assertEqual([r.ctx_id for r in result.compiled[0].of_kind("picture")], ["luna"])

    def test_a_first_frame_picture_is_the_source_to_change(self):
        binding = {"schema_version": 1, "context_id": "room", "role": "first_frame"}
        result = plan(doc(shot(1, "Make the mug on the table red.", [binding])), [ROOM])
        compiled, still = result.compiled[0], result.stills[0]
        self.assertEqual((still.source_id, still.source), ("room", "room.png"))
        self.assertEqual([r.kind for r in compiled.refs], ["picture"], "a reference, never a frame anchor on a one-frame latent")
        self.assertIn(stills.DESCRIPTION + stills.SOURCE_LINE % 1, compiled.prompt)

    def test_with_no_shots_the_idea_changes_the_one_source_picture(self):
        result = plan(items=[ROOM], idea="Make it morning.")
        self.assertEqual(len(result.stills), 1)
        self.assertEqual(result.stills[0].source_id, "room")

    def test_the_card_edit_mask_travels_with_the_still(self):
        room = ctx.ContextItem.from_dict({**ROOM.to_dict(), "options": {**ROOM.options.to_dict(), "edit_mask": "masks/mug.png"}})
        result = plan(items=[room], idea="Make the mug red.")
        self.assertEqual(result.stills[0].mask, "masks/mug.png")

    def test_sound_cards_are_left_out_with_a_note(self):
        result = plan(doc(shot(1, "A lighthouse at dawn.")), [SONG])
        self.assertIn("still_unused", [i.code for i in result.issues])
        self.assertNotIn("song", [r.ctx_id for r in result.compiled[0].refs])

    def test_a_pose_card_is_a_guide_that_is_not_drawn(self):
        pose = ctx.ContextItem("pose", "Pose", "image", "pose.png", usage=("reference",), content=("pose",), description="Arms raised.")
        binding = {"schema_version": 1, "context_id": "pose", "role": "context"}
        result = plan(doc(shot(1, "A woman jumps in the pose of @Pose.", [binding])), [pose])
        self.assertIn("never appears in the picture", result.compiled[0].prompt)

    def test_nothing_written_is_no_picture(self):
        result = plan()
        self.assertEqual(result.stills, ())
        self.assertIn("no_text", [i.code for i in result.issues])


class Options(unittest.TestCase):
    def test_the_edit_mask_round_trips_and_is_left_out_when_empty(self):
        data = options.ContextOptions(edit_mask="m.png").to_dict()
        self.assertEqual(options.ContextOptions.from_dict(data).edit_mask, "m.png")
        self.assertNotIn("edit_mask", options.ContextOptions().to_dict())


class Turbo(unittest.TestCase):
    def test_pictures_take_a_loras_still_values_and_videos_keep_theirs(self):
        base = {"turbo": True, "turbo_lora_ref2va": "minimax-h3/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
                "turbo_lora_fl2va": "minimax_h3_turbo_v4_step600_ema.safetensors", "steps": 20, "sampler_name": "euler", "scheduler": "beta"}
        self.assertEqual(turbo.part_settings("fl2va", {**base, "output": "images"})["steps"], 8)
        self.assertEqual(turbo.part_settings("fl2va", {**base, "output": "video"})["steps"], 20, "no measured video values: the Director's")
        self.assertEqual(turbo.part_settings("ref2va", {**base, "output": "images"})["steps"], 6)
        self.assertEqual(turbo.part_settings("ref2va", base)["steps"], 6)


if __name__ == "__main__":
    unittest.main()
