"""Hold the known video prefix using H3's native per-token noise mask."""
import torch
from comfy.nested_tensor import NestedTensor

from ..core.continuation import has_locked_sound
from .latents import split_av


def uses_sound_prefix(job):
    if not job.chunk.continuation_id or job.compiled.mode != "ref2va":
        return False
    item = job.project.context.item(job.chunk.continuation_id)
    return (item.options.video_audio == "reference" and not job.compiled.of_kind("lock")
            and not has_locked_sound(job.project.context))


def hold_prefix(latent, positive):
    video, audio = split_av(latent)
    source = next(row["latent"] for row in reversed(positive[0][1].get("minimax_keyframes", ()))
                  if row.get("resolved_frame_index") == 0 and row.get("latent") is not None)
    video = video.clone()
    video[:, :, :source.shape[2]] = source.to(video)
    video_mask = torch.ones_like(video[:, :1])
    video_mask[:, :, :source.shape[2]] = 0
    audio_mask = latent["noise_mask"].unbind()[1] if "noise_mask" in latent else torch.ones_like(audio)
    return {**latent, "samples": NestedTensor((video, audio)), "noise_mask": NestedTensor((video_mask, audio_mask))}


def hold_sound_prefix(latent, positive):
    """Known target audio replaces its duplicate guide; all future audio tokens stay free."""
    source = next((row["audio_latent"] for row in reversed(positive[0][1].get("minimax_keyframes", ()))
                   if row.get("resolved_frame_index") == 0 and row.get("audio_latent") is not None), None)
    if source is None:
        return latent, positive
    video, audio = split_av(latent)
    video_mask, audio_mask = latent["noise_mask"].unbind()
    audio, audio_mask = audio.clone(), audio_mask.clone()
    audio[..., :source.shape[-1]] = source.to(audio)
    audio_mask[..., :source.shape[-1]] = 0
    copied = []
    for embedding, extra in positive:
        rows = [{key: value for key, value in row.items()
                 if key != "audio_latent" or row.get("resolved_frame_index") != 0}
                for row in extra.get("minimax_keyframes", ())]
        copied.append([embedding, {**extra, "minimax_keyframes": rows}])
    return ({**latent, "samples": NestedTensor((video, audio)),
             "noise_mask": NestedTensor((video_mask, audio_mask))}, copied)
