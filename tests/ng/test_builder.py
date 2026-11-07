"""Make H3 prompt: the plan request from a direction and the pictures, the checked plan, and what the part writer repairs."""
import json
import os
import re
import unittest

from _pack import module

builder, directions = module("ng.core.builder"), module("ng.core.directions")
part, ctx, project, chunks = module("ng.core.part_prompt"), module("ng.core.context"), module("ng.core.project"), module("ng.core.chunks")
HERE = os.path.dirname(os.path.abspath(__file__))


def card(name, usage="reference", content="character", description="", subject_ids="", cid=None):
    return {"media": "image", "widgets": {"image": name.lower() + ".png", "name": name, "description": description,
                                          "content": content, "usage": usage, "context_id": cid or "ctx_" + name.lower(),
                                          "content_roles": json.dumps([content]), "usage_roles": json.dumps([usage]),
                                          "subject_ids": subject_ids}}


MAGE = card("Mage", description="An elf with white hair.")
HALL = card("Hall", content="environment", description="A gothic hall.")
STEPS = card("Steps", description="The elf sitting on stone steps.", subject_ids='["ctx_mage"]')
QUICK = {"direction": "music_video", "speech": "none", "language": "English"}


def answer(shots, **extra):
    return json.dumps({"look": "2D anime, dark hall.", "shots": shots, "soundscape": "Wind.", "music": "Strings.", **extra})


class Request(unittest.TestCase):
    def test_settings_fall_back_to_their_defaults(self):
        self.assertEqual(builder.read_quick({"quick": {"direction": "nope", "speech": ["x"], "language": "Klingon"}}),
                         {"direction": "auto", "speech": "none", "language": "English"})
        self.assertEqual(builder.read_quick({"quick": {"direction": "spicy", "speech": "dialogue", "language": "German"}}),
                         {"direction": "spicy", "speech": "dialogue", "language": "German"})

    def test_a_picture_or_a_request_is_needed(self):
        with self.assertRaises(ValueError):
            builder.plan_prompt(QUICK, "", 10, [])
        self.assertIn("Request: Two samurai duel.", builder.plan_prompt(QUICK, "Two samurai duel.", 10, []))

    def test_pictures_are_listed_by_their_job(self):
        text = builder.plan_prompt(QUICK, "", 25, [MAGE, HALL, STEPS], shown=2)
        self.assertIn("Pictures (the first 2 attached in this order):", text)
        self.assertIn("1. @Mage - a character: An elf with white hair.\n", text)
        self.assertIn("(not shown to you)", text.split("3. ")[1])
        self.assertIn("2. @Hall - a place or thing to use", text)
        self.assertIn('3. "Steps" - another view of @Mage', text)
        self.assertIn("@Mage, @Hall", text)  # the only @names a shot may use
        self.assertIn('"uses":[]', text)
        self.assertIn("lines is [] in every shot", text)

    def test_rule_cards_and_videos_reach_the_plan(self):
        # 2026-10-18: the AI planned without the style notes and videos that every part then got anyway.
        rule = {"media": "text", "widgets": {"name": "House style", "text": "Always anime CGI, no blood.", "usage": "style",
                                             "usage_roles": json.dumps(["style"])}}
        story = {"media": "text", "widgets": {"name": "Story", "text": "They meet at dawn.", "usage": "scene", "usage_roles": json.dumps(["scene"])}}
        camera = {"media": "video", "widgets": {"name": "Orbit", "description": "A slow orbit around a statue.", "usage": "camera",
                                                "usage_roles": json.dumps(["camera"])}}
        control = {"media": "video", "widgets": {"name": "Walk", "description": "A woman in a red coat walks.", "usage": "control",
                                                 "usage_roles": json.dumps(["control"])}}
        text = builder.plan_prompt(QUICK, "", 10, [MAGE, rule, story, camera, control], shown=1)
        self.assertIn('- "House style" (style): Always anime CGI, no blood.', text)
        self.assertNotIn('"Story"', text.split("Rules")[-1], "a Scene note is the story, not a rule")
        self.assertIn("They meet at dawn.", text)
        self.assertIn("- @Orbit - video, camera: A slow orbit around a statue.", text)
        self.assertIn("Walk - a control video", text)
        self.assertNotIn("red coat", text, "a control video's source is never described")

    def test_speech_shapes_the_example_line(self):
        song = builder.plan_prompt({**QUICK, "direction": "song", "speech": "singing"}, "", 10, [MAGE])
        self.assertIn('"lines":[{"speaker":"Mage","delivery":"sings"', song)
        self.assertIn("short original lyrics", song)
        talk = builder.plan_prompt({**QUICK, "speech": "dialogue", "language": "German"}, "", 10, [MAGE])
        self.assertIn('"delivery":"says","language":"German"', talk)

    def test_a_first_frame_starts_the_video_and_a_card_without_description_is_described(self):
        text = builder.plan_prompt(QUICK, "", 8, [card("Start", usage="first_frame")], shown=1)
        self.assertIn('The video starts exactly on "Start"', text)
        self.assertIn('"describe":{"Start":"..."}', text)
        self.assertNotIn("describe", builder.plan_prompt(QUICK, "", 8, [card("Start", usage="first_frame")], shown=0))

    def test_spicy_is_for_adults_only(self):
        with self.assertRaises(ValueError):
            builder.plan_prompt({**QUICK, "direction": "spicy"}, "A teen girl undresses.", 8, [])
        with self.assertRaises(ValueError):
            builder.plan_prompt({**QUICK, "direction": "spicy"}, "", 8, [card("Ann", description="a 16 year old student")])
        text = builder.plan_prompt({**QUICK, "direction": "spicy"}, "A woman undresses.", 8, [])
        self.assertIn("Everyone in the video is an adult", text)
        builder.plan_prompt({**QUICK, "direction": "story"}, "A teen walks home.", 8, [])  # other directions are not checked


class Plan(unittest.TestCase):
    def test_a_view_named_as_a_person_becomes_its_subject_and_is_bound(self):
        shots = [{"start_s": 0, "end_s": 5, "action": "A medium shot of @Steps sitting.", "camera": "The camera holds.", "lines": []},
                 {"start_s": 5, "end_s": 10, "action": "A wide shot of @Mage in @Hall.", "camera": "The camera pulls out.",
                  "uses": ["Hall"], "lines": [{"speaker": "Mage", "text": "No words here."}]}]
        result = builder.parse_plan(answer(shots), 10, [MAGE, HALL, STEPS], QUICK)
        data = json.loads(result["shots"])["shots"]
        self.assertIn("@Mage sitting", data[0]["text"])
        self.assertEqual([[m["context_id"] for m in s["media"]] for s in data], [["ctx_steps"], ["ctx_hall"]])
        self.assertEqual(data[1]["spoken"], [], "No speech clears the lines")

    def test_a_refusal_and_a_minor_in_the_plan_stop_spicy(self):
        with self.assertRaises(ValueError):
            builder.parse_plan(json.dumps({"refused": "minor"}), 8, [], QUICK)
        shots = [{"start_s": 0, "end_s": 8, "action": "A schoolgirl undresses.", "camera": "The camera holds."}]
        with self.assertRaises(ValueError):
            builder.parse_plan(answer(shots), 8, [], {**QUICK, "direction": "spicy"})

    def test_speakers_and_descriptions(self):
        lines = [{"speaker": "Magierin", "delivery": "says", "language": "German", "text": "Ich warte."}]
        shots = [{"start_s": 0, "end_s": 8, "action": "A close-up of @Mage.", "camera": "The camera holds.", "lines": lines}]
        quick = {**QUICK, "speech": "dialogue"}
        result = builder.parse_plan(answer(shots, describe={"Ann": "A forest at dusk."}), 8,
                                    [MAGE, card("Ann", content="environment")], quick)
        self.assertEqual(json.loads(result["shots"])["shots"][0]["spoken"][0]["speaker_id"], "ctx_mage")
        self.assertEqual(result["descriptions"], {"ctx_ann": "A forest at dusk."})
        framed = builder.parse_plan(answer(shots), 8, [card("Mage", usage="first_frame")], quick)
        line = json.loads(framed["shots"])["shots"][0]["spoken"][0]
        self.assertEqual((line["speaker_id"], line["voice"]), ("", "Mage"))


class Writer(unittest.TestCase):
    REF = ("subject_definitions:\n<Subject 1> is the elf in <Picture 1>.\n\nsummary: [reference generation]\n\n"
           "retention_analysis:\n<Subject 1>: fully_preserved - kept.\n\n"
           "detailed_description: Style. [Shot 1] <Subject 1> waves. [Shot 2] At 00:04.000, the camera cuts to her hands.\n\n"
           "overall_soundscape: wind\n\nnon_diegetic_music: N/A")
    BODY = ("Anime style, dark hall. [Shot 1] <Subject 1> stands in the hall and lifts the staff slowly while embers drift "
            "around her white hair and the candles flicker on the stone walls behind her in the dark. [Shot 2] At 00:04.000, "
            "the camera cuts to her hands closing around the staff, the gems glowing amber between her fingers.")

    def test_the_summary_is_written_after_the_planned_task_type(self):
        final, problems = part.check(self.REF, "summary: The elf waves in <Picture 1>.\ndescription: " + self.BODY)
        self.assertEqual(problems, [])
        self.assertIn("summary: [reference generation] The elf waves in <Picture 1>.", final)
        final, _ = part.check(self.REF, "summary: The elf meets <Subject 2>.\ndescription: " + self.BODY)
        self.assertIn("summary: [reference generation]\n", final, "an unknown label keeps the planned summary")

    def test_an_extra_shot_and_an_invented_line_are_repaired(self):
        extra = self.BODY + " [Shot 3] At 00:06.000, the camera cuts to a close-up of her eyes."
        final, problems = part.check(self.REF, "description: " + extra)
        self.assertEqual(problems, [])
        self.assertNotIn("[Shot 3]", final)
        self.assertIn("A close-up of her eyes.", final)
        spoken = self.BODY.replace("in the dark.", "in the dark. She sings, <d>[English] Light!</d> Then she turns.")
        final, problems = part.check(self.REF, "description: " + spoken)
        self.assertEqual(problems, [])
        self.assertNotIn("<d>", final)

    def test_a_line_without_its_language_tag_gets_it_back(self):
        compiled = self.REF.replace("waves.", "waves. <Subject 1> (S1) says, <d>[English] Hello there.</d>")
        written = self.BODY.replace("in the dark.", "in the dark. <Subject 1> (S1) says, <d>Hello there.</d>")
        final, problems = part.check(compiled, "description: " + written)
        self.assertEqual(problems, [])
        self.assertIn("<d>[English] Hello there.</d>", final)

    def test_first_and_last_frame_are_named_in_the_description(self):
        compiled = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second "
                    "mark of the target video; Picture 2 (from Shot 1) aligns with the 8.00-second mark of the target video.\n\n"
                    "integrated_multimodal_description: [Shot 1] An elf walks.\n\noverall_soundscape: wind\n\nnon_diegetic_music: N/A")
        body = ("[Shot 1] Anime style, a ruined hall. The elf walks slowly through the candlelit ruins, her white hair moving "
                "with each step while embers drift past her and the camera pushes in with small amplitude at slow speed.")
        final, problems = part.check(compiled, "description: " + body)
        self.assertEqual(problems, [])
        self.assertIn("ruined hall. The shot begins in the position and framing established by Picture 1. The elf", final)
        self.assertTrue(final.split("\n\noverall")[0].endswith("established by Picture 2."))


def plan(shots, items, seconds=20):
    data = {"format": "h3-director-shots", "schema_version": 1, "shots": shots}
    director = ctx.DirectorContext(idea="", shots_text=json.dumps(data), project_seconds=seconds, mode="ref2va", items=tuple(items))
    return project.plan_project(director, 10, chunks.ContinuityPlan("none"))


def shot(identity, start, end, text, spoken=()):
    return {"id": identity, "start": start, "end": end, "text": text, "media": [], "locked_fields": [], "draft": None,
            "spoken": [{"schema_version": 1, "text": words, "speaker_id": "mage", "language": "English"} for words in spoken]}


class Compile(unittest.TestCase):
    MAGE = ctx.ContextItem("mage", "Mage", "image", "mage.png", content=("character",))

    def test_a_figure_that_speaks_once_keeps_its_reference_in_every_part(self):
        result = plan([shot("a", 0, 10, "@Mage speaks.", ["I wait."]), shot("b", 10, 20, "@Mage turns away.")], (self.MAGE,))
        self.assertEqual([[r.ctx_id for r in c.refs] for c in result.compiled], [["mage"], ["mage"]])

    def test_a_later_shot_opens_with_the_guides_cut_words(self):
        result = plan([shot("a", 0, 4, "A medium shot of @Mage."), shot("b", 4, 8, "Close-up on her hands."),
                       shot("c", 8, 10, "@Mage turns.")], (self.MAGE,), 10)
        prompt = result.compiled[0].prompt
        self.assertIn("At 00:04.000, the camera cuts to a close-up on her hands.", prompt)
        self.assertIn("At 00:08.000, the camera cuts to a new shot. <Subject 1> turns.", prompt)

    def test_a_later_continuous_shot_does_not_get_an_automatic_cut(self):
        for text in ("@Mage turns without cutting.", "Close-up on her hands, no camera cuts.",
                     "A continuous shot of @Mage turning."):
            with self.subTest(text=text):
                result = plan([shot("a", 0, 4, "@Mage waits."), shot("b", 4, 10, text)], (self.MAGE,), 10)
                self.assertNotIn("the camera cuts", result.compiled[0].prompt)

    def test_a_global_continuous_shot_does_not_get_automatic_cuts(self):
        data = {"format": "h3-director-shots", "schema_version": 1,
                "shots": [shot("a", 0, 4, "@Mage waits."), shot("b", 4, 10, "Close-up on her hands.")]}
        rule = ctx.ContextItem("camera_rule", "Camera rule", "text", "No camera cuts.", usage=("rule",))
        context = ctx.DirectorContext(idea="", shots_text=json.dumps(data), project_seconds=10,
                                      mode="ref2va", items=(self.MAGE, rule))
        result = project.plan_project(context, 10, chunks.ContinuityPlan("none"))
        self.assertNotIn("the camera cuts", result.compiled[0].prompt)

    def test_an_explicit_cut_is_not_rewritten(self):
        text = "The camera cuts to her hands, then holds without cutting."
        result = plan([shot("a", 0, 4, "@Mage waits."), shot("b", 4, 10, text)], (self.MAGE,), 10)
        self.assertIn(text, result.compiled[0].prompt)


class Frontend(unittest.TestCase):
    def test_the_studio_offers_the_same_directions(self):
        with open(os.path.join(HERE, "..", "..", "js", "ng", "h3s_quick.js"), encoding="utf-8") as handle:
            source = handle.read()
        offered = re.findall(r'\["(\w+)", "[^"]+", "(\w+)"\]', source)
        self.assertEqual(offered, [(key, value.speech) for key, value in directions.DIRECTIONS.items()])


if __name__ == "__main__":
    unittest.main()
