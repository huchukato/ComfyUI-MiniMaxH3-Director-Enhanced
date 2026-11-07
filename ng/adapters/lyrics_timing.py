"""Time a song's lyrics with a local Whisper model (openai-whisper, model files in models/whisper)."""
import os

import av
import folder_paths
import numpy as np

from ..core import lyrics
from . import model_files
from .preview_media import require_path

try:
    import whisper
except ImportError:
    whisper = None

def model_file(chosen=""):
    """The Audio card's Models menu choice, else the largest model present: larger ones hear sung words better."""
    name = model_files.find("whisper", chosen)
    if name is None:
        raise ValueError("No Whisper model: " + model_files.missing("whisper"))
    return os.path.join(folder_paths.models_dir, "whisper", name)


def _samples(path):
    """The song as Whisper reads it, 16 kHz mono float, decoded here so no ffmpeg on PATH is needed."""
    chunks = []
    with av.open(path) as container:
        if not container.streams.audio:
            raise ValueError("Choose a source containing audio.")
        resampler = av.AudioResampler(format="flt", layout="mono", rate=whisper.audio.SAMPLE_RATE)
        for frame in container.decode(container.streams.audio[0]):
            chunks.extend(sound.to_ndarray().reshape(-1) for sound in resampler.resample(frame))
        chunks.extend(sound.to_ndarray().reshape(-1) for sound in resampler.resample(None))
    return np.concatenate(chunks).astype(np.float32) if chunks else np.zeros(0, np.float32)


def time_lyrics(source, text, device, chosen=""):
    """LRC text for the song: the user's own lines with recognised times, or what Whisper heard when no lines are given.

    `device` is the caller's choice: the GPU only while nothing renders. `chosen`: the card's Whisper file, if any."""
    if whisper is None:
        raise ValueError("Timing lyrics needs the openai-whisper package in ComfyUI's Python.")
    path = require_path(source)
    known = lyrics.plain_lines(text)
    language, _ = lyrics.parse(text)
    samples = _samples(path)
    model = whisper.load_model(model_file(chosen), device=device)
    try:
        result = model.transcribe(samples, word_timestamps=True, fp16=str(device) != "cpu",
                                  initial_prompt=" ".join(known) or None, condition_on_previous_text=False)
    finally:
        del model
    language = language or whisper.tokenizer.LANGUAGES.get(result.get("language", ""), "english").title()
    words = [(w["word"], float(w["start"]), float(w["end"])) for segment in result["segments"] for w in segment.get("words", [])]
    if known:
        lines = lyrics.align(known, words, len(samples) / float(whisper.audio.SAMPLE_RATE))
    else:
        lines = tuple(lyrics.LyricLine(round(float(s["start"]), 2), round(float(s["end"]), 2), s["text"].strip())
                      for s in result["segments"] if s["text"].strip())
    heard = len(words)
    return {"lrc": lyrics.to_lrc(language, lines), "language": language, "lines": len(lines), "heard_words": heard}
