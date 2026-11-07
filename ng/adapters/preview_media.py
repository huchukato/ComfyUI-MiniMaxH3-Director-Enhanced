"""Bounded thumbnails and sound previews; media bytes never enter a saved workflow."""
import base64
import io
import wave

import av
import numpy as np
from PIL import Image

from .paths import input_path

PREVIEW_SECONDS = 15
AUDIO_RATE = 16000


def require_path(source):
    path = input_path(source)
    if not path:
        raise ValueError("The file is missing; upload it to ComfyUI's input folder.")
    return path


def jpeg(image):
    image = image.convert("RGB")
    image.thumbnail((512, 512))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def video_images(source):
    with av.open(require_path(source)) as container:
        if not container.streams.video:
            raise ValueError("Choose a video with a picture stream.")
        stream = container.streams.video[0]
        duration = (float(stream.duration * stream.time_base) if stream.duration and stream.time_base
                    else float(container.duration or 0) / av.time_base)
        end = min(max(0.0, duration), PREVIEW_SECONDS)
        images = []
        for seconds in (0.0, end / 2, max(0.0, end - 0.2)):
            container.seek(int(seconds * av.time_base), backward=True)
            for frame in container.decode(stream):
                if frame.time is None or frame.time >= seconds:
                    images.append(jpeg(frame.to_image()))
                    break
        if not images:
            raise ValueError("The video could not be decoded.")
        return images


def first_video_image(source):
    with av.open(require_path(source)) as container:
        if not container.streams.video:
            raise ValueError("Choose a video with a picture stream.")
        for frame in container.decode(container.streams.video[0]):
            return jpeg(frame.to_image())
    raise ValueError("The video could not be decoded.")


def audio_samples(source):
    with av.open(require_path(source)) as container:
        if not container.streams.audio:
            raise ValueError("Choose a file with an audio stream.")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=AUDIO_RATE)
        parts, count = [], 0
        limit = AUDIO_RATE * PREVIEW_SECONDS
        for frame in container.decode(container.streams.audio[0]):
            for out in resampler.resample(frame):
                samples = out.to_ndarray().reshape(-1)[:limit - count].copy()
                parts.append(samples)
                count += len(samples)
            if count >= limit:
                break
        for out in resampler.resample(None):
            parts.append(out.to_ndarray().reshape(-1)[:max(0, limit - count)].copy())
        if not parts:
            raise ValueError("The audio could not be decoded.")
        return np.concatenate(parts)[:limit]


def audio_wav(source):
    samples = audio_samples(source)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(AUDIO_RATE)
        stream.writeframes(samples.astype("<i2").tobytes())
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def preview(media, source):
    if media == "image":
        with Image.open(require_path(source)) as image:
            return {"thumbnail": "data:image/jpeg;base64," + jpeg(image)}
    if media == "video":
        return {"thumbnail": "data:image/jpeg;base64," + first_video_image(source), "frame_index": 0}
    if media == "audio":
        samples = audio_samples(source).astype(np.float32) / 32768
        peaks = [float(np.max(np.abs(part))) if len(part) else 0.0 for part in np.array_split(samples, 80)]
        return {"peaks": peaks, "sampled_seconds": round(len(samples) / AUDIO_RATE, 2)}
    raise ValueError("Choose an image, video or audio context.")
