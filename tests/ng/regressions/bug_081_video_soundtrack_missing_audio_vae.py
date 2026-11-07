r"""Regression test for BUG-081: Video soundtrack audio reference without audio_vae is not validated.

Where:
- ng/adapters/chunk_builder.py:39 (_reference_conditioning)

Contrast with legacy:
- minimax_director.py:679:
  if (ref_audios or ref_video_audios) and audio_vae is None:
      raise ValueError("MiniMax H3 Director: audio references need the audio VAE...")

User workflow:
1. In ComfyUI Director Studio, the user creates a Video card (e.g. 'DanceClip', dance.mp4)
   with usage=("motion",).
2. The user sets the video card option 'video_audio' to 'reference' (meaning use the video's
   soundtrack as an audio reference clip).
3. The user has no standalone Audio cards in the project.
4. The user connects clip and vae to NG Director conditioning, but leaves 'audio_vae'
   unconnected (None).
5. The user queues the prompt or executes build_chunk / NGChunkConditioning.

What happens (Ist):
In `ng/adapters/chunk_builder.py:34-45`:
```python
def _reference_conditioning(mm, job, clip, vae, audio_vae, ref_image_size):
    compiled, ctx = job.compiled, job.project.context
    pictures = [media.load_picture(r) for r in compiled.of_kind("picture")]
    videos = [media.load_video(r) for r in compiled.of_kind("video")]
    audios = [media.load_audio(r) for r in compiled.of_kind("audio")]
    if audios and audio_vae is None:
        raise ValueError("audio references need the audio VAE: connect minimax_h3_audio_vae to 'audio_vae', "
                         "or remove the voice and audio items")
    return mm.MiniMaxH3ReferenceToVideo.execute(
        clip=clip, vae=vae, audio_vae=audio_vae, prompt=compiled.prompt, width=ctx.width, height=ctx.height,
        length=job.chunk.sampled_frames, ref_image_size=ref_image_size, ref_images=media.numbered("ref_image", pictures),
        ref_videos=media.numbered("ref_video", videos), ref_video_audios=scene_guides.video_soundtracks(job), ref_audios=media.numbered("ref_audio", audios))
```
`chunk_builder.py` only checks `if audios and audio_vae is None:`.
Because `audios` is empty (`compiled.of_kind("audio")` is empty), the guard passes silently!
`MiniMaxH3ReferenceToVideo.execute` is called with `audio_vae=None` and `ref_video_audios={"ref_video_audio_1": ...}`.
Downstream in `comfy_extras/nodes_minimax_h3.py:346-350`:
```python
if soundtrack is not None and audio_vae is not None:
    audio_latent, ref_audio_t = _encode_ref_audio(audio_vae, soundtrack)
```
Because `audio_vae` is None, `audio_latent` remains None and `ref_audio_t` remains 0.
The reference block is passed as kind="video" without audio latent, while the text prompt
claims `<Audio 1>` is provided. The model receives an empty audio reference conditioning.

What should happen (Soll):
Like legacy `minimax_director.py:679`, `chunk_builder.py` must guard against missing `audio_vae`
whenever ANY audio reference is active — including paired video soundtracks:
`video_soundtracks = scene_guides.video_soundtracks(job)`
`if (audios or video_soundtracks) and audio_vae is None:`
raising `ValueError` stating that audio references need the audio VAE.

Run:
    D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe -B tests/ng/regressions/bug_081_video_soundtrack_missing_audio_vae.py
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NG_TESTS = os.path.dirname(HERE)
if NG_TESTS not in sys.path:
    sys.path.insert(0, NG_TESTS)

from _pack import comfy_available, module, stub_prompt_server  # noqa: E402

HAVE_COMFY = comfy_available()
if HAVE_COMFY:
    import torch
    from comfy.nested_tensor import NestedTensor
    stub_prompt_server()
    media = module("ng.adapters.media")
    builder = module("ng.adapters.chunk_builder")
    scene_guides = module("ng.adapters.scene_guides")

chunks = module("ng.core.chunks")
context = module("ng.core.context")
context_options = module("ng.core.context_options")
project = module("ng.core.project")

VIDEO_PLAN = chunks.ContinuityPlan("video_audio", 22, 24)


def empty_latent(frames):
    video = torch.zeros(1, 24, ((frames - 5) // 17) * 5 + 2, 4, 4)
    audio = torch.zeros(1, 32, 2, round(frames / 24.0 * 40))
    return {"samples": NestedTensor((video, audio))}


class FakeCore:
    AUDIO_LATENT_FPS = 40

    def __init__(self):
        self.calls = []
        self.ImageToVideo = self._node("frame")
        self.ReferenceToVideo = self._node("reference")

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


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class VideoSoundtrackAudioVaeTests(unittest.TestCase):
    def setUp(self):
        self._saved = (media.load_picture, media.load_audio, media.load_video)
        media.load_picture = lambda ref: torch.zeros(1, 64, 48, 3)
        media.load_audio = lambda ref: {"waveform": torch.ones(1, 2, int(44100 * ref.length_f / 24.0)), "sample_rate": 44100}
        media.load_video = lambda ref: torch.zeros(24, 32, 32, 3)

    def tearDown(self):
        media.load_picture, media.load_audio, media.load_video = self._saved

    def test_green_control_audio_vae_provided_with_video_soundtrack(self):
        """When audio_vae is provided, video soundtrack references pass cleanly to MiniMaxH3ReferenceToVideo."""
        video_item = context.ContextItem(
            id="vid_1", name="DanceClip", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(video_audio="reference")
        )
        ctx = context.DirectorContext(idea="A dance scene.", items=(video_item,))
        job = project.jobs(project.plan_project(ctx, 5, VIDEO_PLAN))[0]
        fake = FakeCore()
        audio_vae_mock = object()

        built = builder.build_chunk(job, clip=object(), vae=object(), audio_vae=audio_vae_mock, mm=fake)
        self.assertIsNotNone(built)
        name, kw = fake.calls[0]
        self.assertEqual(name, "reference")
        self.assertIs(kw["audio_vae"], audio_vae_mock)
        self.assertIn("ref_video_audio_1", kw["ref_video_audios"])

    def test_green_control_no_audio_references_without_audio_vae_succeeds(self):
        """When video_audio is 'ignore' and no audio cards exist, audio_vae=None is allowed."""
        video_item = context.ContextItem(
            id="vid_1", name="DanceClip", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(video_audio="ignore")
        )
        ctx = context.DirectorContext(idea="A dance scene.", items=(video_item,))
        job = project.jobs(project.plan_project(ctx, 5, VIDEO_PLAN))[0]
        fake = FakeCore()

        built = builder.build_chunk(job, clip=object(), vae=object(), audio_vae=None, mm=fake)
        self.assertIsNotNone(built)
        name, kw = fake.calls[0]
        self.assertEqual(name, "reference")
        self.assertIsNone(kw["audio_vae"])
        self.assertIsNone(kw["ref_video_audios"])
        self.assertIsNone(kw["ref_audios"])

    def test_green_control_standalone_audio_without_audio_vae_raises_value_error(self):
        """When a standalone audio reference is present without audio_vae, ValueError is raised."""
        alice = context.ContextItem(id="img_1", name="Alice", media="image", source="alice.png", usage=("reference",))
        voice = context.ContextItem(id="aud_1", name="Voice", media="audio", source="voice.wav", usage=("voice",), length_s=5.0)
        ctx = context.DirectorContext(idea="Alice speaking.", items=(alice, voice))
        job = project.jobs(project.plan_project(ctx, 5, VIDEO_PLAN))[0]
        fake = FakeCore()

        with self.assertRaises(ValueError) as err:
            builder.build_chunk(job, clip=object(), vae=object(), audio_vae=None, mm=fake)
        self.assertIn("audio_vae", str(err.exception))

    def test_red_defect_video_soundtrack_reference_without_audio_vae_must_raise_value_error(self):
        """BUG-081: video_audio='reference' without audio_vae must raise ValueError.

        Ist: chunk_builder._reference_conditioning only checks `if audios and audio_vae is None:`.
             Since audios (standalone audio cards) is empty, it proceeds to call
             MiniMaxH3ReferenceToVideo.execute with audio_vae=None and ref_video_audios populated.
             Upstream nodes_minimax_h3 silently drops the soundtrack latent encoding while
             the prompt declares <Audio 1>.
        Soll: chunk_builder must raise ValueError explaining that audio references need the audio VAE,
              matching legacy minimax_director.py:679.
        """
        video_item = context.ContextItem(
            id="vid_1", name="DanceClip", media="video", source="dance.mp4",
            usage=("motion",), options=context_options.ContextOptions(video_audio="reference")
        )
        ctx = context.DirectorContext(idea="A dance scene.", items=(video_item,))
        job = project.jobs(project.plan_project(ctx, 5, VIDEO_PLAN))[0]
        fake = FakeCore()

        # Under the bug, this does NOT raise ValueError, failing the test assertion.
        with self.assertRaises(ValueError) as err:
            builder.build_chunk(job, clip=object(), vae=object(), audio_vae=None, mm=fake)
        self.assertIn("audio_vae", str(err.exception))


if __name__ == "__main__":
    unittest.main()
