"""Shot scope must preserve the ordered media roles consumed by the compiler."""
import json
import unittest

from _pack import module

context = module("ng.core.context")
chunks = module("ng.core.chunks")
project = module("ng.core.project")
bindings = module("ng.core.shot_bindings")
options = module("ng.core.context_options")


def shot(identity, start, end, media):
    return {"id": identity, "start": start, "end": end, "text": "A quiet scene.",
            "media": [{"schema_version": 1, "context_id": target, "role": role} for target, role in media]}


def plan(records, items, seconds=8, chunk_seconds=10, continuity=None):
    document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": records})
    ctx = context.DirectorContext(shots_text=document, items=items, project_seconds=seconds)
    return project.plan_project(ctx, chunk_seconds, continuity or chunks.ContinuityPlan("none"))


class OrderedRoles(unittest.TestCase):
    def test_inheriting_context_settings_preserves_first_supported_audio_role(self):
        item = context.ContextItem("sound", "Voice", "audio", "voice.wav", usage=("voice", "copy"), length_s=3)
        result = plan([shot("one", 0, 8, [("sound", "context")])], (item,))
        scoped, _ = bindings.scoped_context(result.context, result.plan.chunks[0])
        self.assertEqual(scoped.item("sound").effective_usage, ("voice", "copy"))
        self.assertIn("reference", result.compiled[0].prompt)
        self.assertNotIn("fully_copy", result.compiled[0].prompt)

    def test_role_order_follows_story_time_even_when_document_is_unsorted(self):
        item = context.ContextItem("sound", "Sound", "audio", "voice.wav", usage=("voice",), length_s=8)
        result = plan([shot("later", 4, 8, [("sound", "copy")]), shot("earlier", 0, 4, [("sound", "voice")])], (item,))
        scoped, _ = bindings.scoped_context(result.context, result.plan.chunks[0])
        self.assertEqual(scoped.item("sound").effective_usage, ("voice", "copy"))
        self.assertIn("audio_roles", {i.code for i in result.issues})

    def test_invalid_role_fallback_keeps_context_role_priority(self):
        item = context.ContextItem("sound", "Sound", "audio", "voice.wav", usage=("voice", "copy"), length_s=3)
        result = plan([shot("one", 0, 8, [("sound", "first_frame")])], (item,))
        scoped, _ = bindings.scoped_context(result.context, result.plan.chunks[0])
        self.assertEqual(scoped.item("sound").effective_usage, ("voice", "copy"))
        self.assertIn("shot_role_unknown", {i.code for i in result.issues})
        self.assertNotIn("fully_copy", result.compiled[0].prompt)


class NativeFixtureContract(unittest.TestCase):
    def test_late_short_audio_binding_is_placed_at_the_shot_start(self):
        records = [shot("first", 0, 10.125, []), shot("late", 10.125, 20, [("sound", "context")])]
        for role in ("copy", "lock"):
            with self.subTest(role=role):
                sound = context.ContextItem("sound", "Sound", "audio", "short.wav", usage=(role,), length_s=2)
                result = plan(records, (sound,), 20, 10, chunks.ContinuityPlan())
                chunk = result.plan.chunks[1]
                kind = "audio" if role == "copy" else "lock"
                self.assertEqual([(r.start_f, r.trim_start_f, r.length_f) for r in result.compiled[1].of_kind(kind)],
                                 [(243 - chunk.story_start_f + chunk.head_frames, 0, 48)])
                self.assertNotIn("shot_audio_origin", {i.code for i in result.issues})

    def test_reference_free_middle_chunk_and_new_subject_label_do_not_leak_previous_scope(self):
        first = shot("opening", 0, 85/24, [("alice", "context"), ("voice_a", "context")])
        middle = shot("quiet", 85/24, 8, [])
        last = shot("closing", 8, 277/24, [("bob", "context"), ("voice_b", "context")])
        for record, identity, words in ((first, "alice", "Hello there."), (last, "bob", "Good morning.")):
            record.update(spoken=[{"schema_version": 1, "speaker_id": identity, "text": words, "language": "English"}],
                          locked_fields=["spoken"], draft={"text": "DRAFT MUST NOT COMPILE"})
        items = tuple(context.ContextItem(identity, identity, "image", "same.png", content=("character",))
                      for identity in ("alice", "bob"))
        items += tuple(context.ContextItem(voice, voice, "audio", "same.wav", speaker=speaker, length_s=2)
                       for voice, speaker in (("voice_a", "alice"), ("voice_b", "bob")))
        result = plan([first, middle, last], items, 277/24, 4, chunks.ContinuityPlan())
        self.assertEqual(result.plan.total_frames, 277)
        self.assertEqual([c.sampled_frames for c in result.plan.chunks], [107, 107, 107])
        self.assertEqual([c.mode for c in result.compiled], ["ref2va", "t2va", "ref2va"])
        self.assertEqual([{r.ctx_id for r in c.refs} for c in result.compiled], [{"alice", "voice_a"}, set(), {"bob", "voice_b"}])
        self.assertEqual(dict(result.compiled[0].prompt_labels)["<Subject 1>"], "alice")
        self.assertEqual(dict(result.compiled[2].prompt_labels)["<Subject 1>"], "bob")
        self.assertIn("Good morning.", result.compiled[2].prompt)
        self.assertNotIn("Hello there.", result.compiled[2].prompt)
        self.assertTrue(all("DRAFT MUST NOT COMPILE" not in c.prompt for c in result.compiled))

    def test_shot_keyframe_override_keeps_absolute_scene_time_and_native_head_offset(self):
        records = [shot("first", 0, 10.125, []), shot("second", 10.125, 20, [("guide", "keyframe")])]
        guide = context.ContextItem("guide", "Guide", "image", "guide.png", options=options.ContextOptions(anchor_s=12))
        result = plan(records, (guide,), 20, 10, chunks.ContinuityPlan())
        self.assertFalse(result.compiled[0].refs)
        second = result.plan.chunks[1]
        refs = result.compiled[1].of_kind("keyframe")
        self.assertEqual(len(refs), 1)
        self.assertEqual((refs[0].ctx_id, refs[0].start_f), ("guide", 288 - second.story_start_f + second.head_frames))


if __name__ == "__main__":
    unittest.main()
