"""Read basic facts about an input file (its length, its stamp), without decoding it."""
import os

import av
from PIL import Image, UnidentifiedImageError

from .paths import input_path


def video_duration(container):
    stream = container.streams.video[0]
    if stream.duration is not None:
        return max(0.0, float(stream.duration * stream.time_base))
    origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else 0.0
    return max(0.0, (container.duration or 0) / float(av.time_base) - max(0.0, origin))


def duration_seconds(source):
    """Length in seconds of an audio or video file in ComfyUI's input folder; 0.0 when it cannot be found or read."""
    path = input_path(source)
    if not path:
        return 0.0
    try:
        with av.open(path) as container:
            if container.streams.video:
                return video_duration(container)
            return max(container.duration or 0, 0) / float(av.time_base)
    except (av.error.FFmpegError, OSError, ValueError):
        return 0.0


def image_size(source):
    """(width, height) of a picture in ComfyUI's input folder, read from its header; None when it cannot be read."""
    path = input_path(source)
    if not path:
        return None
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, UnidentifiedImageError):
        return None


def file_stamp(source):
    """Size and modification time of an input file, as text. ComfyUI caches a node by its inputs, so a context node must put this
    in its cache key: replacing a file under the same name then still reaches the render."""
    path = input_path(source)
    if not path:
        return "missing"
    info = os.stat(path)
    return "%d:%d" % (info.st_size, info.st_mtime_ns)
