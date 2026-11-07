"""Reference inputs prepared the way the released MiniMax H3 pipeline sees them, before the stock ComfyUI nodes get them.

We keep delegating to ComfyUI's own H3 nodes (see minimax_core) and never patch them. Two gaps in the stock nodes are closed
here, on our side of the call, so the result is the same on a patched and an unpatched ComfyUI:

- Qwen sizing. The stock H3 text encoder runs pictures through the shared Qwen limits (min 3136 / max 12845056 pixels), not the
  bounds of H3's released processor (pictures 65536 / 16777216, videos 4096 / 25165824 over the whole sampled reference). A
  64x64 reference got 4 vision tokens instead of 64, and a long reference video got more tokens than H3 was trained with.
  `H3Clip` resizes every picture and video frame handed to `tokenize` to exactly the size H3's processor would choose. The
  stock path then keeps that size (it is already a multiple of 32 and inside the shared limits), so the tokens match.
- Reference video window. The stock reference node cuts a reference video down to the 17k+5 frame grid but keeps the full
  soundtrack, so the sound ran past its picture. `grid_window` makes the cut itself and trims the soundtrack with it.
"""

import math

import torch
import torch.nn.functional as F

FPS = 24
FACTOR = 32                                  # Qwen patch 16 x spatial merge 2
IMAGE_BOUNDS = (65536, 16777216)             # processor/preprocessor_config.json of MiniMax-H3
VIDEO_BOUNDS = (4096, 25165824)              # processor/video_preprocessor_config.json of MiniMax-H3
STOCK_MAX_PIXELS = 12845056                  # comfy.text_encoders.qwen_vl default: a larger picture would be shrunk again


def _fit(height, width, bounds, frames=1):
    """The Qwen2-VL smart resize with H3's bounds: (h, w) as multiples of 32. For a video the bounds hold for all sampled frames
    together (the temporal patch rounds the count up to an even number)."""
    low, high = bounds
    t_bar = math.ceil(frames / 2.0) * 2 if frames > 1 else 1
    h_bar = round(height / FACTOR) * FACTOR
    w_bar = round(width / FACTOR) * FACTOR
    if t_bar * h_bar * w_bar > high:
        beta = math.sqrt((frames * height * width) / float(high))
        h_bar = max(FACTOR, math.floor(height / beta / FACTOR) * FACTOR)
        w_bar = max(FACTOR, math.floor(width / beta / FACTOR) * FACTOR)
    elif t_bar * h_bar * w_bar < low:
        beta = math.sqrt(low / float(frames * height * width))
        h_bar = math.ceil(height * beta / FACTOR) * FACTOR
        w_bar = math.ceil(width * beta / FACTOR) * FACTOR
    return h_bar, w_bar


def qwen_image_size(height, width):
    h, w = _fit(height, width, IMAGE_BOUNDS)
    if h * w > STOCK_MAX_PIXELS:             # above 12.8 MP the stock encoder shrinks anyway; land where it would
        h, w = _fit(height, width, (IMAGE_BOUNDS[0], STOCK_MAX_PIXELS))
    return h, w


def qwen_video_size(frames, height, width):
    return _fit(height, width, VIDEO_BOUNDS, frames)


def _resized(images, height, width):
    """[N, H, W, C] -> [N, height, width, 3], bilinear like the Qwen processor itself."""
    images = images[..., :3]
    if images.shape[1] == height and images.shape[2] == width:
        return images
    out = F.interpolate(images.movedim(-1, 1), size=(height, width), mode="bilinear", align_corners=False)
    return out.movedim(1, -1)


def qwen_picture(image):
    return _resized(image, *qwen_image_size(image.shape[1], image.shape[2]))


def qwen_item(item):
    """One `minimax_ref_items` entry with its picture or sampled video frames at H3's Qwen size; audio entries pass through."""
    data = item.get("data")
    if data is None or item.get("type") not in ("image", "video"):
        return item
    if item["type"] == "image":
        return dict(item, data=qwen_picture(data))
    return dict(item, data=_resized(data, *qwen_video_size(data.shape[0], data.shape[1], data.shape[2])))


class H3Clip:
    """The CLIP handed to the stock H3 nodes: `tokenize` gets every picture and video reference at H3's Qwen size, everything
    else is the wrapped CLIP itself."""

    def __init__(self, clip):
        self._clip = clip

    def __getattr__(self, name):
        return getattr(self._clip, name)

    def tokenize(self, text, *args, images=None, minimax_ref_items=None, **kwargs):
        if images is not None:
            kwargs["images"] = [qwen_picture(image) for image in images]
        if minimax_ref_items is not None:
            kwargs["minimax_ref_items"] = [qwen_item(item) for item in minimax_ref_items]
        return self._clip.tokenize(text, *args, **kwargs)


def h3_clip(clip):
    return clip if clip is None or isinstance(clip, H3Clip) else H3Clip(clip)


def chunk_frames(length):
    """Frames of a `length`-frame request on the 17k+5 grid, as the stock nodes count them."""
    n = max(5, int(length))
    return n + (5 - n) % 17


def grid_frames(count, frame_count):
    """Frames the stock reference node keeps of a `count`-frame reference video in a `frame_count`-frame chunk: at most the
    chunk, cut down to the 17k+5 grid."""
    n = min(count, frame_count)
    return n - (n - 5) % 17 if n >= 5 else n


def grid_window(frames, soundtrack, frame_count):
    """Cut a reference video to the frames the stock node keeps, and its soundtrack (or None) to the same span."""
    n = grid_frames(frames.shape[0], frame_count)
    frames = frames[:n]
    if soundtrack is not None:
        samples = int(round(n / float(FPS) * soundtrack["sample_rate"]))
        wave = soundtrack["waveform"][..., :samples]
        if wave.shape[-1] < samples:
            wave = torch.cat([wave, wave.new_zeros(*wave.shape[:-1], samples - wave.shape[-1])], dim=-1)
        soundtrack = dict(soundtrack, waveform=wave)
    return frames, soundtrack


def grid_references(ref_videos, ref_video_audios, frame_count):
    """`grid_window` over the stock node's numbered inputs: ref_video_N with its ref_video_audio_N."""
    if not ref_videos:
        return ref_videos, ref_video_audios
    videos, sounds = {}, dict(ref_video_audios or {})
    for name, frames in ref_videos.items():
        if frames is None:
            continue
        key = "ref_video_audio_" + name.rsplit("_", 1)[-1]
        videos[name], sound = grid_window(frames, sounds.get(key), frame_count)
        if sound is not None:
            sounds[key] = sound
    return videos, (sounds or None)
