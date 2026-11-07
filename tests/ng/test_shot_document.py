import json
import unittest

from _pack import module

shots = module("ng.core.shots")
context = module("ng.core.context")
chunks = module("ng.core.chunks")
project = module("ng.core.project")
preview = module("ng.core.preview")
issues = module("ng.core.issues")
NONE = chunks.ContinuityPlan("none")


def record(identity, start=0, end=10, text="Walk.", **extra):
    return dict(id=identity, start=start, end=end, text=text, media=[], spoken=[], locked_fields=[], draft=None, **extra)


def document(*records):
    return json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": list(records)})


def bind(identity, role="context"):
    return {"schema_version": 1, "context_id": identity, "role": role}


def spoken(text="Hallo, Welt!", speaker=""):
    return {"schema_version": 1, "text": text, "speaker_id": speaker, "voice": "a calm narrator", "language": "German", "delivery": "whispers"}


def image(identity, **extra):
    return context.ContextItem(identity, identity, "image", identity + ".png", content=("character",), **extra)


def plan(text, items=(), seconds=20, continuity=NONE):
    return project.plan_project(context.DirectorContext(shots_text=text, items=items, project_seconds=seconds), 10, continuity)


class Document(unittest.TestCase):
    def test_legacy_ids_follow_source_records_after_time_sort(self):
        got, _ = shots.parse_shots("10-20: Later\n0-10: Earlier", 480)
        self.assertEqual([(s.text, s.id) for s in got], [("Earlier", "legacy-shot-2"), ("Later", "legacy-shot-1")])

    def test_stable_ids_survive_sort_clip_and_chunk_roundtrip(self):
        data = document(record("late", 10, 25), record("early", 0, 10))
        got, warnings = shots.parse_shots(data, 480)
        self.assertEqual([(s.id, s.end_f) for s in got], [("early", 240), ("late", 480)])
        self.assertIn("shot_clipped", [i.code for i in warnings])
        planned = plan(data)
        restored = chunks.SequencePlan.from_dict(planned.plan.to_dict())
        self.assertEqual(restored, planned.plan)
        self.assertEqual({s.shot_id for c in restored.chunks for s in c.shots}, {"early", "late"})

    def test_drafts_do_not_compile_and_locks_do_not_change_active_text(self):
        item = record("shot", end=8)
        item.update(draft={"text": "SECRET DRAFT"}, locked_fields=["text", "timing"])
        result = plan(document(item), seconds=8)
        self.assertIn("Walk.", result.compiled[0].prompt)
        self.assertNotIn("SECRET DRAFT", result.compiled[0].prompt)
        self.assertEqual(result.plan.chunks[0].shots[0].locked_fields, ("text", "timing"))

    def test_bad_documents_are_rejected_without_legacy_fallback(self):
        bad = ["{broken", json.dumps({"format": "other", "schema_version": 1, "shots": []}),
               document(record("same"), record("same")), document(record(""))]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(issues.SchemaError):
                shots.parse_shots(data, 240)

    def test_finite_times_types_version_and_locks(self):
        for field, value in [("start", float("nan")), ("start", True), ("end", -1), ("text", 3),
                             ("media", {}), ("locked_fields", ["unknown"]), ("draft", [])]:
            item = record("one"); item[field] = value
            with self.subTest(field=field), self.assertRaises(issues.SchemaError):
                shots.parse_shots(document(item), 240)
        payload = json.loads(document(record("one"))); payload["schema_version"] = 2
        with self.assertRaises(issues.SchemaError):
            shots.parse_shots(json.dumps(payload), 240)

    def test_empty_document_is_explicit_empty_story(self):
        self.assertEqual(shots.parse_shots(document(), 240), ((), ()))


class Bindings(unittest.TestCase):
    def story(self):
        first, second = record("first", 0, 10.125), record("second", 10.125, 20)
        first["media"] = [bind("a")]; second["media"] = [bind("b")]
        return document(first, second)

    def test_grid_extension_includes_next_shot_reference(self):
        first, second = record("first", 0, 10), record("second", 10, 20)
        first["media"] = [bind("a")]; second["media"] = [bind("b")]
        result = plan(document(first, second), (image("a"), image("b")))
        self.assertEqual(result.plan.chunks[0].story_end_f, 243)
        self.assertEqual({r.ctx_id for r in result.compiled[0].refs}, {"a", "b"})

    def test_shot_scopes_actual_compiled_references_not_just_display(self):
        result = plan(self.story(), (image("a"), image("b")))
        self.assertEqual([{r.ctx_id for r in c.refs} for c in result.compiled], [{"a"}, {"b"}])

    def test_unbound_contexts_remain_global_and_legacy_is_unchanged(self):
        result = plan(self.story(), (image("a"), image("b"), image("global")))
        self.assertEqual([{r.ctx_id for r in c.refs} for c in result.compiled], [{"a", "global"}, {"b", "global"}])
        old = plan("0-10: Walk\n10-20: Sit", (image("a"), image("b")))
        self.assertTrue(all({r.ctx_id for r in c.refs} == {"a", "b"} for c in old.compiled))

    def test_pinned_head_keeps_crossing_shot_media(self):
        result = plan(self.story(), (image("a"), image("b")), continuity=chunks.ContinuityPlan())
        self.assertEqual({r.ctx_id for r in result.compiled[1].refs}, {"a", "b"})

    def test_disconnected_context_is_reported_but_text_survives(self):
        result = plan(self.story())
        self.assertIn("Walk.", result.compiled[0].prompt)
        self.assertIn("shot_context_unknown", {i.code for i in result.issues})

    def test_bound_asset_keeps_subject_dependency(self):
        first, second = record("first", 0, 10), record("second", 10, 20)
        first["media"] = [bind("a")]; second["media"] = [bind("outfit")]
        result = plan(document(first, second), (image("a"), image("outfit", subject_ids=("a",))))
        self.assertEqual({r.ctx_id for r in result.compiled[1].refs}, {"a", "outfit"})

    def test_override_role_changes_compiled_media_with_invalid_role_warning(self):
        one = record("one", end=8); one["media"] = [bind("a", "first_frame")]
        result = plan(document(one), (image("a"),), seconds=8)
        self.assertEqual([(r.kind, r.ctx_id) for r in result.compiled[0].refs], [("first_frame", "a")])
        one["media"][0]["role"] = "music_style"
        result = plan(document(one), (image("a"),), seconds=8)
        self.assertIn("shot_role_unknown", {i.code for i in result.issues})
        self.assertEqual(result.compiled[0].refs[0].kind, "picture")

    def test_interior_shot_start_uses_its_actual_base_chunk_edge(self):
        first, second = record("first", 0, 10.125), record("second", 10.125, 20)
        second["media"] = [bind("a", "first_frame")]
        result = plan(document(first, second), (image("a"),))
        self.assertNotIn("shot_boundary_role", {i.code for i in result.issues})
        self.assertEqual([(r.kind, r.ctx_id, r.start_f) for r in result.compiled[1].refs], [("first_frame", "a", 0)])
        self.assertEqual(result.plan.chunks[1].story_start_f, 243)

    def test_override_anchor_conflicts_are_diagnosed_after_scope(self):
        one = record("one", end=8); one["media"] = [bind("a", "first_frame"), bind("b", "first_frame")]
        result = plan(document(one), (image("a"), image("b")), seconds=8)
        self.assertIn("anchor_multiple", {i.code for i in result.issues})
        self.assertEqual([(r.kind, r.ctx_id) for r in result.compiled[0].refs], [("first_frame", "a")])


class Dialogue(unittest.TestCase):
    def test_manual_narrator_without_context_or_api(self):
        one = record("one", end=8, text=""); one["spoken"] = [spoken()]
        result = plan(document(one), seconds=8)
        self.assertIn("<d>[German] Hallo, Welt!</d>", result.compiled[0].prompt)
        self.assertNotIn("no_text", {i.code for i in result.issues})
        self.assertEqual(result.compiled[0].refs, ())

    def test_speaker_binding_survives_rename(self):
        one = record("one", end=8); one["spoken"] = [spoken(speaker="a")]
        for name in ("Alice", "New Name"):
            subject = context.ContextItem("a", name, "image", "a.png", content=("character",))
            result = plan(document(one), (subject,), seconds=8)
            self.assertIn("<Subject 1> (S1) whispers", result.compiled[0].prompt)
            self.assertIn("<d>[German] Hallo, Welt!</d>", result.compiled[0].prompt)

    def test_a_note_that_belongs_to_a_figure_compiles_in_both_modes(self):
        alice = context.ContextItem("img1", "Alice", "image", "alice.png", usage=("reference",), content=("character",))
        note = context.ContextItem("t1", "Notes", "text", "Stay calm.", usage=("rule",), subject_ids=("img1",))
        for mode, expected in (("fl2va", "For Alice: Stay calm."), ("ref2va", "For <Subject 1>: Stay calm.")):
            result = project.plan_project(context.DirectorContext(idea="A walk.", project_seconds=4, items=(alice, note), mode=mode), 10, NONE)
            self.assertIn(expected, result.compiled[0].prompt, mode)

    def test_an_analysed_description_continues_the_subject_sentence(self):
        # The analysis answers in a sentence of its own; the prompt read "<Subject 1> is An elfin woman ...".
        elf = context.ContextItem("elf", "Mage", "image", "elf.png", usage=("reference",), content=("character",),
                                  description="An elfin woman with long white hair.")
        result = project.plan_project(context.DirectorContext(idea="She sings.", project_seconds=4, items=(elf,), mode="ref2va"), 10, NONE)
        self.assertIn("<Subject 1> is an elfin woman with long white hair, shown in <Picture 1>.", result.compiled[0].prompt)

    def test_a_manual_prompt_is_text_enough(self):
        empty = context.DirectorContext(shots_text="", project_seconds=8)
        self.assertIn("no_text", {i.code for i in project.plan_project(empty, 10, NONE).issues})
        manual = context.DirectorContext(shots_text="", project_seconds=8, prompt_override="A baker kneads dough.")
        self.assertNotIn("no_text", {i.code for i in project.plan_project(manual, 10, NONE).issues})

    def test_several_lines_compile_in_order_and_empty_ones_are_skipped(self):
        one = record("one", end=8); one["spoken"] = [spoken("Erste Zeile."), spoken(""), spoken("Second line.", speaker="a")]
        one["spoken"][2]["language"] = "English"
        result = plan(document(one), (context.ContextItem("a", "Alice", "image", "a.png", content=("character",)),), seconds=8)
        prompt = result.compiled[0].prompt
        self.assertLess(prompt.index("<d>[German] Erste Zeile.</d>"), prompt.index("<d>[English] Second line.</d>"))
        self.assertEqual(prompt.count("<d>"), 2)

    def test_unknown_speaker_retains_verbatim_line_with_warning(self):
        one = record("one", end=8); one["spoken"] = [spoken(speaker="gone")]
        result = plan(document(one), seconds=8)
        self.assertIn("<d>[German] Hallo, Welt!</d>", result.compiled[0].prompt)
        self.assertIn("shot_speaker_unknown", {i.code for i in result.issues})

    def test_continued_shot_does_not_repeat_dialogue(self):
        one = record("one", end=20); one["spoken"] = [spoken()]
        result = plan(document(one), continuity=chunks.ContinuityPlan())
        self.assertIn("Hallo, Welt!", result.compiled[0].prompt)
        self.assertNotIn("Hallo, Welt!", result.compiled[1].prompt)

    def test_preview_and_execution_use_identical_prompt_and_ids(self):
        one = record("one", end=8); one["spoken"] = [spoken()]
        text = document(one)
        execution = plan(text, seconds=8)
        view = preview.plan_preview({"director": {"shots": text, "project_seconds": 8, "chunk_seconds": 10, "continuity": "none"}})
        self.assertTrue(view["ok"], view)
        self.assertEqual(view["chunks"][0]["prompt"], execution.compiled[0].prompt)
        self.assertEqual(view["chunks"][0]["shots"][0]["shot_id"], "one")


if __name__ == "__main__":
    unittest.main()
