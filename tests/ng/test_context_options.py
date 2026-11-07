import json
import unittest

from _pack import module

ctx = module("ng.core.context")
options = module("ng.core.context_options")
build = module("ng.core.context_build")
presets = module("ng.core.presets")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


class ContextDetails(unittest.TestCase):
    def plan(self, item):
        # Two H3 parts need at least 214 frames; 8 seconds is correctly one part (BUG-064).
        director = ctx.DirectorContext(idea="A woman walks.", project_seconds=10, items=(item,))
        return project.plan_project(director, 5, chunks.ContinuityPlan("none"))

    def test_multi_content_usage_and_preserve_survive_preset_and_widget_roundtrip(self):
        settings = options.ContextOptions(preserve=(("identity", "high"), ("background", "ignore")), anchor_s=3)
        item = build.item_from_widgets("image", {"image": "woman.png", "name": "Alice", "content": "character", "usage": "reference",
                                                 "content_roles": '["character","outfit"]', "usage_roles": '["reference","first_frame"]',
                                                 "context_options": json.dumps(settings.to_dict())})
        self.assertEqual(item.content, ("character", "outfit"))
        self.assertEqual(item.usage, ("reference", "first_frame"))
        preset = presets.ContextPreset.from_dict(presets.ContextPreset("Alice", item).to_dict())
        self.assertEqual(build.item_from_widgets("image", presets.widget_values(preset.item)), item)
        prompt = self.plan(item).compiled[0].prompt
        self.assertIn("identity: fully preserve", prompt)
        self.assertIn("background: allow to change", prompt)

    def test_old_context_without_options_is_still_readable(self):
        original = ctx.ContextItem("a", "Alice", "image", "alice.png")
        data = original.to_dict()
        del data["options"]
        self.assertEqual(ctx.ContextItem.from_dict(data), original)

    def test_options_validate_interval_properties_and_unknown_fields(self):
        for change in ({"start_s": 4, "end_s": 2}, {"preserve": {"identity": "infinite"}},
                       {"preserve": {"unknown": "high"}}, {"volume": 1}):
            with self.assertRaises(ValueError):
                options.ContextOptions.from_dict({**options.ContextOptions().to_dict(), **change})
        with self.assertRaises(ValueError):
            options.roles('{"role":"reference"}', "reference")

    def test_audio_selection_limits_reference_and_lock_material(self):
        selected = options.ContextOptions(start_s=2, end_s=5)
        for usage, kind in (("voice", "audio"), ("lock", "lock")):
            sound = ctx.ContextItem("v", "Voice", "audio", "voice.wav", usage=(usage,), length_s=10, options=selected)
            plan = self.plan(sound)
            first = plan.compiled[0].of_kind(kind)[0]
            self.assertEqual(first.trim_start_f, 48)
            self.assertLessEqual(first.length_f, 72)
            if usage == "lock":
                self.assertEqual(plan.compiled[1].of_kind("lock"), ())

    def test_keyframe_has_local_time_in_only_its_story_chunk(self):
        image = ctx.ContextItem("k", "Key", "image", "key.png", usage=("keyframe",), options=options.ContextOptions(anchor_s=6))
        plan = self.plan(image)
        self.assertEqual(plan.compiled[0].of_kind("keyframe"), ())
        guide = plan.compiled[1].of_kind("keyframe")[0]
        self.assertEqual(guide.start_f, 144 - plan.plan.chunks[1].story_start_f)
        self.assertNotIn("usage_pending", {issue.code for issue in plan.issues})

    def test_eight_seconds_keeps_its_duration_and_keyframe_in_one_valid_part(self):
        image = ctx.ContextItem("k", "Key", "image", "key.png", usage=("keyframe",), options=options.ContextOptions(anchor_s=6))
        director = ctx.DirectorContext(idea="A woman walks.", project_seconds=8, items=(image,))
        plan = project.plan_project(director, 5, chunks.ContinuityPlan("none"))
        self.assertEqual(plan.plan.total_frames, 192)
        self.assertEqual(len(plan.compiled), 1)
        self.assertEqual(plan.compiled[0].of_kind("keyframe")[0].start_f, 144)

    def test_video_continuation_and_soundtrack_options_are_explicit(self):
        video = ctx.ContextItem("v", "Continue", "video", "video.mp4", usage=("continue",), length_s=10,
                                options=options.ContextOptions(start_s=1, end_s=6, video_audio="ignore"))
        plan = self.plan(video)
        ref = plan.compiled[0].of_kind("continue_video")[0]
        self.assertEqual((ref.trim_start_f, ref.length_f), (105, 39))
        self.assertEqual(plan.compiled[1].of_kind("continue_video"), ())


if __name__ == "__main__":
    unittest.main()
