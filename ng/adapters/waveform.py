"""Stream the whole source into a small peak envelope without retaining decoded audio."""
import av
import numpy as np

from .preview_media import require_path


def envelope(source, bins=320):
    with av.open(require_path(source)) as container:
        if not container.streams.audio:
            raise ValueError("Choose a source containing audio.")
        stream = container.streams.audio[0]
        duration = float(stream.duration * stream.time_base) if stream.duration and stream.time_base else float(container.duration or 0) / av.time_base
        if duration <= 0:
            raise ValueError("This source has no readable duration; use the audio player's timing.")
        peaks = np.zeros(bins, dtype=np.float32)
        rate = stream.codec_context.sample_rate
        channels = len(stream.codec_context.layout.channels)
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=8000)
        for frame in container.decode(stream):
            for sound in resampler.resample(frame):
                data = np.abs(sound.to_ndarray().reshape(-1))
                seconds = float(sound.pts * sound.time_base) if sound.pts is not None else 0.0
                indices = np.clip(((seconds + np.arange(len(data)) / 8000) / duration * bins).astype(int), 0, bins - 1)
                np.maximum.at(peaks, indices, data)
        return {"duration_s": duration, "sample_rate": rate, "channels": channels, "peaks": peaks.tolist()}
