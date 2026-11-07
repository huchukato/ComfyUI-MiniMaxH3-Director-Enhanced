"""Decode the control/source/mask windows together, at H3's 24 fps and render size."""
from dataclasses import dataclass

import torch
import comfy.utils

from ... import minimax_media
from ..core import control_timing
from ..core.frames import seconds_to_frames
from . import control, probe
from .paths import input_path


@dataclass(frozen=True)
class ControlFrames:
    control_video: object = None
    mask: object = None
    source_video: object = None


def _read(filename, source, count, context, limit):
    if not input_path(filename):
        raise ValueError("Control source or mask video is missing: %s" % filename)
    last = max(0, seconds_to_frames(limit) - 1) if limit else source + count - 1
    source = min(source, last)
    decoded = minimax_media.load_video_tensor(filename, source / 24.0, min(count, last - source + 1) / 24.0, out_fps=24.0,
                                              max_short_edge=min(context.width, context.height),
                                              max_pixels=context.width * context.height, strict=True)
    return comfy.utils.common_upscale(decoded.movedim(-1, 1), context.width, context.height, "bilinear", "center").movedim(1, -1)


def _place(out, decoded, start, end, cursor):
    if out is None:
        return
    if start > cursor:
        out[cursor:start] = out[cursor - 1] if cursor else decoded[0]
    indices = torch.arange(end - start).clamp(max=decoded.shape[0] - 1)
    out[start:end] = decoded[indices]


def prepare(job):
    pieces = control_timing.spans(job)
    if not pieces:
        return ControlFrames()
    context, chunk = job.project.context, job.chunk
    kinds = {context.item(clip.context_id).options.control_kind for clip, *_ in pieces}
    size = (chunk.sampled_frames, context.height, context.width)
    video = torch.zeros(*size, 3) if kinds - {"mask"} else None
    mask = torch.ones(size) if "mask" in kinds else None
    source_video = torch.zeros(*size, 3) if mask is not None else None
    first, cursor = chunk.story_start_f - chunk.head_frames, 0
    for clip, a, b, source in pieces:
        item = context.item(clip.context_id)
        options = item.options
        decoded = _read(item.source, source, b - a, context, options.end_s or item.length_s)
        is_mask = options.control_kind == "mask"
        if is_mask:
            limits = [t for t in (probe.duration_seconds(options.control_mask), options.end_s or item.length_s) if t]
            hole = _read(options.control_mask, source, b - a, context, min(limits) if limits else 0).mean(dim=-1)
            hole = control.shaped(hole, options.mask_shape, options.mask_grow)
        else:
            hole = torch.ones(1, context.height, context.width)
        blank = torch.zeros(1, context.height, context.width, 3)
        start, end = a - first, b - first
        _place(video, blank if is_mask else decoded, start, end, cursor)
        _place(mask, hole, start, end, cursor)
        _place(source_video, decoded if is_mask else blank, start, end, cursor)
        cursor = end
    for out in (video, mask, source_video):
        if out is not None and cursor < size[0]:
            out[cursor:] = out[cursor - 1]
    return ControlFrames(video, mask, source_video)
