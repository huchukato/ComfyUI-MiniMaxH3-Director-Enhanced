"""The selected video tail, preserving its actual final source frame."""
import av
import torch
from bisect import bisect_right

from ... import minimax_media as legacy
from ... import minimax_plan as plan
from .paths import input_path
from ..core.limits import FPS
from .probe import video_duration


def tail_frames(source, start_s, end_s, count):
    """Resample a bounded tail at H3's clock, including the actual final source frame."""
    path = input_path(source)
    if not path:
        raise ValueError("Choose an existing continuation video: %s" % source)
    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else (container.start_time or 0) / av.time_base
        if not end_s:
            end_s = video_duration(container)
        first = max(start_s, end_s - count / float(FPS))
        container.seek(int((origin + max(start_s, first - 1 / FPS)) / stream.time_base), stream=stream, backward=True)
        candidates, times = [], []
        for frame in container.decode(stream):
            time = float(frame.time) - origin if frame.time is not None else None
            if time is None or time < start_s - 1e-7:
                continue
            if end_s and time >= end_s - 1e-7:
                break
            if time < first - 1 / FPS:
                continue
            candidates.append(frame)
            times.append(time)
        if not candidates:
            raise ValueError("No video frame in the selected range of '%s'; choose an earlier source end or a wider range." % source)
        indices = [max(0, bisect_right(times, first + n / float(FPS) + 1e-7) - 1) for n in range(count)]
        indices[-1] = len(candidates) - 1
        width, height = legacy._decode_target_size(candidates[-1].width, candidates[-1].height, plan.REF_VIDEO_SHORT_EDGE,
                                                   int(plan.REF_VIDEO_SHORT_EDGE ** 2 * plan.REF_VIDEO_ASPECT_BUDGET))
        images = [torch.from_numpy(legacy._video_frame_array(candidates[index], width, height)) for index in indices]
    return torch.stack(images)
