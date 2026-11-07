"""Cut tails out of H3 AV latents. Pure tensor work: no model, no VAE, no files."""
from ..core import pin
from ..core.limits import AUDIO_HZ, FPS


def split_av(latent):
    """(video [B,24,T,H,W], audio [B,32,2,A]) of an H3 AV latent dict."""
    samples = latent["samples"]
    if not getattr(samples, "is_nested", False):
        raise ValueError("expected an H3 AV latent (video and audio together), got a plain latent")
    video, audio = samples.unbind()
    return video, audio


def validate_chunk(latent, sampled_frames, label):
    """External samplers must retain both streams and the complete sampled time axis, including the pinned head."""
    video, audio = split_av(latent)
    if video.ndim != 5 or audio.ndim != 4 or video.shape[:2] != (1, 24) or audio.shape[:3] != (1, 32, 2):
        raise ValueError("%s must be one H3 AV latent: video [1,24,T,H,W] and audio [1,32,2,A]." % label)
    expected_video = pin.steps_for_frames(sampled_frames)
    expected_audio = round(sampled_frames / float(FPS) * AUDIO_HZ)
    if video.shape[2] != expected_video or audio.shape[-1] != expected_audio:
        raise ValueError("%s needs the full %d-frame AV latent (%d video / %d audio steps); return the final sampler result before trimming or decoding."
                         % (label, sampled_frames, expected_video, expected_audio))
    return video, audio


def video_blocks(video, video_pin):
    """One single-step block per pinned latent step, cut straight out of the previous clip's latent (no decode, no re-encode)."""
    first = video_pin.start_step
    return [video[:1, :, first + k:first + k + 1].clone() for k in range(video_pin.steps)]


def audio_tail(audio, steps):
    return audio[:1, ..., audio.shape[-1] - steps:].clone()


def check_same_canvas(video, previous_video):
    """Direct continuity pins require the previous and current video streams on the same canvas."""
    here, there = tuple(video.shape[3:]), tuple(previous_video.shape[3:])
    if here != there or video.shape[1] != previous_video.shape[1]:
        raise ValueError("the previous chunk was %dx%d but this one is %dx%d; return a same-resolution continuity latent to the loop "
                         "or adapt the H3 pins for this sampling stage" % (there[1] * 16, there[0] * 16, here[1] * 16, here[0] * 16))
