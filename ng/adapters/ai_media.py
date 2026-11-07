"""Bounded local media for explicit native AI analysis; no temporary files or uploads."""
import base64
import io

import numpy as np
import torch
from PIL import Image

from . import preview_media


def read_media(media, source):
    if media == "audio":
        samples = preview_media.audio_samples(source).astype(np.float32) / 32768
        return None, {"waveform": torch.from_numpy(samples).reshape(1, 1, -1), "sample_rate": preview_media.AUDIO_RATE}
    if media == "video":
        encoded = preview_media.video_images(source)
        frames = [Image.open(io.BytesIO(base64.b64decode(value))).convert("RGB") for value in encoded]
    elif media == "image":
        with Image.open(preview_media.require_path(source)) as image:
            frames = [image.convert("RGB")]
            frames[0].thumbnail((1024, 1024))
    else:
        raise ValueError("Choose an image, video or audio source.")
    size = frames[0].size
    frames = [frame.resize(size) if frame.size != size else frame for frame in frames]
    return torch.from_numpy(np.stack([np.asarray(frame, dtype=np.float32) / 255 for frame in frames])), None
