"""Pin the previous chunk's tail into this chunk's conditioning, as never-denoised keyframe rows (experiments E2, E4, E6).

The Core's H3 layout places `minimax_keyframes` entries on the new clip's timeline. Picture steps go at their real frame offsets from
frame 0 (the head that is cut off again afterwards); the sound window ends where the pinned picture ends. Nothing here modifies ComfyUI.
"""

from ..core import pin
from ..core.chunks import ContinuityPlan
from . import latents


def _keyframes(previous, continuity, this_video):
    video, audio = latents.split_av(previous)
    latents.check_same_canvas(this_video, video)
    video_pin = pin.video_pin(continuity.video_frames, int(video.shape[2]))
    frames = [{"resolved_frame_index": offset, "latent": block}
              for offset, block in zip(video_pin.offsets, latents.video_blocks(video, video_pin))]
    if continuity.mode == "video_audio":
        audio_pin = pin.audio_pin(continuity.audio_frames, int(audio.shape[-1]), int(video.shape[2]), video_pin.span)
        frames.append({"resolved_frame_index": audio_pin.index, "audio_latent": latents.audio_tail(audio, audio_pin.steps)})
    return frames, video_pin.span


def pin_previous(conditioning, latent, previous, continuity: ContinuityPlan):
    """Returns (conditioning, trim_frames, dropped) where `dropped` lists anchors that sat inside the pinned head and were removed.

    `previous` is the AV latent of the previous chunk (None for the first chunk, or when the plan has no continuity).
    """
    if previous is None or continuity.mode == "none":
        return conditioning, 0, ()
    this_video = latents.split_av(latent)[0]
    new_frames, span = _keyframes(previous, continuity, this_video)
    out, dropped = [], []
    for embedding, extra in conditioning:
        data = extra.copy()
        kept = []
        for frame in data.get("minimax_keyframes") or []:
            (dropped if frame["resolved_frame_index"] < span else kept).append(frame)
        data["minimax_keyframes"] = kept + new_frames
        out.append([embedding, data])
    return out, span, tuple(sorted({f["resolved_frame_index"] for f in dropped}))
