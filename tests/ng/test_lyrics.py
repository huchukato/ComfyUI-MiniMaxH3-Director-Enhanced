"""A song's timed lyrics reach only the render part they are sung in; the Look is what every part shares.

User's 27 s elf song (2026-10-05): all eight lines were in each of the three 9 s parts, twice (Prompt and Shot), and only
the first was a sung line at all.
"""
import json
import unittest

from _pack import module

ctx, opts = module("ng.core.context"), module("ng.core.context_options")
chunks, project, lyrics = module("ng.core.chunks"), module("ng.core.project"), module("ng.core.lyrics")

SONG = """[la:English]
[00:01.00] My master, where did your footsteps fade?
[00:05.00] I still wait where your shadow stayed.
[00:09.50]
[00:12.00] The halls are cold, the candles burn,
[00:16.00] but every flame still waits for your return.
[00:21.00] You taught my hands to shape the light,
"""


def doc(shots=(), audio=(), look=None):
    data = {"format": "h3-director-shots", "schema_version": 1, "shots": list(shots), "audio": list(audio)}
    if look is not None:
        data["look"] = look
    return json.dumps(data)


def shot(identity, start, end, text="She sings in the hall."):
    return dict(id=identity, start=start, end=end, text=text, media=[], spoken=[], locked_fields=[], draft=None)


def lane(start=0.0, end=27.0, offset=0.0, mode="lock"):
    return {"schema_version": 1, "id": "c1", "context_id": "song", "start": start, "end": end, "offset": offset, "mode": mode, "lane": "l1"}


def song(text=SONG, usage=("voice",), speaker="", length=27.0):
    return ctx.ContextItem("song", "Song", "audio", "song.mp3", usage=usage, length_s=length, speaker=speaker,
                           options=opts.ContextOptions(lyrics=text))


def mage():
    return ctx.ContextItem("mage", "Mage", "image", "mage.png", usage=("reference",), content=("character",))


def plan(shots_text, items, mode="fl2va", seconds=27.0, idea="An elf mage sings a sad song."):
    director = ctx.DirectorContext(idea=idea, shots_text=shots_text, items=items, project_seconds=seconds, mode=mode)
    return project.plan_project(director, 0, chunks.ContinuityPlan("video_audio"))


class Parse(unittest.TestCase):
    def test_lines_end_at_the_next_stamp_and_a_bare_stamp_is_a_pause(self):
        language, lines = lyrics.parse(SONG)
        self.assertEqual(language, "English")
        self.assertEqual([(l.start, l.end) for l in lines][:3], [(1.0, 5.0), (5.0, 9.5), (12.0, 16.0)])
        self.assertEqual(lines[-1].end, 21.0 + lyrics.LAST_LINE_SECONDS)

    def test_lrc_roundtrip_keeps_times_and_pauses(self):
        language, lines = lyrics.parse(SONG)
        self.assertEqual(lyrics.parse(lyrics.to_lrc(language, lines)), (language, lines))

    def test_the_option_survives_the_card_json_and_old_cards_have_none(self):
        options = opts.ContextOptions(lyrics=SONG)
        self.assertEqual(opts.ContextOptions.from_dict(options.to_dict()), options)
        self.assertNotIn("lyrics", opts.ContextOptions().to_dict())


class Align(unittest.TestCase):
    # Whisper small on the user's song (2026-10-05) heard all eight lines; a misheard word must not move a line.
    WORDS = [(" My", 0.0, 0.4), (" master,", 0.4, 1.2), (" where", 1.3, 1.6), (" did", 1.6, 1.8), (" your", 1.8, 2.0),
             (" footsteps", 2.0, 2.6), (" fade?", 2.6, 3.2), (" I", 3.48, 3.6), (" still", 3.6, 4.0), (" wade", 4.0, 4.3),
             (" where", 4.3, 4.6), (" your", 4.6, 4.8), (" shadow", 4.8, 5.4), (" stayed", 5.4, 6.4)]

    def test_the_users_words_keep_the_recognised_times(self):
        lines = lyrics.align(["My master, where did your footsteps fade?", "I still wait where your shadow stayed."], self.WORDS)
        self.assertEqual([l.text for l in lines], ["My master, where did your footsteps fade?", "I still wait where your shadow stayed."])
        self.assertEqual([(l.start, l.end) for l in lines], [(0.0, 3.2), (3.48, 6.4)])

    def test_an_unheard_line_sits_between_its_neighbours(self):
        lines = lyrics.align(["My master, where did your footsteps fade?", "La la la la", "I still wait where your shadow stayed."],
                             self.WORDS)
        self.assertEqual(lines[1].start, 3.2)
        self.assertEqual(lines[1].end, 3.48)
        self.assertEqual(lines[2].start, 3.48)

    def test_lines_after_the_last_heard_one_share_the_rest_of_the_file(self):
        lines = lyrics.align(["My master, where did your footsteps fade?", "Come back to me", "through fire and rain"], self.WORDS[:7], 60.0)
        self.assertEqual([(l.start, l.end) for l in lines[1:]], [(3.2, 31.6), (31.6, 60.0)])

    def test_plain_lines_drop_stamps_language_and_blank_lines(self):
        self.assertEqual(lyrics.plain_lines(SONG)[:2], ["My master, where did your footsteps fade?", "I still wait where your shadow stayed."])
        self.assertEqual(len(lyrics.plain_lines(SONG)), 5)


class Placement(unittest.TestCase):
    def prompts(self, result):
        return [c.prompt for c in result.compiled]

    def test_each_part_sings_only_its_own_lines(self):
        result = plan(doc([shot("s1", 0, 27)], [lane()]), (song(),))
        self.assertEqual(len(result.compiled), 3)
        parts = self.prompts(result)
        first, second, third = parts
        self.assertIn("<d>[English] My master, where did your footsteps fade?</d>", first)
        self.assertIn("<d>[English] I still wait where your shadow stayed.</d>", first)
        self.assertNotIn("halls are cold", first)
        self.assertIn("<d>[English] The halls are cold, the candles burn,</d>", second)
        self.assertIn("You taught my hands", third)
        self.assertTrue(all(p.count("My master") <= 1 for p in parts))
        self.assertTrue(all("sings" in p for p in parts))

    def test_a_lane_offset_shifts_the_song_against_the_story(self):
        # The clip starts at story 8 s and plays the file from 0: "My master" (file 1-5 s) is sung at story 9-13 s.
        result = plan(doc([shot("s1", 0, 27)], [lane(start=8.0, end=27.0)]), (song(),))
        self.assertNotIn("My master", result.compiled[0].prompt)
        self.assertIn("My master", result.compiled[1].prompt)

    def test_the_singer_is_the_figure_the_voice_belongs_to(self):
        result = plan(doc([shot("s1", 0, 27, "@Mage sings in the hall.")], [lane()]), (mage(), song(speaker="mage")), mode="ref2va")
        self.assertRegex(result.compiled[0].prompt, r"<Subject 1> \(S1\) sings, <d>\[English\] My master")

    def test_in_first_last_frame_mode_the_figure_is_shown_in_the_picture_and_sings_by_name(self):
        # Elf song in FL2VA (2026-10-05): "<Picture 1> stands in a three-quarter portrait ... the singer (S1) sings".
        first = ctx.ContextItem("mage", "Mage", "image", "mage.png", usage=("first_frame",), content=("character",))
        compiled = plan(doc([shot("s1", 0, 27, "@Mage stands in the hall. @Mage looks up.")], [lane()]), (first, song(speaker="mage"))).compiled
        prompt = compiled[0].prompt
        # the 27 s shot spans several parts: each part gets its own share of the action (ng.core.shot_share, 2026-10-13)
        self.assertIn("[Shot 1] Mage, shown in <Picture 1>, stands in the hall.", prompt)
        self.assertNotIn("looks up", prompt)
        self.assertIn("Mage looks up.", compiled[-1].prompt)
        self.assertIn("Mage (S1) sings, <d>[English] My master", prompt)

    def test_a_reference_song_is_not_sung(self):
        result = plan(doc([shot("s1", 0, 27)]), (song(usage=("music_style",)),))
        self.assertNotIn("<d>", "".join(self.prompts(result)))

    def test_a_song_locked_over_the_whole_video_is_no_dulling_chain(self):
        # A full-video lock requires a file long enough to cover that video (BUG-083).
        long = plan(doc([shot("s1", 0, 177)], [lane(end=177.0)]), (song(length=177.0),), seconds=177.0)
        self.assertNotIn("audio_dulling", {i.code for i in long.issues})
        unlocked = plan(doc([shot("s1", 0, 177)], [lane(end=60.0)]), (song(length=177.0),), seconds=177.0)
        self.assertIn("audio_dulling", {i.code for i in unlocked.issues}, "generated sound after 60 s is still carried")

    def test_a_short_song_cannot_lock_sound_past_its_file_end(self):
        result = plan(doc([shot("s1", 0, 177)], [lane(end=177.0)]), (song(),), seconds=177.0)
        self.assertIn("audio_dulling", {i.code for i in result.issues})
        timing = module("ng.core.audio_timing")
        self.assertEqual(timing.locked_spans(result.context), [(0, 648)])

    def test_a_carried_shot_keeps_its_timed_lines(self):
        result = plan(doc([shot("s1", 0, 27)], [lane()]), (song(),))
        self.assertTrue(result.plan.chunks[1].shots[0].carried)
        self.assertIn("candles burn", result.compiled[1].prompt)


class Look(unittest.TestCase):
    def test_the_prompt_is_not_pasted_into_every_part_once_shots_exist(self):
        result = plan(doc([shot("s1", 0, 27)], look="Dark gothic fantasy, cinematic anime style."), ())
        for n, prompt in enumerate(c.prompt for c in result.compiled):
            self.assertNotIn("An elf mage sings a sad song.", prompt)
            go_on = "Continue the same scene and action from the preceding video, preserving the subject and setting. " if n else ""
            self.assertIn("integrated_multimodal_description: [Shot 1] Dark gothic fantasy, cinematic anime style. %sShe sings" % go_on, prompt)

    def test_a_scene_note_is_story_and_other_notes_go_into_every_part(self):
        # User (2026-10-05): the prompt in H3 Context Text was "not understood" - it was pasted, whole, into every part.
        scene = ctx.ContextItem("t1", "Song scene", "text", "She sings the whole verse: My master ...", usage=("scene",))
        rule = ctx.ContextItem("t2", "Rule", "text", "No camera cuts.", usage=("rule",))
        with_shots = plan(doc([shot("s1", 0, 27)]), (scene, rule))
        self.assertTrue(all("whole verse" not in c.prompt and "No camera cuts." in c.prompt for c in with_shots.compiled))
        without = plan("", (scene,), seconds=8.0)
        self.assertIn("whole verse", without.compiled[0].prompt, "a text-only video without shots still gets its scene")
        direct = module("ng.core.auto_direct")
        card = {"media": "text", "widgets": {"name": "Song scene", "text": "She sings the whole verse.", "usage": "scene"}}
        self.assertIn("She sings the whole verse.", direct.direction_prompt("", 27, [card]), "the split reads it with an empty Prompt")
        with self.assertRaisesRegex(ValueError, "Text card used as Scene"):
            direct.direction_prompt("", 27, [{**card, "widgets": {**card["widgets"], "usage": "rule"}}])

    def test_without_shots_the_prompt_still_carries_the_video(self):
        result = plan("", (), seconds=8.0)
        self.assertIn("[Shot 1] An elf mage sings a sad song.", result.compiled[0].prompt)

    def test_reference_mode_keeps_the_look_before_shot_one(self):
        result = plan(doc([shot("s1", 0, 8, "@Mage sings.")], look="Cinematic anime style."), (mage(),), mode="ref2va", seconds=8.0)
        self.assertIn("detailed_description: Cinematic anime style. [Shot 1]", result.compiled[0].prompt)


if __name__ == "__main__":
    unittest.main()
