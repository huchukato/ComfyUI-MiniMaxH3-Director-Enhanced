import types
import unittest

from _pack import comfy_available, module, stub_prompt_server

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    from comfy.nested_tensor import NestedTensor
    stub_prompt_server()
    media = module("ng.adapters.media")
    builder = module("ng.adapters.chunk_builder")

chunks = module("ng.core.chunks")
context = module("ng.core.context")
project = module("ng.core.project")

VIDEO = chunks.ContinuityPlan("video_audio", 22, 24)


def item(id_, name, media_, source, **kw):
    return context.ContextItem(id=id_, name=name, media=media_, source=source, **kw)


def empty_latent(frames):
    video = torch.zeros(1, 24, ((frames - 5) // 17) * 5 + 2, 4, 4)
    audio = torch.zeros(1, 32, 2, round(frames / 24.0 * 40))
    return {"samples": NestedTensor((video, audio))}


class FakeCore:
    """Stands in for comfy_extras.nodes_minimax_h3: records what it was asked and returns an empty conditioning + latent.

    The two node names are the ones `chunk_builder` really calls: MiniMaxH3ImageToVideo is the frame-guided run
    (fl2va) and MiniMaxH3ReferenceToVideo takes reference media (ref2va).
    """
    AUDIO_LATENT_FPS = 40

    def __init__(self):
        self.calls = []
        self.ImageToVideo = self._node("frame")      # MiniMaxH3ImageToVideo
        self.ReferenceToVideo = self._node("reference")  # MiniMaxH3ReferenceToVideo

    def _node(self, name):
        outer = self

        class Node:
            @staticmethod
            def execute(**kw):
                outer.calls.append((name, kw))
                return types.SimpleNamespace(args=([[torch.zeros(1, 2, 8), {}]], empty_latent(kw["length"])))
        return Node

    @property
    def MiniMaxH3ImageToVideo(self):
        return self.ImageToVideo

    @property
    def MiniMaxH3ReferenceToVideo(self):
        return self.ReferenceToVideo

    @staticmethod
    def _encode_ref_audio(_vae, mix):
        steps = round(mix["waveform"].shape[-1] / mix["sample_rate"] * 40)
        return torch.ones(1, 32, 2, steps), steps


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class Build(unittest.TestCase):
    def setUp(self):
        self.pictures = []
        self._saved = (media.load_picture, media.load_audio, media.load_video)
        media.load_picture = lambda ref: self.pictures.append(ref.source) or torch.zeros(1, 64, 48, 3)
        media.load_audio = lambda ref: {"waveform": torch.ones(1, 2, int(44100 * ref.length_f / 24.0)), "sample_rate": 44100}
        media.load_video = lambda ref: torch.zeros(24, 32, 32, 3)

    def tearDown(self):
        media.load_picture, media.load_audio, media.load_video = self._saved

    def jobs(self, ctx, seconds=12):
        ctx = context.DirectorContext.from_dict({**ctx.to_dict(), "project_seconds": seconds})
        return project.jobs(project.plan_project(ctx, 5, VIDEO))

    def test_last_frame_reaches_the_frame_conditioning(self):
        # R6: the compiled ref must actually arrive as last_frame, not only exist in the plan.
        # One chunk only, so the mode belongs to this chunk and is not mixed with the others.
        end = item("image_end", "Ende", "image", "end.png", usage=("last_frame",))
        fake = FakeCore()
        job = self.jobs(context.DirectorContext(idea="She turns.", items=(end,)), seconds=8)[-1]
        builder.build_chunk(job, clip=object(), vae=object(), mm=fake)
        name, kw = fake.calls[0]
        self.assertEqual((name, job.compiled.mode), ("frame", "fl2va"),
                         "a last frame guide needs the frame model, not the reference model")
        self.assertIsNone(kw["first_frame"])
        self.assertIsNotNone(kw["last_frame"], "the compiled last frame must reach MiniMaxH3ImageToVideo")
        self.assertEqual(tuple(kw["last_frame"].shape), (1, job.project.context.height, job.project.context.width, 3))
        self.assertEqual(self.pictures, ["end.png"], "the last frame is loaded exactly once")

    def test_only_the_final_chunk_gets_a_last_frame(self):
        end = item("image_end", "Ende", "image", "end.png", usage=("last_frame",))
        fake = FakeCore()
        jobs = self.jobs(context.DirectorContext(idea="She turns.", items=(end,)), seconds=30)
        self.assertTrue(len(jobs) > 1)
        for job in jobs[:-1]:
            builder.build_chunk(job, clip=object(), vae=object(), mm=fake)
            self.assertIsNone(fake.calls[-1][1]["last_frame"], "chunk %d must not receive it" % (job.index + 1))
        builder.build_chunk(jobs[-1], clip=object(), vae=object(), mm=fake)
        self.assertIsNotNone(fake.calls[-1][1]["last_frame"])
        self.assertEqual(self.pictures, ["end.png"], "the file is loaded once, in the chunk that uses it")

    def test_two_last_frames_send_only_the_first_one(self):
        first = item("image_a", "Ende A", "image", "a.png", usage=("last_frame",))
        second = item("image_b", "Ende B", "image", "b.png", usage=("last_frame",))
        fake = FakeCore()
        job = self.jobs(context.DirectorContext(idea="She turns.", items=(first, second)))[-1]
        builder.build_chunk(job, clip=object(), vae=object(), mm=fake)
        self.assertEqual(self.pictures, ["a.png"], "the second image must not be loaded at all")
        self.assertIn("anchor_multiple", {i.code for i in job.project.issues})

    def test_text_only_uses_the_frame_node(self):
        fake = FakeCore()
        job = self.jobs(context.DirectorContext(idea="A dog runs."))[0]
        built = builder.build_chunk(job, clip=object(), vae=object(), mm=fake)
        name, kw = fake.calls[0]
        self.assertEqual((name, kw["length"], kw["first_frame"], kw["last_frame"]), ("frame", job.chunk.sampled_frames, None, None))
        self.assertIn("A dog runs.", kw["prompt"])
        self.assertEqual((built.trim_frames, built.dropped_anchors), (0, ()))

    def test_first_frame_is_fitted_to_the_canvas(self):
        frame = item("image_start", "Start", "image", "start.png", usage=("first_frame",))
        fake = FakeCore()
        job = self.jobs(context.DirectorContext(idea="She turns.", items=(frame,), width=256, height=384))[0]
        builder.build_chunk(job, clip=object(), vae=object(), mm=fake)
        self.assertEqual(tuple(fake.calls[0][1]["first_frame"].shape), (1, 384, 256, 3))

    def test_references_go_to_the_reference_node_in_label_order(self):
        alice = item("image_alice", "Alice", "image", "alice.png", content=("character",), usage=("reference",), description="a woman")
        voice = item("audio_v", "V", "audio", "v.wav", usage=("voice",), speaker="Alice", length_s=6)
        fake = FakeCore()
        job = self.jobs(context.DirectorContext(idea="Alice talks.", items=(alice, voice)))[0]
        builder.build_chunk(job, clip=object(), vae=object(), audio_vae=object(), mm=fake)
        name, kw = fake.calls[0]
        self.assertEqual(name, "reference")
        self.assertEqual(job.compiled.mode, "ref2va")
        self.assertEqual(list(kw["ref_images"]), ["ref_image_1"])
        self.assertEqual(list(kw["ref_audios"]), ["ref_audio_1"])
        self.assertIsNone(kw["ref_videos"])

    def test_audio_reference_without_audio_vae_is_refused_with_advice(self):
        alice = item("image_alice", "Alice", "image", "alice.png", usage=("reference",))
        voice = item("audio_v", "V", "audio", "v.wav", usage=("voice",), length_s=6)
        job = self.jobs(context.DirectorContext(idea="x", items=(alice, voice)))[0]
        with self.assertRaises(ValueError) as e:
            builder.build_chunk(job, clip=object(), vae=object(), mm=FakeCore())
        self.assertIn("audio_vae", str(e.exception))

    def test_continued_chunk_pins_the_previous_tail_and_reports_the_trim(self):
        fake = FakeCore()
        jobs = self.jobs(context.DirectorContext(idea="A dog runs."), seconds=30)
        first = builder.build_chunk(jobs[0], clip=object(), vae=object(), mm=fake)
        second = builder.build_chunk(jobs[1], clip=object(), vae=object(), previous=first.latent, mm=fake)
        self.assertEqual(second.trim_frames, 22)
        frames = second.positive[0][1]["minimax_keyframes"]
        self.assertEqual((len([k for k in frames if "latent" in k]), len([k for k in frames if "audio_latent" in k])), (7, 1))

    def test_locked_audio_is_held_in_the_audio_stream_and_replaces_the_pinned_sound(self):
        song = item("audio_song", "Song", "audio", "song.wav", usage=("lock",), length_s=40)
        fake = FakeCore()
        jobs = self.jobs(context.DirectorContext(idea="She sings.", items=(song,)), seconds=30)
        first = builder.build_chunk(jobs[0], clip=object(), vae=object(), audio_vae=object(), mm=fake)
        mask = first.latent["noise_mask"].unbind()[1]
        self.assertEqual(float(mask.min()), 0.0)                       # the whole clip is locked
        second = builder.build_chunk(jobs[1], clip=object(), vae=object(), audio_vae=object(), previous=first.latent, mm=fake)
        frames = second.positive[0][1]["minimax_keyframes"]
        self.assertEqual(len([k for k in frames if "audio_latent" in k]), 0)
        self.assertEqual(len([k for k in frames if "latent" in k]), 7)

    def test_lock_without_audio_vae_is_refused(self):
        song = item("audio_song", "Song", "audio", "song.wav", usage=("lock",), length_s=40)
        job = self.jobs(context.DirectorContext(idea="x", items=(song,)))[0]
        with self.assertRaises(ValueError):
            builder.build_chunk(job, clip=object(), vae=object(), mm=FakeCore())


if __name__ == "__main__":
    unittest.main()
