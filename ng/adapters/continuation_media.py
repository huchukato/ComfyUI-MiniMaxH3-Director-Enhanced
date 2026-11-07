"""Selected source-video tail and synchronized audio for native H3 AddGuide."""
import math

import torch
import comfy.audio
from comfy_extras import nodes_audio

from ..core.continuation import source_end
from ..core.limits import AUDIO_HZ, FPS
from . import media, video_end
from .paths import input_path


def load(ref, item, audio_vae):
    count, end = ref.length_f, source_end(item)
    image = video_end.tail_frames(ref.source, item.options.start_s, end, count)
    if item.options.video_audio != "reference":
        return image, None
    if audio_vae is None:
        raise ValueError("Continuation sound needs the audio VAE; connect it or set Video sound to Ignore.")
    try:
        wave, rate = nodes_audio.load(input_path(ref.source))
    except (ValueError, RuntimeError, IndexError) as error:
        raise media.MediaError("The continuation video '%s' has no readable soundtrack; set Video sound to Ignore or use an audio card." % item.name) from error
    end = end or item.length_s or wave.shape[-1] / float(rate)
    start = max(item.options.start_s, end - count / float(FPS))
    first = round(start * rate)
    wave = wave[:, first:first + round((end - start) * rate)].unsqueeze(0)
    if not wave.shape[-1]:
        raise media.MediaError("The selected continuation range of '%s' has no sound; choose an earlier end or ignore its sound." % item.name)
    target_rate = getattr(audio_vae, "audio_sample_rate", 32000)
    if rate != target_rate:
        wave = comfy.audio.resample(wave, rate, target_rate)
    # A rounded 44.1 kHz boundary can resample to one extra sample. It must not
    # turn an exact 39-frame/65-hop tail into a padded 66-hop audio guide.
    wave = wave[..., :round(count / float(FPS) * target_rate)]
    # The generic VAE wrapper center-crops partial hops before the audio VAE's
    # own padding; right-pad first so shorter tails keep their true time origin.
    samples = math.ceil(wave.shape[-1] * AUDIO_HZ / target_rate) * target_rate // AUDIO_HZ
    wave = torch.nn.functional.pad(wave, (0, samples - wave.shape[-1]))
    return image, {"waveform": wave, "sample_rate": target_rate}
