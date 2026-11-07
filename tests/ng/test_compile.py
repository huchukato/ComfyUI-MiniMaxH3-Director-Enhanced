import unittest

from _pack import module

chunks = module("ng.core.chunks")
compile_ = module("ng.core.compile")
context = module("ng.core.context")
shots = module("ng.core.shots")
plan_mod = module("minimax_plan")

VIDEO = chunks.ContinuityPlan("video_audio", 22, 24)


def item(id_, name, media, source="", **kw):
    return context.ContextItem(id=id_, name=name, media=media, source=source or "%s.bin" % name.lower(), **kw)


def build(ctx, continuity=VIDEO, chunk_s=10):
    total = round(ctx.project_seconds * 24)
    if ctx.shots_text.strip():
        story, _ = shots.parse_shots(ctx.shots_text, total)
    else:
        story = shots.auto_shots(ctx.idea, total)
    plan = chunks.plan_chunks(total, chunk_s * 24, continuity, story)
    return plan, [compile_.compile_chunk(ctx, c, continuity) for c in plan.chunks]


ALICE = item("ctx_0001", "Alice", "image", "refs/alice.png", content=("character",), usage=("reference",),
             description="a young woman in a red coat")
VOICE = item("ctx_0002", "AliceVoice", "audio", "refs/alice.wav", content=("voice",), usage=("voice",), speaker="ctx_0001", length_s=8.0)
SCRIPT = "0-8: @Alice walks in.\n@Alice says: Hello there."


class Modes(unittest.TestCase):
    def test_idea_only_is_text_to_video(self):
        _, out = build(context.DirectorContext(idea="A woman plays with a red ball.", project_seconds=8))
        self.assertEqual(out[0].mode, "t2va")
        self.assertIn("A woman plays with a red ball.", out[0].prompt)
        self.assertEqual(out[0].refs, ())

    def test_references_switch_to_ref2va(self):
        _, out = build(context.DirectorContext(idea="Alice walks.", project_seconds=8, items=(ALICE,)))
        self.assertEqual(out[0].mode, "ref2va")
        self.assertEqual([(r.kind, r.ctx_id) for r in out[0].refs], [("picture", "ctx_0001")])

    def test_explicit_mode_wins(self):
        _, out = build(context.DirectorContext(idea="Alice walks.", project_seconds=8, items=(ALICE,), mode="fl2va"))
        self.assertEqual(out[0].mode, "t2va")
        # since 2026-10-12 a Reference picture stays a reference in fl2va (ng.core.fl2va_refs); no frame comes from it
        self.assertEqual([(r.kind, r.ctx_id) for r in out[0].refs], [("picture", "ctx_0001")])
        self.assertIn("The appearance of Alice (face, hair, outfit and props) comes from <Picture 1>", out[0].prompt)
        self.assertEqual(dict(out[0].prompt_labels)["<Picture 1>"], "ctx_0001")

    def test_first_frame_image_makes_fl2va(self):
        frame = item("ctx_0003", "Start", "image", "refs/start.png", content=("composition",), usage=("first_frame",))
        _, out = build(context.DirectorContext(idea="She turns.", project_seconds=8, items=(frame,)))
        self.assertEqual(out[0].mode, "fl2va")
        self.assertEqual([(r.kind, r.ctx_id) for r in out[0].refs], [("first_frame", "ctx_0003")])


class References(unittest.TestCase):
    def ctx(self, **kw):
        base = dict(idea="", project_seconds=8, items=(ALICE, VOICE), shots_text=SCRIPT)
        base.update(kw)
        return context.DirectorContext(**base)

    def test_names_become_subjects_and_voice_is_bound(self):
        _, out = build(self.ctx())
        prompt = out[0].prompt
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1> (S1).", prompt)
        self.assertIn("<Subject 1> (S1) says, <d>[English] Hello there.</d>", prompt)
        self.assertEqual([(r.kind, r.ctx_id) for r in out[0].refs], [("picture", "ctx_0001"), ("audio", "ctx_0002")])

    def test_tags_in_the_legacy_form_still_work(self):
        _, out = build(self.ctx(shots_text="0-8: @ref1 walks in."))
        self.assertIn("<Subject 1> walks in", out[0].prompt)

    def test_loose_voice_has_no_subject(self):
        loose = item("ctx_0004", "Narrator", "audio", "refs/n.wav", content=("voice",), usage=("voice",), length_s=6)
        _, out = build(self.ctx(items=(ALICE, loose)))
        self.assertIn("<Audio 1> is a reference audio clip", out[0].prompt)
        self.assertEqual([r.kind for r in out[0].refs], ["picture", "audio"])

    def test_voice_pointing_to_a_text_note_is_not_discarded(self):
        note = item("note", "Narrator", "text", "refs/n.wav", usage=("rule",))
        voice = item("voice", "Sound", "audio", "refs/n.wav", usage=("voice",), speaker="note", length_s=6)
        _, out = build(self.ctx(items=(note, voice)))
        self.assertEqual([(r.kind, r.ctx_id) for r in out[0].refs], [("audio", "voice")])

    def test_too_many_audio_clips_are_named(self):
        clips = tuple(item("ctx_%04d" % (10 + n), "Clip%d" % n, "audio", "refs/c%d.wav" % n, usage=("voice",), length_s=5) for n in range(4))
        _, out = build(self.ctx(items=(ALICE,) + clips))
        self.assertEqual(len(out[0].of_kind("audio")), 3)
        texts = [str(i) for i in out[0].issues]
        self.assertTrue(any("Clip3" in t or "c3.wav" in t for t in texts), texts)

    def test_style_text_reaches_the_prompt(self):
        note = item("ctx_0005", "Rules", "text", "Keep camera movement slow and physical.", usage=("style",))
        _, out = build(self.ctx(items=(ALICE, note)))
        self.assertIn("Keep camera movement slow and physical.", out[0].prompt)

    def test_prepend_text_comes_first(self):
        _, out = build(self.ctx(prepend_text="lora_trigger"))
        self.assertIn("lora_trigger", out[0].prompt)


class Chunks(unittest.TestCase):
    def test_continued_chunk_starts_inside_the_pinned_head(self):
        ctx = context.DirectorContext(idea="", items=(), project_seconds=20, shots_text="0-12: The baker kneads dough.\n12-20: The baker sits down.")
        plan, out = build(ctx)
        self.assertEqual(len(plan.chunks), 2)
        self.assertTrue(any(s.carried for s in plan.chunks[1].shots))
        self.assertIn("kneads", out[1].prompt)      # still running in the pinned head
        self.assertIn("sits down", out[1].prompt)

    def test_a_written_shot_continues_without_repeating_its_camera_move(self):
        ctx = context.DirectorContext(idea="", items=(), project_seconds=20, shots_text=(
            "0-20: The baker kneads dough. The camera pushes in slowly with small amplitude. Flour drifts in the light."))
        _, out = build(ctx)
        self.assertIn("pushes in", out[0].prompt)
        self.assertNotIn("Continue the same scene", out[0].prompt)
        self.assertNotIn("pushes in", out[1].prompt)        # the part before made the push; a second one compounds it
        self.assertIn("Continue the same scene", out[1].prompt)
        self.assertIn("Flour drifts", out[1].prompt)

    def test_a_held_camera_stays_in_a_continued_shot(self):
        ctx = context.DirectorContext(idea="", items=(), project_seconds=20, shots_text="0-20: The baker kneads dough. The camera holds a stable side view.")
        _, out = build(ctx)
        self.assertIn("stable side view", out[1].prompt)

    def test_spoken_lines_are_not_repeated_in_the_next_chunk(self):
        ctx = context.DirectorContext(idea="", items=(ALICE, VOICE), project_seconds=20,
                                      shots_text="0-12: @Alice walks through the market.\n@Alice says: Hello there.\n12-20: @Alice sits down.")
        _, out = build(ctx)
        self.assertIn("Hello there.", out[0].prompt)
        self.assertNotIn("Hello there.", out[1].prompt)
        self.assertFalse([i for i in out[1].issues if "no spoken line" in str(i)])      # absent on purpose, not a mistake
        self.assertIn("walks through the market", out[1].prompt)

    def test_lock_audio_follows_the_story_not_the_chunk(self):
        song = item("ctx_0006", "Song", "audio", "refs/song.wav", content=("music",), usage=("lock",), length_s=40)
        ctx = context.DirectorContext(idea="She sings.", project_seconds=20, items=(song,))
        plan, out = build(ctx)
        first, second = out[0].of_kind("lock"), out[1].of_kind("lock")
        self.assertEqual((first[0].trim_start_f, first[0].length_f), (0, plan.chunks[0].sampled_frames))
        expected = plan.chunks[1].story_start_f - plan.chunks[1].head_frames
        self.assertEqual(second[0].trim_start_f, expected)
        self.assertEqual(second[0].length_f, plan.chunks[1].sampled_frames)

    def test_every_chunk_gets_a_prompt(self):
        ctx = context.DirectorContext(idea="A long walk through the station.", project_seconds=60)
        plan, out = build(ctx)
        self.assertEqual(len(out), len(plan.chunks))
        self.assertTrue(all("long walk" in c.prompt for c in out))
        self.assertNotIn("Continue the same scene", out[0].prompt)
        self.assertTrue(all("Continue the same scene" in c.prompt for c in out[1:]))


class Persistence(unittest.TestCase):
    def test_compiled_chunk_roundtrip(self):
        _, out = build(context.DirectorContext(idea="", project_seconds=8, items=(ALICE, VOICE), shots_text=SCRIPT))
        self.assertEqual(compile_.CompiledChunk.from_dict(out[0].to_dict()), out[0])


class AgainstLegacy(unittest.TestCase):
    def test_same_prompt_as_a_hand_built_legacy_timeline(self):
        ctx = context.DirectorContext(idea="", project_seconds=8, items=(ALICE, VOICE), shots_text=SCRIPT)
        plan, out = build(ctx)
        legacy = {"reference_mode": "REF2VA", "prompt_format": "minimax", "global_prompt": "",
                  "segments": [{"type": "text", "start": 0, "length": 192, "prompt": "@ref1 walks in.\n@ref1 says: Hello there."}],
                  "subjects": [{"images": [{"name": "refs/alice.png"}], "description": "a young woman in a red coat", "shortName": "Alice",
                                "kind": "person", "retention": "fully_preserved", "retentionNote": "",
                                "voice": {"audioFile": "refs/alice.wav", "fileName": "AliceVoice"}}],
                  "subjectSlotCount": 1, "audioSegments": [], "overall_soundscape": "", "non_diegetic_music": "",
                  "summary": "@ref1 walks in."}         # NG writes the part's first sentence as its summary (2026-10-20)
        want = plan_mod.plan_timeline(legacy, 0, plan.chunks[0].sampled_frames, 24.0, use_custom_audio=True)
        self.assertEqual(out[0].prompt, want["prompt"])


if __name__ == "__main__":
    unittest.main()
