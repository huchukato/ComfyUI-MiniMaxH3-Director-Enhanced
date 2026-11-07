import unittest

from _pack import module

context = module("ng.core.context")
issues = module("ng.core.issues")
chunks_mod = module("ng.core.chunks")


def item(**kw):
    base = dict(id="ctx_0001", name="Alice", media="image", source="refs/alice.png", content=("character",),
                usage=("reference",), preserve="high", description="a young woman in a red coat")
    base.update(kw)
    return context.ContextItem(**base)


class Items(unittest.TestCase):
    def test_roundtrip(self):
        a = item(speaker="ctx_0002", color="#88aaff")
        self.assertEqual(context.ContextItem.from_dict(a.to_dict()), a)

    def test_defaults_per_medium(self):
        self.assertEqual(item(usage=()).effective_usage, ("reference",))
        self.assertEqual(item(media="audio", usage=()).effective_usage, ("voice",))
        self.assertEqual(item(media="video", usage=()).effective_usage, ("motion",))
        self.assertEqual(item(media="text", usage=()).effective_usage, ("style",))

    def test_unknown_values_are_reported_not_mapped(self):
        problems = context.check_item(item(content=("character", "hat"), usage=("reference", "voice")))
        self.assertEqual({p.code for p in problems}, {"content_unknown", "usage_unknown"})
        self.assertIn("Alice", str(problems[0]))

    def test_missing_source_and_empty_text(self):
        self.assertEqual([p.code for p in context.check_item(item(source=""))], ["source_missing"])
        self.assertEqual([p.code for p in context.check_item(item(media="text", source=" ", usage=()))], ["text_empty"])

    def test_bad_data_names_the_path(self):
        with self.assertRaises(issues.SchemaError) as e:
            context.ContextItem.from_dict({"schema_version": 1, "id": "a", "name": "x", "media": "gif"}, "items[3]")
        self.assertTrue(str(e.exception).startswith("items[3].media"))
        with self.assertRaises(issues.SchemaError) as e:
            context.ContextItem.from_dict({"schema_version": 2}, "items[0]")
        self.assertIn("schema_version", str(e.exception))


class Director(unittest.TestCase):
    def test_roundtrip_with_items(self):
        d = context.DirectorContext(idea="a walk", project_seconds=30, items=(item(), item(id="ctx_0002", name="Bob")))
        self.assertEqual(context.DirectorContext.from_dict(d.to_dict()), d)

    def test_duplicate_ids_are_refused(self):
        data = context.DirectorContext(items=(item(), item(name="Other"))).to_dict()
        with self.assertRaises(issues.SchemaError):
            context.DirectorContext.from_dict(data)

    def test_duplicate_names_are_refused_for_mentions(self):
        data = context.DirectorContext(items=(item(), item(id="other", name="ALICE"))).to_dict()
        with self.assertRaisesRegex(issues.SchemaError, "name used twice"):
            context.DirectorContext.from_dict(data)

    def test_lookup_helpers(self):
        d = context.DirectorContext(items=(item(), item(id="ctx_0002", name="Voice", media="audio", usage=("voice",))))
        self.assertEqual(d.item("ctx_0002").name, "Voice")
        self.assertIsNone(d.item("nope"))
        self.assertEqual([i.name for i in d.by_media("audio")], ["Voice"])

    def test_invalid_numbers(self):
        with self.assertRaises(issues.SchemaError):
            context.DirectorContext.from_dict({"schema_version": 1, "project_seconds": 0})
        with self.assertRaises(issues.SchemaError):
            context.DirectorContext.from_dict({"schema_version": 1, "mode": "sideways"})


class SubjectsAndVoices(unittest.TestCase):
    """R4: a figure may own several voice cards, and a second take is never silently demoted."""

    def project(self, items, seconds=4):
        director = context.DirectorContext(idea="Alice walks.", project_seconds=seconds,
                                           shots_text="0-%d: Alice walks." % seconds, items=tuple(items))
        project = module("ng.core.project").plan_project(
            director, 0.0, chunks_mod.ContinuityPlan(mode="video_audio", video_frames=22, audio_frames=24))
        return project.compiled[0]

    def figure(self):
        return item(id="ctx_a", name="Alice", usage=("reference",))

    def voice(self, ctx_id, speaker="ctx_a", **kw):
        base = dict(id=ctx_id, name="Voice", media="audio", source="refs/%s.wav" % ctx_id,
                    usage=("voice",), speaker=speaker)
        base.update(kw)
        return context.ContextItem(**base)

    def test_one_voice_fills_the_subject_slot(self):
        compiled = self.project([self.figure(), self.voice("ctx_v")])
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1>.", compiled.prompt)
        self.assertEqual([r.ctx_id for r in compiled.refs if r.kind == "audio"], ["ctx_v"])
        self.assertEqual([i.code for i in compiled.issues if i.code == "voice_extra_take"], [])

    def test_a_second_take_is_sent_and_named(self):
        # H3 has one voice slot per subject, so the first take keeps it; the second still reaches the model and
        # the user is told why it is not the subject's voice.
        compiled = self.project([self.figure(), self.voice("ctx_v1", name="Take 1"), self.voice("ctx_v2", name="Take 2")])
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1>.", compiled.prompt)
        self.assertEqual(sorted(r.ctx_id for r in compiled.refs if r.kind == "audio"), ["ctx_v1", "ctx_v2"])
        notes = [i for i in compiled.issues if i.code == "voice_extra_take"]
        self.assertEqual([str(i) for i in notes], [
            "is a further voice take for the same figure; the first take keeps the subject's voice slot and this "
            "one is sent as an additional reference. (Take 2)"])

    def test_three_takes_report_once_each(self):
        compiled = self.project([self.figure()] + [self.voice("ctx_v%d" % n, name="Take %d" % n) for n in (1, 2, 3)])
        self.assertEqual([str(i).split(".")[-1].strip() for i in compiled.issues if i.code == "voice_extra_take"],
                         ["(Take 2)", "(Take 3)"])
        self.assertEqual(len([r for r in compiled.refs if r.kind == "audio"]), 3)

    def test_a_voice_without_a_figure_stays_an_ordinary_reference(self):
        compiled = self.project([self.figure(), self.voice("ctx_v", speaker="")])
        self.assertIn("<Audio 1> is a reference audio clip", compiled.prompt)
        self.assertEqual([i.code for i in compiled.issues if i.code == "voice_extra_take"], [])

    def test_every_planned_chunk_reports_the_extra_take(self):
        # The note lives on the chunk, so a long project must not lose it after the first 10 seconds.
        context_ = context.DirectorContext(idea="Alice walks.", project_seconds=20,
                                           shots_text="0-20: Alice walks.",
                                           items=(self.figure(), self.voice("ctx_v1", name="Take 1"),
                                                  self.voice("ctx_v2", name="Take 2")))
        project = module("ng.core.project").plan_project(
            context_, 0.0, chunks_mod.ContinuityPlan(mode="video_audio", video_frames=22, audio_frames=24))
        self.assertTrue(len(project.plan.chunks) > 1, "the example must actually split into several chunks")
        for chunk in project.compiled:
            self.assertEqual([i.code for i in chunk.issues if i.code == "voice_extra_take"], ["voice_extra_take"])


if __name__ == "__main__":
    unittest.main()
