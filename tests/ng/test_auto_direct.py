import json
import unittest

from _pack import module

direction = module("ng.core.auto_direct")
MAGE = {"media": "image", "widgets": {"name": "Mage", "context_id": "ctx_mage"}}


def shots_of(result):
    data = json.loads(result["shots"])
    assert data["format"] == "h3-director-shots"
    return data["shots"]


class SceneSuggestion(unittest.TestCase):
    def answer(self):
        return {"look": "Dark gothic hall, cinematic anime style.",
                "shots": [{"start_s": 0, "end_s": 4, "action": "@Alice enters.", "camera": "Slow dolly", "lines": []},
                          {"start_s": 4, "end_s": 8, "action": "@Alice turns.", "camera": "Close-up",
                           "lines": [{"speaker": "Alice", "delivery": "whispers", "language": "German", "text": "Hallo."}]}],
                "soundscape": "Room tone", "music": "N/A"}

    def test_the_proposal_is_a_shot_document_with_look_camera_and_real_spoken_lines(self):
        result = direction.parse_direction("```json\n" + json.dumps(self.answer()) + "\n```", 8,
                                           [{"media": "image", "widgets": {"name": "Alice", "context_id": "ctx_a"}}])
        shots = shots_of(result)
        self.assertEqual([(s["start"], s["end"]) for s in shots], [(0, 4), (4, 8)])
        self.assertEqual(shots[0]["text"], "@Alice enters. Slow dolly.")
        self.assertEqual(shots[1]["spoken"], [{"schema_version": 1, "text": "Hallo.", "speaker_id": "ctx_a", "voice": "a narrator",
                                               "language": "German", "delivery": "whispers"}])
        self.assertEqual(result["look"], "Dark gothic hall, cinematic anime style.")
        self.assertEqual(json.loads(result["shots"])["look"], result["look"])
        self.assertEqual(result["music"], "N/A")

    def test_a_copied_example_line_without_words_is_no_line(self):
        # qwen3.5:9b, nobody speaks: it copied the example's line with "text":[] or "text":"[]" (2026-10-13).
        for text in ([], "[]", "", ["Hello there.", "Bye."]):
            answer = {"shots": [{"start_s": 0, "end_s": 8, "action": "She walks.",
                                 "lines": [{"speaker": "", "delivery": "says", "language": "English", "text": text}]}]}
            with self.subTest(text=text):
                spoken = shots_of(direction.parse_direction(json.dumps(answer), 8))[0]["spoken"]
                self.assertEqual([line["text"] for line in spoken], text if isinstance(text, list) else [])

    def test_a_long_shot_is_written_in_beats_fitted_to_its_real_length(self):
        # The user sets the shot times (5 s, 10 s, 2.5 s ...); beats are seconds from the shot's own start and are fitted to it.
        beats = [{"from_s": 0, "to_s": 4, "action": "A full-body shot of @Alice at the door", "camera": "The camera holds a static shot"},
                 {"from_s": 4, "to_s": 8, "action": "A close-up of @Alice smiling", "camera": "The camera pushes in with small amplitude at slow speed."}]
        answer = {"shots": [{"start_s": 0, "end_s": 2.5, "action": "A wide shot of the hall.", "camera": "The camera holds a static shot.",
                             "beats": beats},
                            {"start_s": 2.5, "end_s": 12.5, "action": "@Alice walks.", "camera": "", "beats": beats}]}
        shots = shots_of(direction.parse_direction(json.dumps(answer), 12.5, [{"media": "image", "widgets": {"name": "Alice"}}]))
        self.assertEqual(shots[0]["text"], "A wide shot of the hall. The camera holds a static shot.", "2.5 s: no beats")
        self.assertEqual(shots[1]["text"], "0–5s: A full-body shot of @Alice at the door. The camera holds a static shot. "
                                           "5–10s: A close-up of @Alice smiling. The camera pushes in with small amplitude at slow speed.")
        share = module("ng.core.shot_share")
        self.assertEqual(share._beats(shots[1]["text"])[1][1][:2], (5.0, 10.0), "the render parts read the beats")

    def test_unusable_beats_fall_back_to_action_and_camera(self):
        for beats in ([{"from_s": 0, "to_s": 10, "action": "One beat only."}], [{"from_s": 5, "to_s": 2, "action": "x"}, {"from_s": 0, "to_s": 1, "action": "y"}],
                      [{"from_s": 0, "to_s": 5, "action": ""}, {"from_s": 5, "to_s": 10, "action": "y"}], "0-5s: text"):
            answer = {"shots": [{"start_s": 0, "end_s": 10, "action": "She walks.", "camera": "The camera holds a static shot.", "beats": beats}]}
            with self.subTest(beats=beats):
                self.assertEqual(shots_of(direction.parse_direction(json.dumps(answer), 10))[0]["text"],
                                 "She walks. The camera holds a static shot.")

    def test_the_split_prompt_asks_for_framing_camera_and_beats(self):
        prompt = direction.direction_prompt("She walks.", 20, [])
        for words in ("begin with the framing", "holds a static shot", "with small or large amplitude", "beats", "from the shot's own start"):
            self.assertIn(words, prompt)

    def test_a_song_becomes_one_sung_line_per_line(self):
        # Elf song (2026-10-05): eight lines arrived as one "says" line and seven lines of prose.
        answer = {"shots": [{"start_s": 0, "end_s": 8, "action": "@Mage sings.", "lines": [
            {"speaker": "@Mage", "delivery": "sings", "language": "English", "text": "My master, where did your footsteps fade?\nI still wait where your shadow stayed."}]}]}
        spoken = shots_of(direction.parse_direction(json.dumps(answer), 8, [MAGE]))[0]["spoken"]
        self.assertEqual([(l["text"], l["delivery"], l["speaker_id"]) for l in spoken],
                         [("My master, where did your footsteps fade?", "sings", "ctx_mage"), ("I still wait where your shadow stayed.", "sings", "ctx_mage")])

    def test_lines_the_song_already_sings_are_not_doubled_and_odd_values_are_tamed(self):
        answer = {"shots": [{"start_s": 0, "end_s": 8, "action": "She sings.", "lines": [
            {"speaker": "", "delivery": "sings", "text": "My master, where did your footsteps fade?"},
            {"speaker": "A stranger (far away)", "delivery": "yells", "language": "Eng[lish]", "text": "Wait!"}]}]}
        sung = ((0.0, 3.5, "Song", "My master, where did your footsteps fade?"),)
        spoken = shots_of(direction.parse_direction(json.dumps(answer), 8, [], sung=sung))[0]["spoken"]
        self.assertEqual(len(spoken), 1)
        self.assertEqual((spoken[0]["voice"], spoken[0]["delivery"], spoken[0]["language"]), ("A stranger far away", "says", "Eng lish"))

    def test_the_users_own_line_replaces_the_one_the_ai_wrote_for_that_speaker(self):
        # Real gemma split: "@Mage says: Welcome back." came back as "@Mage says: Welcome... settle your spirit."
        answer = {"shots": [{"start_s": 0, "end_s": 3, "action": "The mage stands.", "lines": [{"speaker": "Mage", "text": "Welcome... settle your spirit."}]},
                            {"start_s": 3, "end_s": 8, "action": "Close up.", "lines": [{"speaker": "Mage", "text": "Find the quiet."}]}]}
        result = direction.parse_direction(json.dumps(answer), 8, [MAGE], keep="@Mage says: Welcome back.\nNarrator says: Long ago.")
        shots = shots_of(result)
        self.assertEqual([l["text"] for l in shots[0]["spoken"]], ["Welcome back."])
        self.assertEqual(shots[1]["spoken"][0]["text"], "Long ago.")
        self.assertEqual(shots[1]["spoken"][0]["speaker_id"], "")
        self.assertEqual(result["kept_dialogue"], ["Welcome back.", "Long ago."])

    def test_a_proposal_parses_as_the_studio_and_the_planner_read_it(self):
        shots = module("ng.core.shots")
        parsed, issues = shots.parse_shots(direction.parse_direction(json.dumps(self.answer()), 8)["shots"], 8 * 24)
        self.assertEqual(issues, ())
        self.assertEqual(len(parsed), 2)

    def test_invalid_times_do_not_change_the_project(self):
        # Still refused: a shot that ends before it starts or before the previous one, no number, no action.
        for change in ({"end_s": 4}, {"end_s": 3}, {"start_s": float("nan")}, {"action": ""}):
            answer = self.answer()
            answer["shots"][1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                direction.parse_direction(json.dumps(answer), 8)
        for answer in (None, "[]", '{"shots":[]}', "not json"):
            with self.assertRaises(ValueError):
                direction.parse_direction(answer, 8)

    def test_an_answer_cut_off_by_max_tokens_says_so(self):
        """512 tokens ended a real 10 s shot list mid-sentence; "not valid JSON" sent the user looking for another model."""
        whole = json.dumps(self.answer())
        for cut in (whole[:len(whole) // 2], "```json\n" + whole[:-5]):
            with self.subTest(cut=cut[-20:]), self.assertRaisesRegex(ValueError, "Raise Max tokens"):
                direction.parse_direction(cut, 8)
        with self.assertRaisesRegex(ValueError, "generative model"):
            direction.parse_direction(",,,,,,", 8)
        self.assertEqual(direction.direct_tokens(512), 2048)
        self.assertEqual(direction.direct_tokens(4096), 4096)

    def test_prompt_sends_meanings_parts_and_sung_lines_without_local_file_paths(self):
        context = {"media": "image", "widgets": {"name": "Alice", "description": "a woman", "image": "private/file.png", "usage": "reference"}}
        prompt = direction.direction_prompt("She walks.", 27, [context], "", (((0, 8.7), (8.7, 17.9), (17.9, 27.1)),
                                                                              ((0.0, 3.48, "Song", "My master, where did your footsteps fade?"),)))
        self.assertIn("Alice", prompt)
        self.assertNotIn("private/file.png", prompt)
        self.assertIn("Do not claim generation", prompt)
        self.assertIn("0-8.7 s, 8.7-17.9 s, 17.9-27.1 s", prompt)
        self.assertIn('0-3.5 s "My master, where did your footsteps fade?"', prompt)
        self.assertNotIn("rendered in separate parts", direction.direction_prompt("She walks.", 8, [context]))
        director = {"idea": "She walks.", "project_seconds": 27, "continuity": "video_audio"}
        self.assertEqual(direction.timing_hints(director, [])[0], (), "a continued part is planned around the shots, not the reverse")
        self.assertEqual(len(direction.timing_hints({**director, "continuity": "none"}, [])[0]), 3)

    def test_gaps_overlaps_and_a_short_end_are_laid_end_to_end_unknown_mentions_become_words(self):
        # Qwen3-VL 4B ended a 10 s project at 5 s; the whole proposal used to be thrown away for it.
        for change in ({"start_s": 5}, {"start_s": 3}, {"end_s": 7}, {"end_s": 9}):
            answer = self.answer(); answer["shots"][1].update(change)
            result = direction.parse_direction(json.dumps(answer), 8)
            self.assertEqual([(s["start"], s["end"]) for s in shots_of(result)], [(0, 4), (4, 8)])
            self.assertTrue(result["timing_adjusted"], change)
        self.assertNotIn("timing_adjusted", direction.parse_direction(json.dumps(self.answer()), 8))
        one = {"shots": [{"start_s": 0, "end_s": 5, "action": "She sings."}]}
        self.assertEqual([(s["start"], s["end"]) for s in shots_of(direction.parse_direction(json.dumps(one), 10))], [(0, 10)])
        past = self.answer(); past["shots"][0]["end_s"] = 12
        filled = shots_of(direction.parse_direction(json.dumps(past), 8))
        self.assertEqual([(s["start"], s["end"]) for s in filled], [(0, 8)], "a shot past the end fills it; later ones are dropped")
        # An @name of no Content becomes a plain word and is named.
        plain = direction.parse_direction(json.dumps(self.answer()), 8, [])
        self.assertEqual(shots_of(plain)[0]["text"], "Alice enters. Slow dolly.")
        self.assertEqual(plain["unknown_mentions"], ["Alice"])

    def test_context_names_with_spaces_and_prefixes_are_resolved(self):
        answer = self.answer()
        answer["shots"][0]["action"] = "@Alice Cooper enters. @Alice follows."
        contexts = [{"widgets": {"name": "Alice"}}, {"widgets": {"name": "Alice Cooper"}}]
        self.assertIn("@Alice Cooper", shots_of(direction.parse_direction(json.dumps(answer), 8, contexts))[0]["text"])
        answer["shots"][0]["action"] = "@AliceX enters. @Name waves."
        result = direction.parse_direction(json.dumps(answer), 8, contexts)
        self.assertIn("AliceX enters. Name waves.", shots_of(result)[0]["text"])
        self.assertEqual(result["unknown_mentions"], ["AliceX", "Name"])

    def test_the_prompt_names_the_mentions_it_allows_instead_of_a_placeholder(self):
        # Qwen3-VL 4B copied the instruction's "@Name" into a real answer for the user's workflow.
        alice = {"media": "image", "widgets": {"name": "Alice"}}
        for prompt in (direction.direction_prompt("She walks.", 8, [alice]),
                       direction.direction_prompt("She walks.", 8, [alice], json.dumps({"format": "h3-director-shots", "schema_version": 1,
                           "shots": [{"id": "s1", "start": 0, "end": 8, "text": "Walk.", "media": [], "spoken": [], "locked_fields": []}]}))):
            self.assertNotIn("@Name", prompt)
            self.assertIn("@Alice", prompt)
        self.assertIn("write no @ mentions", direction.direction_prompt("She walks.", 8, []))

    def test_a_document_with_only_audio_lanes_is_split_from_the_prompt(self):
        # The Studio sends its lanes along so the plan knows when the song sings; that is not an existing shot list.
        lanes = json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": [], "audio": [], "audio_lanes": ["l1"]})
        self.assertIn('"look"', direction.direction_prompt("She sings.", 8, [], lanes))


if __name__ == "__main__":
    unittest.main()
