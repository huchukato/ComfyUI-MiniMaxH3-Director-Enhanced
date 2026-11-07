"""A render part's own prompt: the AI writes only prose, the plan's structure is checked, and an edit made for an older
plan is not used silently."""
import json
import unittest

from _pack import module

part, writer = module("ng.core.part_prompt"), module("ng.core.part_writer")
ctx, project, chunks = module("ng.core.context"), module("ng.core.project"), module("ng.core.chunks")

BASE = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video.\n\n"
        "integrated_multimodal_description: [Shot 1] Gothic hall. The mage (S1) sings, <d>[English] My master, where did your footsteps fade?</d> "
        "[Shot 2] At 00:04.500, the camera cuts to her hands.\n\n"
        "overall_soundscape: ambience that fits the scene\n\nnon_diegetic_music: N/A")
LONG = ("The mage stands in the cold gothic hall, white hair falling over a black lace dress, the staff glowing amber in her "
        "right hand while candles flicker behind her and embers drift through the dark air. She lifts her gaze toward the "
        "high windows. The camera pushes in with small amplitude at slow speed. ")
GOOD = ("description: [Shot 1] Dark fantasy anime style, a medium shot frames the mage. " + LONG +
        "The mage (S1) sings, <d>[English] My master, where did your footsteps fade?</d> Her lips close softly. "
        "[Shot 2] At 00:04.500, the camera cuts to a close-up of her hands tightening around the staff.\n"
        "overall_soundscape: Candles crackle and wind moves through the hall.\n"
        "non_diegetic_music: Slow strings and soft piano.")


class Check(unittest.TestCase):
    def test_a_faithful_answer_keeps_the_alignment_line_and_replaces_only_prose(self):
        final, problems = part.check(BASE, GOOD)
        self.assertEqual(problems, [])
        self.assertTrue(final.startswith("How the reference pictures align"))
        self.assertIn("integrated_multimodal_description: [Shot 1] Dark fantasy anime style", final)
        self.assertIn("overall_soundscape: Candles crackle", final)
        self.assertIn("non_diegetic_music: Slow strings and soft piano.", final)

    def test_changed_words_cuts_labels_or_sections_are_refused(self):
        cases = {
            "spoken or sung lines": GOOD.replace("footsteps fade", "steps fade"),
            "cut times": GOOD.replace("00:04.500", "00:05.000"),
            "labels the plan does not have": GOOD.replace("The mage stands", "<Subject 2> stands"),
            "start with [Shot 1]": GOOD.replace("description: [Shot 1] ", "description: Style. [Shot 1] "),
            "nests another prompt section": GOOD.replace("Her lips close softly.", "Her lips close.\nsummary: x"),
            "shorter than": "description: [Shot 1] Short. The mage (S1) sings, <d>[English] My master, where did your footsteps fade?</d> "
                            "[Shot 2] At 00:04.500, hands.",
        }
        for reason, answer in cases.items():
            with self.subTest(reason=reason):
                final, problems = part.check(BASE, answer)
                self.assertIsNone(final)
                self.assertTrue(any(reason in problem for problem in problems), problems)

    def test_what_a_model_reliably_gets_slightly_wrong_is_put_back(self):
        # qwen3.5:9b on the elf song: a time on Shot 1, "(S1) sings" without its label, a lyric line re-punctuated.
        compiled = BASE.replace("The mage (S1)", "<Subject 1> (S1)")
        answer = (GOOD.replace("[Shot 1] Dark", "[Shot 1] At 00:00.000, Dark").replace("The mage (S1)", "Then (S1)")
                  .replace("My master, where did your footsteps fade?", "My master where did your footsteps fade")
                  .replace("[Shot 2] At 00:04.500,", "[Shot 2]"))
        final, problems = part.check(compiled, answer)
        self.assertEqual(problems, [])
        self.assertIn("[Shot 1] Dark fantasy", final)
        self.assertIn("Then <Subject 1> (S1) sings, <d>[English] My master, where did your footsteps fade?</d>", final)
        self.assertIn("[Shot 2] At 00:04.500,", final)
        # ... and once left every lyric line out of an otherwise good part: each goes back to the end of its shot.
        lost = GOOD.replace("The mage (S1) sings, <d>[English] My master, where did your footsteps fade?</d> ", "")
        final, problems = part.check(compiled, lost)
        self.assertEqual(problems, [])
        self.assertIn("high windows. The camera pushes in with small amplitude at slow speed. Her lips close softly. <Subject 1> (S1) sings, "
                      "<d>[English] My master, where did your footsteps fade?</d> [Shot 2]", final)
        # qwen3.5:9b dropped the speaker of a sung line altogether ("As she sings, <d>...").
        final, problems = part.check(compiled, GOOD.replace("The mage (S1) sings, <d>", "As she sings, <d>"))
        self.assertEqual(problems, [])
        self.assertIn("As she sings, <Subject 1> (S1) <d>[English] My master", final)
        self.assertIn("- <Subject 1> (S1) sings, <d>[English] My master, where did your footsteps fade?</d>", part.request(compiled, "fl2va", 8))

    def test_reference_sections_stay_the_planners(self):
        compiled = ("subject_definitions:\n<Subject 1> is the woman in <Picture 1>.\n\nsummary: [reference generation] x\n\n"
                    "retention_analysis:\n<Subject 1> (appears in [Shot 1]): fully_preserved - kept.\n\n"
                    "detailed_description: Style. [Shot 1] <Subject 1> waves.\n\noverall_soundscape: wind\n\nnon_diegetic_music: N/A")
        answer = "subject_definitions: <Subject 1> is someone else.\ndescription: Cinematic anime style. [Shot 1] <Subject 1> " + LONG
        final, problems = part.check(compiled, answer)
        self.assertEqual(problems, [])
        self.assertIn("subject_definitions:\n<Subject 1> is the woman in <Picture 1>.", final)
        self.assertNotIn("someone else", final)
        self.assertIn("overall_soundscape: wind", final, "a missing sound field keeps the planner's")

    def test_the_request_names_labels_cuts_and_keeps_the_story_as_material(self):
        text = part.request(BASE, "fl2va", 8.7, story="She sings a sad song.", continues=True, part=(2, 3))
        self.assertIn("part 2 of 3", text)
        self.assertIn("Draft:\nHow the reference pictures align", text)
        self.assertIn("description: [Shot 1] Gothic hall.", text)
        self.assertIn("Story:\nShe sings a sad song.", text)
        self.assertIn("continues the previous part", text)
        self.assertIn("holds a static shot", text)
        # comparison 2026-10-20: movement as a change, no camera move over a seam, no oily skin words
        for rule in ("easing out of", "go on past its end", "flawless", "keep the camera's framing"):
            self.assertIn(rule, text)
        self.assertNotIn("time beat", text, "no beats in the draft, no beat rule")
        beats = BASE.replace("[Shot 1] Gothic hall.", "[Shot 1] 0–2.5s: Gothic hall, a wide shot. 2.5–4.5s: She turns.")
        self.assertIn("Keep each time beat of the draft", part.request(beats, "fl2va", 8.7))


def plan(shots_text, idea="An elf sings.", seconds=8.0):
    director = ctx.DirectorContext(idea=idea, shots_text=shots_text, project_seconds=seconds, mode="fl2va")
    return project.plan_project(director, 0, chunks.ContinuityPlan("none"))


def doc(own=None):
    data = {"format": "h3-director-shots", "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 8, "text": "She sings.", "media": [], "spoken": [], "locked_fields": [], "draft": None}]}
    if own is not None:
        data["part_prompts"] = own
    return json.dumps(data)


class OwnPrompt(unittest.TestCase):
    def test_an_own_prompt_written_from_this_plan_goes_to_the_sampler(self):
        compiled = plan(doc()).compiled[0]
        self.assertEqual((compiled.source, len(compiled.key)), ("compiled", 12))
        mine = plan(doc([{"index": 0, "key": compiled.key, "text": "integrated_multimodal_description: [Shot 1] Mine.", "by": "user"}])).compiled[0]
        self.assertEqual((mine.prompt, mine.source, mine.key), ("integrated_multimodal_description: [Shot 1] Mine.", "user", compiled.key))

    def test_after_a_plan_change_the_compiled_prompt_is_used_and_said(self):
        result = plan(doc([{"index": 0, "key": "000000000000", "text": "old", "by": "ai"}]))
        self.assertEqual(result.compiled[0].source, "compiled")
        self.assertNotEqual(result.compiled[0].prompt, "old")
        self.assertIn("part_prompt_outdated", {issue.code for issue in result.issues})

    def test_an_answer_that_keeps_the_compiled_prompt_is_marked(self):
        facts = {"index": 0, "key": "k", "compiled": BASE.replace("Gothic hall.", LONG)}
        _, sections = part.split_sections(facts["compiled"])
        copied = "description: " + sections["integrated_multimodal_description"] + "\noverall_soundscape: ambience that fits the scene\nnon_diegetic_music: N/A"
        self.assertTrue(writer.finish(copied, facts)["unchanged"])
        self.assertFalse(writer.finish(GOOD, facts)["unchanged"])

    def test_the_writer_always_starts_from_the_compiled_prompt(self):
        compiled = plan(doc()).compiled[0]
        director = {"idea": "An elf sings.", "shots": doc([{"index": 0, "key": compiled.key, "text": "mine", "by": "user"}]),
                    "project_seconds": 8, "mode": "fl2va", "continuity": "none"}
        facts = writer.brief(director, [], 0)
        self.assertEqual((facts["compiled"], facts["key"], facts["story"]), (compiled.prompt, compiled.key, "An elf sings."))
        with self.assertRaisesRegex(ValueError, "no render part 2"):
            writer.brief(director, [], 1)


if __name__ == "__main__":
    unittest.main()
