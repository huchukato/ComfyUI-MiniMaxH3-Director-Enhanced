"""Several assets can describe one Subject, without losing their own card or native picture labels."""
import json
import unittest

from _pack import module

build = module("ng.core.context_build")
ctx = module("ng.core.context")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def card(media, identity, name, **changes):
    values = dict(context_id=identity, name=name, description="", content="character" if media == "image" else media,
                  usage=dict(image="reference", video="motion", audio="voice", text="rule")[media], preserve="high")
    values[media] = "Follow @Alice." if media == "text" else "same.file"
    values.update(changes)
    return build.item_from_widgets(media, values, 2 if media in ("video", "audio") else 0)


def plan(items):
    return project.plan_project(ctx.DirectorContext(idea="@Alice wears @Coat and moves.", shots_text="0-8: @Alice walks.\n@Alice says: Hello.",
                                project_seconds=8, width=64, height=64, items=tuple(items)), 5, chunks.ContinuityPlan("video_audio", 22, 24))


class SubjectAssets(unittest.TestCase):
    def test_scene_suggestion_receives_stable_relationships_without_file_paths(self):
        direction = module("ng.core.auto_direct")
        entries = [{"media": "image", "widgets": {"name": "Alice", "context_id": "alice", "image": "private/alice.png"}},
                   {"media": "image", "widgets": {"name": "Coat", "context_id": "coat", "image": "private/coat.png",
                                              "subject_ids": '["alice"]'}}]
        prompt = direction.direction_prompt("Alice wears Coat", 8, entries)
        meanings = json.loads(prompt.split("\nContexts: ")[1])
        self.assertEqual(meanings[1]["subject_ids"], '["alice"]')
        self.assertEqual(meanings[0]["context_id"], "alice")
        self.assertNotIn("private/", prompt)
        self.assertIn("instead of inventing independent figures", prompt)

    def test_outfit_keeps_its_card_and_picture_but_does_not_become_a_second_subject(self):
        figure = card("image", "alice", "Alice", description="a woman")
        coat = card("image", "coat", "Coat", content="outfit", subject_ids='["alice"]', description="a red coat", preserve="low")
        voice = card("audio", "voice", "Voice", speaker="alice")
        for compiled in plan([coat, figure, voice]).compiled:
            self.assertEqual(dict(compiled.prompt_labels)["<Subject 1>"], "alice")
            self.assertNotIn("<Subject 2>", compiled.prompt)
            self.assertEqual([(r.ctx_id, r.source) for r in compiled.of_kind("picture")], [("alice", "same.file"), ("coat", "same.file")])
            self.assertIn("<Subject 1> wears <Picture 2>", compiled.prompt)
            self.assertIn("outfit reference in <Picture 2>", compiled.prompt)
            self.assertIn("weak_reference", compiled.prompt)
            self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1>", compiled.prompt)

    def test_one_asset_can_belong_to_two_subjects(self):
        cards = [card("image", "alice", "Alice"), card("image", "bob", "Bob"),
                 card("image", "coat", "Coat", content="outfit", subject_ids='["alice","bob"]')]
        for compiled in plan(cards).compiled:
            self.assertEqual([ref.ctx_id for ref in compiled.of_kind("picture")], ["alice", "coat", "bob", "coat"])
            self.assertEqual(dict(compiled.prompt_labels)["<Subject 2>"], "bob")
            self.assertIn("<Subject 2> uses the outfit reference in <Picture 4>", compiled.prompt)
            self.assertNotIn("<Subject 3>", compiled.prompt)

    def test_voice_name_resolution_uses_the_same_casefold_as_mentions(self):
        items = [card("image", "alice", "Straße"), card("audio", "voice", "Voice", speaker="STRASSE")]
        result = plan(items)
        self.assertEqual(result.context.item("voice").speaker, "alice")
        self.assertNotIn("speaker_unknown", [issue.code for issue in result.issues])

    def test_old_context_and_preset_roundtrip_keeps_stable_owners(self):
        preset = module("ng.core.presets")
        coat = card("image", "coat", "Coat", subject_ids='["alice","bob"]')
        restored = preset.ContextPreset.from_dict(preset.ContextPreset("Coat", coat).to_dict()).item
        self.assertEqual(build.item_from_widgets("image", preset.widget_values(restored)), coat)
        old = card("image", "alice", "Alice").to_dict()
        del old["subject_ids"]
        self.assertEqual(ctx.ContextItem.from_dict(old).subject_ids, ())

    def test_names_normalize_to_ids_and_do_not_depend_on_connector_order(self):
        figure = card("image", "alice", "Straße")
        coat = card("image", "coat", "Coat", subject_ids='["STRASSE","alice"]')
        result = plan([coat, figure])
        self.assertEqual(result.context.item("coat").subject_ids, ("alice",))
        self.assertEqual(result.compiled[0].of_kind("picture")[0].ctx_id, "alice")

    def test_invalid_self_chained_and_cyclic_assignments_report_and_keep_material(self):
        for assignments in [("missing", ""), ("alice", ""), ("coat", "alice")]:
            with self.subTest(assignments=assignments):
                first = card("image", "alice", "Alice", subject_ids=json.dumps([assignments[0]]))
                second = card("image", "coat", "Coat", subject_ids=json.dumps([assignments[1]]) if assignments[1] else "")
                result = plan([first, second])
                self.assertIn("subject_target_invalid", [issue.code for issue in result.issues])
                self.assertEqual({ref.ctx_id for ref in result.compiled[0].of_kind("picture")}, {"alice", "coat"})

    def test_video_and_text_scope_keeps_audio_offset_and_voice_binding(self):
        figure = card("image", "alice", "Alice")
        video = card("video", "motion", "Move", content="pose", subject_ids='["alice"]',
                     context_options='{"schema_version":1,"video_audio":"reference"}')
        rules = card("text", "rules", "Rules", text="Use slow gestures and @Move.", subject_ids='["alice"]')
        voice = card("audio", "voice", "Voice", speaker="alice")
        for compiled in plan([figure, video, rules, voice]).compiled:
            self.assertIn("<Subject 1> uses the pose reference in <Video 1>", compiled.prompt)
            self.assertIn("For <Subject 1>: Use slow gestures and <Video 1>.", compiled.prompt)
            self.assertIn("<Audio 1> is the soundtrack of <Video 1>", compiled.prompt)
            self.assertIn("<Audio 2> is the voice-timbre reference for <Subject 1>", compiled.prompt)

    def test_a_shared_asset_dropped_only_for_second_owner_is_named(self):
        figures = [card("image", "alice", "Alice"), card("image", "bob", "Bob")]
        assets = [card("image", "coat%d" % n, "Coat%d" % n, content="outfit", subject_ids='["alice","bob"]') for n in range(5)]
        result = plan(figures + assets)
        for compiled in result.compiled:
            self.assertEqual(len(compiled.of_kind("picture")), 9)
            notes = [issue for issue in compiled.issues if issue.code == "asset_relation_unavailable"]
            self.assertTrue(any(issue.ref == "Coat4" and "Bob" in issue.text for issue in notes), notes)
            self.assertNotIn("<Picture 10>", compiled.prompt)
            self.assertNotIn("<Picture 12>", compiled.prompt)

    def test_scoped_nonreference_roles_warn_without_becoming_fake_reference_labels(self):
        figure = card("image", "alice", "Alice")
        frame = card("image", "frame", "Frame", usage="first_frame", subject_ids='["alice"]')
        result = plan([figure, frame])
        self.assertIn("asset_relation_unavailable", [issue.code for issue in result.issues])
        self.assertEqual(result.compiled[0].of_kind("first_frame")[0].ctx_id, "frame")

    def test_text_scope_never_mentions_a_subject_dropped_by_the_reference_budget(self):
        figures = [card("image", "alice", "Alice"), card("image", "bob", "Bob")]
        assets = [card("image", "coat%d" % n, "Coat%d" % n, content="outfit", subject_ids='["alice"]') for n in range(8)]
        for owners, scope in [('["alice","bob"]', "For <Subject 1>:"), ('["bob"]', "Context guidance:")]:
            with self.subTest(owners=owners):
                rules = card("text", "rules", "Rules", content="rules", text="Keep hands visible.", subject_ids=owners)
                result = plan(figures + assets + [rules])
                for compiled in result.compiled:
                    self.assertIn(scope + " Keep hands visible.", compiled.prompt)
                    self.assertNotIn("@ref2", compiled.prompt)
                    self.assertNotIn("<Subject 2>", compiled.prompt)
                    self.assertTrue(any(issue.ref == "Rules" and "Bob" in issue.text for issue in compiled.issues))

    def test_manual_override_stays_exact_and_raw_relations_remain_visible(self):
        items = (card("image", "alice", "Alice"), card("image", "coat", "Coat", subject_ids='["alice"]'))
        original = ctx.DirectorContext(idea="x", items=items, project_seconds=8, prompt_override="exact raw prompt")
        result = project.plan_project(original, 5, chunks.ContinuityPlan("none"))
        self.assertTrue(all(compiled.prompt == "exact raw prompt" for compiled in result.compiled))
        self.assertEqual(result.context.item("coat").subject_ids, ("alice",))
