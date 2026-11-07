"""Restore declared source audio at native sampler stages and inside output Lock spans."""
from dataclasses import dataclass

import torch
from comfy.nested_tensor import NestedTensor
from comfy.patcher_extension import WrappersMP
from comfy.utils import pack_latents, unpack_latents

from ...minimax_core import core
from ..core.limits import FPS
from . import media
from .chunk_builder import _hold_locked_audio
from .latents import validate_chunk


@dataclass(frozen=True)
class AudioLockSource:
    refs: tuple
    sampled_frames: int
    audio_vae: object

    def __call__(self, executor, *args, **kwargs):
        # OUTER_SAMPLE sees native packed latents before latent-format normalization.
        values = list(args)
        shapes = kwargs["latent_shapes"]
        if len(shapes) != 2:
            raise ValueError("Locked H3 audio needs the full AV latent at every sampler stage.")
        video, audio = unpack_latents(values[1], shapes)
        latent = {"samples": NestedTensor((video, audio))}
        validate_chunk(latent, self.sampled_frames, "Audio lock")
        held = _hold_locked_audio(core(), latent, self.refs, self.sampled_frames, self.audio_vae)
        source = held["samples"].unbind()[1].to(audio)
        video_mask, audio_mask = held["noise_mask"].unbind()
        restored = torch.where(audio_mask.to(audio.device) == 0, source, audio)
        values[1], _ = pack_latents((video, restored))
        lock_mask, _ = pack_latents((video_mask, audio_mask))
        lock_mask = lock_mask.to(values[1])
        values[4] = lock_mask if values[4] is None else values[4] * lock_mask.to(values[4])
        return executor(*values, **kwargs)


def bind_source(model, job, audio_vae):
    refs = job.compiled.of_kind("lock")
    if not refs:
        return model
    bound = model.clone()
    bound.remove_wrappers_with_key(WrappersMP.OUTER_SAMPLE, "ng_audio_lock")
    bound.add_wrapper_with_key(WrappersMP.OUTER_SAMPLE, "ng_audio_lock",
                               AudioLockSource(refs, job.chunk.sampled_frames, audio_vae))
    return bound


def restore_waveform(job, wave, sample_rate):
    """Use source samples inside Lock spans; keep decoded model sound everywhere else."""
    refs = job.compiled.of_kind("lock")
    if not refs:
        return wave
    chunk = job.chunk
    origin = round(chunk.story_start_f / float(FPS) * sample_rate)
    window_start = chunk.story_start_f - chunk.head_frames
    mix = torch.zeros_like(wave)
    covered = torch.zeros_like(wave[:, :1], dtype=torch.bool)
    for ref in refs:
        start_f = window_start + ref.start_f
        first = max(origin, round(start_f / float(FPS) * sample_rate))
        last = min(origin + wave.shape[-1], round((start_f + ref.length_f) / float(FPS) * sample_rate))
        if last <= first:
            continue
        source = media.load_audio_source(ref, sample_rate).to(wave)
        if wave.shape[1] == 1:
            source = source.mean(dim=1, keepdim=True)
        offset = round((ref.trim_start_f - start_f) / float(FPS) * sample_rate)
        source_start = first + offset
        destination = first - origin
        covered[..., destination:destination + last - first] = True
        count = min(last - first, source.shape[-1] - source_start)
        if count > 0:
            mix[..., destination:destination + count] += source[..., source_start:source_start + count]
    return torch.where(covered, mix.clamp(-1, 1), wave)
