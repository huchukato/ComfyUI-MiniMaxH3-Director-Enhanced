"""Audio-lane clips keep their own clock: story range plus source offset, independent of Shots and render chunks."""
import json
import unittest

from _pack import module

ctx, opts = module("ng.core.context"), module("ng.core.context_options")
chunks, project = module("ng.core.chunks"), module("ng.core.project")
document, issues_ = module("ng.core.shot_document"), module("ng.core.issues")


def clip(identity, context_id, start, end, mode, offset=0.0, lane="l1"):
    return {"schema_version": 1, "id": identity, "context_id": context_id, "start": start, "end": end,
            "offset": offset, "mode": mode, "lane": lane}


def text(shots=(), audio=()):
    return json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": list(shots), "audio": list(audio)})


def song(**changes):
    values = {"usage": ("music_style",), "length_s": 60, **changes}
    return ctx.ContextItem("song", "Song", "audio", "song.wav", **values)


def plan(audio, seconds=20, chunk_seconds=10, continuity="video_audio", items=None, shots=()):
    director = ctx.DirectorContext(idea="A woman walks through a station.", shots_text=text(shots, audio),
                                   items=items or (song(),), project_seconds=seconds, mode="ref2va")
    return project.plan_project(director, chunk_seconds, chunks.ContinuityPlan(continuity))


def spans(compiled, kind):
    return [(r.start_f, r.length_f, r.trim_start_f) for r in compiled.of_kind(kind)]


def expected(chunk, origin, end, offset):
    window = chunk.story_start_f - chunk.head_frames
    first, last = max(origin, window), min(end, chunk.story_end_f)
    return [(first - window, last - first, offset + first - origin)] if last > first else []


class Document(unittest.TestCase):
    def test_clips_round_trip_and_old_documents_have_none(self):
        clips = document.read_audio_clips(text(audio=[clip("a1", "song", 1.5, 9, "lock", offset=2)]))
        self.assertEqual(clips, (document.AudioClip("a1", "song", 1.5, 9.0, 2.0, "lock", "l1"),))
        self.assertEqual(document.AudioClip.from_dict(clips[0].to_dict()), clips[0])
        self.assertEqual(document.read_audio_clips("0-4: a line"), ())
        self.assertEqual(document.read_audio_clips(json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": []})), ())

    def test_invalid_clips_are_named_not_dropped(self):
        for bad in (clip("a", "song", 4, 4, "lock"), clip("a", "", 0, 4, "lock"), clip("a", "song", 0, 4, "loud"),
                    clip("a", "song", 0, 4, "lock", offset=-1)):
            with self.subTest(bad=bad), self.assertRaises(issues_.SchemaError):
                document.read_audio_clips(text(audio=[bad]))
        with self.assertRaises(issues_.SchemaError):
            document.read_audio_clips(text(audio=[clip("a", "song", 0, 4, "lock"), clip("a", "song", 5, 6, "ref")]))

    def test_a_document_with_only_clips_leaves_the_prompt_in_charge(self):
        self.assertFalse(document.has_shots(text(audio=[clip("a1", "song", 0, 4, "lock")])))
        self.assertTrue(document.has_shots("0-4: a line"))
        result = plan([clip("a1", "song", 0, 20, "lock")])
        self.assertEqual(len(result.plan.chunks[0].shots), 1)
        self.assertIn("A woman walks through a station.", result.compiled[0].prompt)
        self.assertNotIn("no_text", {i.code for i in result.issues})


class Placement(unittest.TestCase):
    def test_lock_runs_on_across_chunks_with_its_head(self):
        for mode in ("none", "video", "video_audio"):
            with self.subTest(continuity=mode):
                result = plan([clip("a1", "song", 0, 20, "lock")], continuity=mode)
                self.assertGreater(len(result.plan.chunks), 1)
                for chunk, compiled in zip(result.plan.chunks, result.compiled):
                    self.assertEqual(spans(compiled, "lock"), expected(chunk, 0, min(480, result.plan.total_frames), 0))

    def test_offset_and_late_start_pick_the_right_part_of_the_file(self):
        result = plan([clip("a1", "song", 4, 18, "lock", offset=10)])
        for chunk, compiled in zip(result.plan.chunks, result.compiled):
            self.assertEqual(spans(compiled, "lock"), expected(chunk, 96, 432, 240))

    def test_copy_is_placed_guidance_with_its_interval(self):
        result = plan([clip("a1", "song", 2, 6, "copy", offset=1)], seconds=8, chunk_seconds=10)
        self.assertEqual(spans(result.compiled[0], "audio"), [(48, 96, 24)])
        self.assertIn("partially_copy", result.compiled[0].prompt)
        self.assertIn("2.000-6.000s", result.compiled[0].prompt)

    def test_reference_clip_only_reaches_the_chunks_it_touches(self):
        result = plan([clip("a1", "song", 14, 20, "ref", offset=3)])
        touched = [bool(c.of_kind("audio")) for c in result.compiled]
        self.assertEqual(touched, [False, True])
        ref = result.compiled[1].of_kind("audio")[0]
        self.assertEqual(ref.trim_start_f, 72)
        self.assertNotIn("fully_copy", result.compiled[1].prompt)
        self.assertFalse(result.compiled[0].of_kind("lock"))

    def test_two_reference_clips_of_one_card_send_both_windows(self):
        result = plan([clip("a1", "song", 0, 2, "ref", offset=0), clip("a2", "song", 3, 5, "ref", offset=20)], seconds=8)
        self.assertEqual(sorted((r.trim_start_f, r.length_f) for r in result.compiled[0].of_kind("audio")), [(0, 48), (480, 48)])
        same = plan([clip("a1", "song", 0, 2, "ref"), clip("a2", "song", 4, 6, "ref")], seconds=8)
        self.assertEqual(len(same.compiled[0].of_kind("audio")), 1, "the same file window is sent once")

    def test_two_clips_of_one_card_keep_separate_clocks(self):
        result = plan([clip("a1", "song", 0, 3, "lock", offset=0), clip("a2", "song", 5, 8, "lock", offset=30)], seconds=8)
        self.assertEqual(spans(result.compiled[0], "lock"), [(0, 72, 0), (120, 72, 720)])

    def test_a_lane_plays_one_clip_at_a_time_and_names_an_overlap(self):
        # BUG-027: the Studio keeps clips on a lane apart; an older or edited document may not. The later clip yields the
        # overlap and goes on at its own place in the file, so the sound is never stacked on itself.
        result = plan([clip("a1", "song", 0, 6, "lock"), clip("a2", "song", 2, 8, "lock")], seconds=8)
        self.assertEqual(spans(result.compiled[0], "lock"), [(0, 144, 0), (144, 48, 96)])
        self.assertIn(("audio_clip_overlap", "a2"), {(i.code, i.ref) for i in result.issues})
        apart = plan([clip("a1", "song", 0, 6, "lock"), clip("a2", "song", 2, 8, "lock", lane="l2")], seconds=8)
        self.assertEqual(spans(apart.compiled[0], "lock"), [(0, 144, 0), (48, 144, 0)], "two lanes play together")
        self.assertNotIn("audio_clip_overlap", {i.code for i in apart.issues})

    def test_a_clip_stops_at_the_end_of_its_file(self):
        short = song(length_s=5)
        result = plan([clip("a1", "song", 0, 8, "lock", offset=2)], seconds=8, items=(short,))
        self.assertEqual(spans(result.compiled[0], "lock"), [(0, 72, 48)])

    def test_clips_past_the_end_and_unknown_cards_are_reported(self):
        result = plan([clip("a1", "song", 15, 30, "lock"), clip("a2", "song", 25, 30, "lock"), clip("a3", "gone", 0, 2, "lock")])
        codes = {(i.code, i.ref) for i in result.issues}
        self.assertIn(("audio_clip_clipped", "a1"), codes)
        self.assertIn(("audio_clip_after_end", "a2"), codes)
        self.assertIn(("audio_clip_unknown", "a3"), codes)

    def test_a_laned_card_bound_to_a_shot_plays_in_both_places(self):
        bound = {"id": "s1", "start": 5, "end": 8, "text": "She sings.", "media": [{"schema_version": 1, "context_id": "song", "role": "context"}],
                 "spoken": [], "locked_fields": [], "draft": None}
        result = plan([clip("a1", "song", 0, 3, "lock")], seconds=8, items=(song(usage=("lock",)),), shots=[bound])
        self.assertEqual(sorted(spans(result.compiled[0], "lock")), [(0, 72, 0), (120, 72, 0)], "lane clip and shot binding, each on its own clock")
        result = plan([clip("a1", "song", 0, 3, "lock")], seconds=8, items=(song(),), shots=[bound])
        self.assertEqual(spans(result.compiled[0], "lock"), [(0, 72, 0)])
        self.assertEqual(len(result.compiled[0].of_kind("audio")), 1, "the shot binding's reference reaches the chunk once")

    def test_an_offset_past_the_file_end_is_named(self):
        result = plan([clip("a1", "song", 0, 4, "lock", offset=75)], seconds=8)
        self.assertIn(("audio_clip_past_file", "a1"), {(i.code, i.ref) for i in result.issues})
        self.assertFalse(result.compiled[0].of_kind("lock"))

    def test_the_offset_is_a_second_in_the_file_not_in_the_cards_selection(self):
        trimmed = song(options=opts.ContextOptions(start_s=5, end_s=40))
        result = plan([clip("a1", "song", 2, 6, "lock", offset=10)], seconds=8, items=(trimmed,))
        self.assertEqual(spans(result.compiled[0], "lock"), [(48, 96, 240)], "file second 10, as the Studio shows")

    def test_a_shot_lock_never_doubles_the_lane_lock_of_the_same_card(self):
        bound = {"id": "s1", "start": 2, "end": 6, "text": "A", "media": [{"schema_version": 1, "context_id": "song", "role": "context"}],
                 "spoken": [], "locked_fields": [], "draft": None}
        result = plan([clip("a1", "song", 0, 4, "lock")], seconds=8, items=(song(usage=("lock",)),), shots=[bound])
        self.assertEqual(sorted(spans(result.compiled[0], "lock")), [(0, 96, 0), (96, 48, 48)],
                         "lane 0-4 s; the shot (from 2 s) only adds 4-6 s, continuing at file second 2 + 2")

    def test_a_shot_copy_role_and_a_lane_lock_both_play_without_a_false_role_warning(self):
        shot = {"id": "s1", "start": 0, "end": 6, "text": "A", "media": [{"schema_version": 1, "context_id": "song", "role": "copy"}],
                "spoken": [], "locked_fields": [], "draft": None}
        result = plan([clip("c1", "song", 0, 4, "lock")], seconds=8, shots=[shot])
        self.assertEqual(spans(result.compiled[0], "lock"), [(0, 96, 0)])
        self.assertEqual(spans(result.compiled[0], "audio"), [(96, 48, 96)],
                         "the lane clip wins where it plays; the shot's copy fills 4-6 s at its own place in the file, never doubled")
        self.assertNotIn("audio_roles", {i.code for i in result.issues})
        two_roles = song(usage=("copy", "music_style"))
        self.assertIn("audio_roles", {i.code for i in plan([clip("c1", "song", 0, 4, "lock")], seconds=8, items=(two_roles,), shots=[shot]).issues},
                      "a card that itself has two roles is still warned about")

    def test_copy_and_reference_clips_ignore_the_cards_own_selection(self):
        trimmed = song(options=opts.ContextOptions(start_s=5, end_s=12))
        for mode in ("copy", "ref"):
            with self.subTest(mode=mode):
                result = plan([clip("a1", "song", 2, 6, mode, offset=2)], seconds=8, items=(trimmed,))
                ref = result.compiled[0].of_kind("audio")[0]
                self.assertEqual((ref.trim_start_f, ref.length_f), (48, 96), "file seconds 2-6, as the Studio shows")

    def test_a_laned_card_is_not_also_sent_globally(self):
        result = plan([clip("a1", "song", 0, 4, "lock")])
        self.assertEqual([bool(c.of_kind("audio")) or bool(c.of_kind("lock")) for c in result.compiled], [True, False])


class PlainNames(unittest.TestCase):
    def test_without_reference_slots_a_mention_is_the_name_and_a_line_names_its_voice(self):
        mage = ctx.ContextItem("mage", "Mage", "image", "mage.png", usage=("reference",))
        director = ctx.DirectorContext(idea="@Mage speaks quietly.", shots_text="0-8: @Mage looks up.\n@Mage says: Welcome back, @Mage.",
                                       items=(mage,), project_seconds=8, mode="fl2va")
        prompt = project.plan_project(director, 0, chunks.ContinuityPlan("none")).compiled[0].prompt
        self.assertNotIn("@ref", prompt)
        self.assertIn("Mage looks up.", prompt)
        self.assertIn("Mage (S1) says, <d>[English] Welcome back, Mage.</d>", prompt)
        reference = project.plan_project(ctx.DirectorContext(**{**director.__dict__, "mode": "ref2va"}), 0, chunks.ContinuityPlan("none"))
        self.assertIn("<Subject 1> looks up.", reference.compiled[0].prompt)

    def test_a_sentence_that_later_contains_a_colon_is_not_a_spoken_line(self):
        mage = ctx.ContextItem("mage", "Mage", "image", "mage.png", usage=("reference",))
        director = ctx.DirectorContext(idea="@Mage speaks quietly in a warm sanctuary.", shots_text="0-8: @Mage says: Welcome back.",
                                       items=(mage,), project_seconds=8, mode="fl2va", style="Cinematic")
        prompt = project.plan_project(director, 0, chunks.ContinuityPlan("none")).compiled[0].prompt
        self.assertIn("Mage speaks quietly in a warm sanctuary. Visual style: Cinematic.", prompt, "the style's colon made the Prompt a voice line")
        self.assertNotIn("@voice(Mage) speaks", prompt)
        self.assertIn("Mage (S1) says, <d>[English] Welcome back.</d>", prompt)


if __name__ == "__main__":
    unittest.main()
