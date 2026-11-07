"""A shot's effect embedding (the official embedding:minimaxh3_* files) is written after the shot's action in the part
where the shot starts, in both modes; a later part of the shot does not start the effect again."""
import json
import unittest

from _pack import module

ctx, project, chunks, document = (module("ng.core.context"), module("ng.core.project"), module("ng.core.chunks"),
                                  module("ng.core.shot_document"))
HERO = ctx.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",), content=("character",), description="A runner.")


def plan(mode, effect="minimaxh3_bullet_time", seconds=20):
    shots = [{"id": "a", "start": 0, "end": seconds, "text": "@Hero jumps over the wall. She lands softly.", "effect": effect,
              "spoken": [{"schema_version": 1, "text": "Now.", "speaker_id": "hero", "language": "English", "delivery": "says"}],
              "media": [{"schema_version": 1, "context_id": "hero", "role": "context"}]}]
    context = ctx.DirectorContext(shots_text=json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": shots}),
                                  items=(HERO,), project_seconds=seconds, width=1280, height=704, mode=mode, music="N/A", soundscape="Wind.")
    return project.plan_project(context, 10, chunks.ContinuityPlan("video_audio"))


class Effect(unittest.TestCase):
    def test_the_effect_follows_the_action_in_the_first_part_only(self):
        for mode in ("ref2va", "fl2va"):
            first, second = (c.prompt for c in plan(mode).compiled)
            self.assertIn("embedding:minimaxh3_bullet_time", first, mode)
            self.assertLess(first.index("embedding:minimaxh3_bullet_time"), first.index("Now."), mode)
            self.assertNotIn("embedding:", second, mode)

    def test_names_are_cleaned_and_odd_ones_dropped(self):
        self.assertEqual(document.effect_name("embedding:minimaxh3_kiss_camera.safetensors"), "minimaxh3_kiss_camera")
        self.assertEqual(document.effect_name("bad name; rm"), "")
        self.assertNotIn("embedding:", plan("ref2va", effect="a b").compiled[0].prompt)

    def test_an_own_prompt_that_lost_the_effect_gets_it_back(self):
        share = module("ng.core.shot_share")
        own = "detailed_description: [Shot 1] A rewritten jump.\n\noverall_soundscape: Wind."
        kept = share.keep_effects("x embedding:minimaxh3_bullet_time y", own)
        self.assertIn("A rewritten jump. embedding:minimaxh3_bullet_time \n\noverall_soundscape: Wind.", kept)
        self.assertEqual(share.keep_effects("no effect", own), own)


if __name__ == "__main__":
    unittest.main()
