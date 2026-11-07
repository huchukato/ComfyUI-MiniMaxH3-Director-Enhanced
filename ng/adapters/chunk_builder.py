"""Turn one planned chunk into model conditioning: load its media, call the Core's H3 nodes, hold locked sound, pin the previous tail."""
import dataclasses
import math
from dataclasses import dataclass

import torch
import comfy.audio
import node_helpers

from ... import minimax_media as legacy
from ... import minimax_refprep as refprep
from ...minimax_core import core
from ...minimax_director import lock_audio_latent
from ..core.chunks import ContinuityPlan
from ..core.limits import FPS
from . import conditioning, media, scene_guides, continuation_latent


@dataclass(frozen=True)
class BuiltChunk:
    positive: object
    latent: dict
    trim_frames: int
    dropped_anchors: tuple


def _first_two(out):
    args = getattr(out, "args", out)
    return args[0], args[1]


def _canvas_frame(tensor, width, height, method):
    return legacy.resize_image(tensor, width, height, method, 32)


def _reference_conditioning(mm, job, clip, vae, audio_vae, ref_image_size):
    compiled, ctx = job.compiled, job.project.context
    pictures = [media.load_picture(r) for r in compiled.of_kind("picture")]
    videos = [media.load_video(r) for r in compiled.of_kind("video")]
    audios = [media.load_audio(r) for r in compiled.of_kind("audio")]
    soundtracks = scene_guides.video_soundtracks(job)
    ref_videos, soundtracks = refprep.grid_references(media.numbered("ref_video", videos), soundtracks,
                                                      refprep.chunk_frames(job.chunk.sampled_frames))
    if (audios or soundtracks) and audio_vae is None:
        raise ValueError("audio references need the audio VAE: connect minimax_h3_audio_vae to 'audio_vae', "
                         "or remove the voice and audio items")
    return mm.MiniMaxH3ReferenceToVideo.execute(
        clip=refprep.h3_clip(clip), vae=vae, audio_vae=audio_vae, prompt=compiled.prompt, width=ctx.width, height=ctx.height,
        length=job.chunk.sampled_frames, ref_image_size=ref_image_size, ref_images=media.numbered("ref_image", pictures),
        ref_videos=ref_videos, ref_video_audios=soundtracks, ref_audios=media.numbered("ref_audio", audios))


def _frame_conditioning(mm, job, clip, vae, resize_method, ref_image_size="match"):
    compiled, ctx = job.compiled, job.project.context

    def frame(kind):
        refs = compiled.of_kind(kind)
        return _canvas_frame(media.load_picture(refs[0]), ctx.width, ctx.height, resize_method) if refs else None

    first, last = frame("first_frame"), frame("last_frame")
    pictures = [media.load_picture(r) for r in compiled.of_kind("picture")]
    if pictures:
        return _frames_with_references(mm, compiled.prompt, clip, vae, ctx.width, ctx.height, job.chunk.sampled_frames, first, last,
                                       pictures, ref_image_size)
    return mm.MiniMaxH3ImageToVideo.execute(clip=refprep.h3_clip(clip), vae=vae, prompt=compiled.prompt, width=ctx.width, height=ctx.height,
                                            length=job.chunk.sampled_frames, first_frame=first, last_frame=last)


def _reference_block(mm, vae, image, width, height, ref_image_size):
    """One reference picture sized as MiniMaxH3ReferenceToVideo sizes it: (Qwen item, DiT block)."""
    h, w = image.shape[1], image.shape[2]
    if ref_image_size == "match":
        scale = min(1.0, math.sqrt((width * height) / float(w * h)))
    else:
        scale = min(1.0, mm.REF_IMAGE_SHORT_EDGE / float(min(w, h)))
    tw = max(mm.CANVAS_MULTIPLE, round(w * scale / mm.CANVAS_MULTIPLE) * mm.CANVAS_MULTIPLE)
    th = max(mm.CANVAS_MULTIPLE, round(h * scale / mm.CANVAS_MULTIPLE) * mm.CANVAS_MULTIPLE)
    resized = mm._resize(image[:1], tw, th, "disabled")
    return {"type": "image", "data": resized}, {"kind": "image", "latent_h": th // 16, "latent_w": tw // 16, "latent": vae.encode(resized)}


def _frames_with_references(mm, prompt, clip, vae, width, height, length, first, last, pictures, ref_image_size):
    """First / last frame plus reference pictures in one fl2va conditioning (ng.core.fl2va_refs). The stock fl2va node has no
    reference input, so this follows it for the frames (first frame stretched, last frame cover-cropped, both already on the
    canvas here) and MiniMaxH3ReferenceToVideo for the references. Qwen sees the frames first (<Picture 1>, <Picture 2>), the
    references after them; the DiT payload carries `minimax_keyframes` and `minimax_refs` together."""
    latent, frame_count = mm._empty_av_latent(width, height, length)
    items, keyframes = [], []
    for image, index, crop in ((first, 0, "disabled"), (last, frame_count - 1, "center")):
        if image is not None:
            image = mm._resize(image[:1], width, height, crop)
            items.append({"type": "image", "data": image})
            keyframes.append({"resolved_frame_index": index, "latent": vae.encode(image)})
    blocks = []
    for picture in pictures:
        item, block = _reference_block(mm, vae, picture, width, height, ref_image_size)
        items.append(item)
        blocks.append(block)
    cond = clip.encode_from_tokens_scheduled(refprep.h3_clip(clip).tokenize(prompt, minimax_ref_items=items))
    values = {"minimax_refs": blocks}
    if keyframes:
        values["minimax_keyframes"] = keyframes
    return node_helpers.conditioning_set_values(cond, values), latent


def _locked_waveform(locks, sampled_frames, sample_rate, steps_per_second=None):
    """All locked clips laid onto one silent track as long as the clip, at their positions.

    With `steps_per_second` (the audio latent rate) the track is padded up to whole latent steps. A chunk whose frame count
    is not a multiple of 3 (209 frames = 348.33 steps at 40/s) otherwise reached the audio VAE with a partial last step,
    and the locked song came back garbled for that whole chunk (measured: 0.3 correlation at 209 frames, 0.95 at 192/243)."""
    seconds = sampled_frames / float(FPS)
    if steps_per_second:
        seconds = math.ceil(round(seconds * steps_per_second, 6)) / float(steps_per_second)
    track = torch.zeros(1, 2, int(round(seconds * sample_rate)))
    for ref in locks:
        audio = media.load_audio(ref)
        wave = audio["waveform"]
        if audio["sample_rate"] != sample_rate:
            wave = comfy.audio.resample(wave, audio["sample_rate"], sample_rate)
        start = int(round(ref.start_f / float(FPS) * sample_rate))
        size = min(max(track.shape[-1] - start, 0), int(round(ref.length_f / float(FPS) * sample_rate)))
        piece = wave[..., :size]
        track[..., start:start + piece.shape[-1]] += piece[:, :2] if piece.shape[1] >= 2 else piece.expand(-1, 2, -1)
    return {"waveform": track.clamp(-1, 1), "sample_rate": sample_rate}


def _hold_locked_audio(mm, latent, locks, sampled_frames, audio_vae):
    if audio_vae is None:
        raise ValueError("an audio item is set to lock, which needs the audio VAE: connect minimax_h3_audio_vae to 'audio_vae'")
    # Built at the VAE's own rate, so whole latent steps are whole samples (32 kHz / 40 = 800) and no resampling rounds them.
    mix = _locked_waveform(locks, sampled_frames, getattr(audio_vae, "audio_sample_rate", legacy.AUDIO_SR), mm.AUDIO_LATENT_FPS)
    encoded, _ = mm._encode_ref_audio(audio_vae, mix)
    spans = [(r.start_f / float(FPS), (r.start_f + r.length_f) / float(FPS)) for r in locks]
    return lock_audio_latent(latent, encoded, spans, mm.AUDIO_LATENT_FPS)


def build_chunk(job, clip, vae, audio_vae=None, previous=None, ref_image_size="match", mm=None, resize_method="crop") -> BuiltChunk:
    mm = mm or core()
    compiled = job.compiled
    if compiled.mode == "ref2va":
        out = _reference_conditioning(mm, job, clip, vae, audio_vae, ref_image_size)
    else:
        out = _frame_conditioning(mm, job, clip, vae, resize_method, ref_image_size)
    positive, latent = _first_two(out)
    positive = scene_guides.apply_guides(mm, job, positive, latent, vae, audio_vae)
    continuity: ContinuityPlan = job.project.plan.continuity
    locks = compiled.of_kind("lock")
    if locks:
        latent = _hold_locked_audio(mm, latent, locks, job.chunk.sampled_frames, audio_vae)
        head_steps = math.ceil(job.chunk.head_frames / float(FPS) * mm.AUDIO_LATENT_FPS)
        if continuity.mode == "video_audio" and any(math.floor(r.start_f / float(FPS) * mm.AUDIO_LATENT_FPS) < head_steps for r in locks):
            continuity = dataclasses.replace(continuity, mode="video")       # a lock inside the head wins over audio carry
    if job.chunk.continuation_id:
        latent = continuation_latent.hold_prefix(latent, positive)
        if continuation_latent.uses_sound_prefix(job):
            latent, positive = continuation_latent.hold_sound_prefix(latent, positive)
        return BuiltChunk(positive, latent, job.chunk.head_frames, ())
    if not job.chunk.head_frames:
        return BuiltChunk(positive, latent, 0, ())
    positive, trim, dropped = conditioning.pin_previous(positive, latent, previous, continuity)
    return BuiltChunk(positive, latent, trim, dropped)
