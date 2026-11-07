import unittest

from _pack import module

chunks = module("ng.core.chunks")
context = module("ng.core.context")
project = module("ng.core.project")

VIDEO = chunks.ContinuityPlan("video_audio", 22, 24)


def item(id_, name, media, source, **kw):
    return context.ContextItem(id=id_, name=name, media=media, source=source, **kw)


ALICE = item("image_alice", "Alice", "image", "alice.png", content=("character",), usage=("reference",), description="a young woman")
VOICE = item("audio_alice", "Alice voice", "audio", "alice.wav", usage=("voice",), speaker="alice", length_s=8)


class Helpers(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(project.slug("Space Station!"), "space_station")
        self.assertEqual(project.slug("???"), "item")

    def test_speaker_names_become_ids(self):
        items, issues = project.resolve_speakers((ALICE, VOICE))
        self.assertEqual(items[1].speaker, "image_alice")
        self.assertEqual(issues, [])

    def test_unknown_speaker_is_reported_and_cleared(self):
        ghost = item("audio_x", "Ghost", "audio", "g.wav", usage=("voice",), speaker="Nobody")
        items, issues = project.resolve_speakers((ALICE, ghost))
        self.assertEqual(items[1].speaker, "")
        self.assertEqual([i.code for i in issues], ["speaker_unknown"])

    def test_canvas_snaps_to_multiples_of_32(self):
        self.assertEqual(project.snap_canvas(768, 1152), ((768, 1152), []))
        (w, h), issues = project.snap_canvas(500, 700)
        self.assertEqual((w, h), (512, 704))
        self.assertEqual(issues[0].code, "canvas_snapped")
        self.assertEqual(project.snap_canvas(10, 10)[0], (32, 32))


class Plan(unittest.TestCase):
    def test_idea_only_project(self):
        out = project.plan_project(context.DirectorContext(idea="A woman plays with a red ball.", project_seconds=60), 10, VIDEO)
        self.assertEqual(len(out.plan.chunks), len(out.compiled))
        self.assertGreaterEqual(len(out.plan.chunks), 6)
        self.assertTrue(all("red ball" in c.prompt for c in out.compiled))
        self.assertIn("audio_dulling", [i.code for i in out.issues])

    def test_scripted_project_with_references(self):
        ctx = context.DirectorContext(items=(ALICE, VOICE), project_seconds=20, shots_text="0-12: @Alice walks.\n@Alice says: Hi.\n12-20: @Alice sits.")
        out = project.plan_project(ctx, 10, VIDEO)
        self.assertEqual(out.compiled[0].mode, "ref2va")
        self.assertIn("(S1)", out.compiled[0].prompt)
        self.assertEqual(out.context.item("audio_alice").speaker, "image_alice")

    def test_issues_are_collected_once(self):
        ghost = item("audio_x", "Ghost", "audio", "g.wav", usage=("voice", "teleport"), speaker="Nobody")
        out = project.plan_project(context.DirectorContext(idea="x", items=(ALICE, ghost), project_seconds=40), 10, VIDEO)
        codes = [i.code for i in out.issues]
        self.assertEqual(codes.count("usage_unknown"), 1)
        self.assertEqual(codes.count("speaker_unknown"), 1)

    def test_the_same_problem_in_every_chunk_is_listed_once(self):
        out = project.plan_project(context.DirectorContext(idea="A dog runs.", project_seconds=30), 10, VIDEO)
        soundscape = [i for i in out.issues if "overall_soundscape is empty" in i.text]
        self.assertEqual(len(soundscape), 1)
        self.assertEqual(soundscape[0].ref, "")                       # it applies to all three chunks

    def test_a_problem_in_some_chunks_names_them(self):
        issues = [project.Issue("planner", "x", "Render part 1"), project.Issue("planner", "x", "Render part 3"), project.Issue("other", "y", "shot 2")]
        merged = project._merge(issues, 3)
        self.assertEqual([(i.text, i.ref) for i in merged], [("x", "Render part 1, 3"), ("y", "shot 2")])

    def test_describe_lists_every_chunk(self):
        out = project.plan_project(context.DirectorContext(idea="x", project_seconds=30), 10, VIDEO)
        text = project.describe(out)
        self.assertEqual(text.count("chunk "), len(out.plan.chunks))
        self.assertIn("video_audio", text)

    def test_canvas_is_applied_to_the_planned_context(self):
        out = project.plan_project(context.DirectorContext(idea="x", project_seconds=8, width=500, height=700), 0, VIDEO)
        self.assertEqual((out.context.width, out.context.height), (512, 704))
        self.assertIn("canvas_snapped", [i.code for i in out.issues])


if __name__ == "__main__":
    unittest.main()
