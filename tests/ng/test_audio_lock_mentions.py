"""Audio locks have no native reference number; their names and source spans still matter."""
import unittest
from unittest.mock import patch

from _pack import comfy_available, module

ctx = module("ng.core.context")
opts = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


def audio(identity, role, **changes):
    return ctx.ContextItem(identity, identity, "audio", "same.wav", usage=(role,), length_s=12, **changes)


def plan(items, **changes):
    settings = dict(idea="Use @Backing under @Mage.", project_seconds=12, width=64, height=64,
                    soundscape="Room tone", music="N/A", items=tuple(items))
    settings.update(changes)
    return project.plan_project(ctx.DirectorContext(**settings), 5, chunks.ContinuityPlan("video_audio", 22, 24))


class AudioLockMentions(unittest.TestCase):
    def test_lock_name_in_idea_and_text_never_borrows_a_voice_or_soundtrack_number(self):
        mage = ctx.ContextItem("mage", "Mage", "image", "mage.png", content=("character",), usage=("reference",))
        video = ctx.ContextItem("move", "Move", "video", "move.mp4", usage=("motion",), length_s=3,
                                options=opts.ContextOptions(video_audio="reference"))
        items = [mage, video, audio("Voice", "voice", speaker="mage"),
                 audio("Backing", "lock", description="a quiet backing track.", options=opts.ContextOptions(start_s=2, end_s=7)),
                 ctx.ContextItem("text", "Rules", "text", "Keep @Voice distinct from @Backing.", usage=("rule",))]
        for compiled in plan(items).compiled:
            self.assertNotIn("@Backing", compiled.prompt)
            self.assertIn("Use a quiet backing track under <Subject 1>.", compiled.prompt)
            self.assertIn("Keep <Audio 2> distinct from a quiet backing track.", compiled.prompt)
            self.assertEqual(dict(compiled.prompt_labels)["<Audio 1>"], "move")
            self.assertEqual(dict(compiled.prompt_labels)["<Audio 2>"], "Voice")
            self.assertNotIn("<Audio 3>", compiled.prompt)
            code = "audio_lock_mention_prose" if compiled.of_kind("lock") else "audio_lock_mention_unavailable"
            self.assertIn(code, [issue.code for issue in compiled.issues])

    def test_lock_source_window_follows_the_story_and_stops_without_changing_the_selection(self):
        lock = audio("Backing", "lock", options=opts.ContextOptions(start_s=2, end_s=7))
        for mode in ("none", "video", "video_audio"):
            context = ctx.DirectorContext(idea="A walk.", project_seconds=12, items=(lock,))
            result = project.plan_project(context, 5, chunks.ContinuityPlan(mode, 22, 24))
            for chunk, compiled in zip(result.plan.chunks, result.compiled):
                base = chunk.story_start_f - chunk.head_frames
                expected = min(chunk.sampled_frames, max(0, 120 - base))
                refs = compiled.of_kind("lock")
                if expected:
                    self.assertEqual([(r.start_f, r.trim_start_f, r.length_f) for r in refs], [(0, 48 + base, expected)])
                else:
                    self.assertEqual(refs, ())
            self.assertEqual(result.context.items[0].options, lock.options)

    def test_unavailable_lock_uses_its_name_and_warns_without_inventing_audio_labels(self):
        result = plan([audio("Backing", "lock", options=opts.ContextOptions(end_s=1))], idea="Use @Backing.")
        self.assertIn("Use the locked audio.", result.compiled[0].prompt)
        for compiled in result.compiled[1:]:
            self.assertIn("Use Backing.", compiled.prompt)
            self.assertIn("audio_lock_mention_unavailable", [issue.code for issue in compiled.issues])
        self.assertTrue(all(not compiled.prompt_labels for compiled in result.compiled))

    def test_unicode_names_unknown_names_and_unmentioned_locks_keep_their_meaning(self):
        lock = audio("Große Musik", "lock")
        compiled = plan([lock], idea="Use @GROSSE MUSIK; keep @Unknown.").compiled[0]
        self.assertIn("Use the locked audio; keep @Unknown.", compiled.prompt)
        self.assertEqual([issue.ref for issue in compiled.issues if issue.code == "audio_lock_mention_prose"], ["Große Musik"])
        unmentioned = plan([lock], idea="A walk.").compiled[0]
        self.assertFalse(any(issue.code.startswith("audio_lock_mention") for issue in unmentioned.issues))

    def test_raw_prompt_and_missing_source_are_not_rewritten(self):
        raw = "My raw @Backing."
        compiled = plan([audio("Backing", "lock")], prompt_override=raw).compiled[0]
        self.assertEqual(compiled.prompt, raw)
        self.assertFalse(any(issue.code.startswith("audio_lock_mention") for issue in compiled.issues))
        missing = ctx.ContextItem("Backing", "Backing", "audio", "", usage=("lock",))
        self.assertIn("@Backing", plan([missing], idea="Use @Backing.").compiled[0].prompt)

    def test_shared_source_lock_cards_keep_separate_descriptions_and_ids(self):
        first = audio("Rain", "lock", description="soft rain", options=opts.ContextOptions(start_s=1, end_s=2))
        second = audio("Engine", "lock", description="a low engine", options=opts.ContextOptions(start_s=3, end_s=7))
        compiled = plan([first, second], idea="Use @Rain beside @Engine.").compiled[0]
        self.assertIn("Use soft rain beside a low engine.", compiled.prompt)
        self.assertEqual({ref.ctx_id for ref in compiled.of_kind("lock")}, {"Rain", "Engine"})
        self.assertEqual({issue.ref for issue in compiled.issues if issue.code == "audio_lock_mention_prose"}, {"Rain", "Engine"})

    @unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
    def test_partial_lock_mask_and_selected_waveform_yield_to_av_tail_after_lock_ends(self):
        import math
        import torch
        from test_chunk_builder import FakeCore
        builder, media = module("ng.adapters.chunk_builder"), module("ng.adapters.media")
        lock = audio("Backing", "lock", options=opts.ContextOptions(start_s=2, end_s=7))
        result = plan([lock], idea="A walk.")
        source = torch.arange(12 * 44100, dtype=torch.float32)[None, None, :] / (12 * 44100)
        mixes = []
        def loaded(ref):
            start = int(ref.trim_start_f / 24 * 44100)
            size = int(ref.length_f / 24 * 44100)
            return {"waveform": source[..., start:start + size], "sample_rate": 44100}
        def encoded(vae, mix):
            mixes.append(mix)
            steps = round(mix["waveform"].shape[-1] / 44100 * 40)
            return torch.ones(1, 32, 2, steps), steps
        previous = None
        with patch.object(media, "load_audio", side_effect=loaded), patch.object(FakeCore, "_encode_ref_audio", side_effect=encoded):
            for job in project.jobs(result):
                built = builder.build_chunk(job, object(), object(), audio_vae=object(), previous=previous, mm=FakeCore())
                keys = built.positive[0][1].get("minimax_keyframes") or []
                if job.index < 2:
                    ref = job.compiled.of_kind("lock")[0]
                    video_mask, audio_mask = built.latent["noise_mask"].unbind()
                    end = min(audio_mask.shape[-1], math.ceil(ref.length_f / 24 * 40))
                    self.assertTrue(torch.all(audio_mask[..., :end] == 0))
                    self.assertTrue(torch.all(audio_mask[..., end:] == 1))
                    self.assertTrue(torch.all(video_mask == 1))
                    self.assertAlmostEqual(float(mixes[-1]["waveform"][0, 0, 0]), int(ref.trim_start_f / 24 * 44100) / (12 * 44100), places=5)
                    self.assertFalse(any("audio_latent" in key for key in keys))
                else:
                    pins = [key["audio_latent"] for key in keys if "audio_latent" in key]
                    self.assertEqual(len(pins), 1)
                    previous_audio = previous["samples"].unbind()[1]
                    self.assertTrue(torch.equal(pins[0], previous_audio[..., -pins[0].shape[-1]:]))
                previous = built.latent
                stream = previous["samples"].unbind()[1]
                stream.copy_(torch.arange(stream.shape[-1], dtype=stream.dtype) + job.index * 1000)
        self.assertEqual(len(mixes), 2)
