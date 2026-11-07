"""The torch side of the Director's Pictures output (core/stills.py): the one-frame latent, the edit mask, the decode and
the saved files.

One H3 latent frame is a still; ComfyUI 0.41's own VAE decode turns it into the picture (it decodes a lone frame as a
clip of copies, the best of every way measured on 2026-10-19). A source picture with an edit mask is encoded into the
latent and only the masked area is sampled again; afterwards the source's own pixels go back outside a soft edge, so what
was not to change stays exactly as it was."""
import os
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

import comfy.model_management
import comfy.nested_tensor
import comfy.utils
import folder_paths

from ..core.media_ref import MediaRef
from . import media
from .paths import input_path

FOLDER = "h3-director-stills"   # in the input folder, so every Image card can choose a picture made here
AUDIO_STEPS = 2                 # the audio stream H3 samples alongside one frame
EDGE_GROW, EDGE_SOFT = 8, 12    # pixels: the mask grows by this before sampling; the paste-back fades over this


def _canvas(image, width, height):
    """A picture fitted to the canvas as the First frame would be: cover-cropped, lanczos."""
    samples = image[:1, :, :, :3].movedim(-1, 1)
    return comfy.utils.common_upscale(samples, width, height, "lanczos", "center").movedim(1, -1)


def load_mask(name, width, height):
    """The card's edit mask, white = change, as [H, W] in 0..1 on the canvas."""
    path = input_path(name)
    if not path:
        raise media.MediaError("the edit mask '%s' is not in ComfyUI's input folder" % name)
    with Image.open(path) as picture:
        gray = np.asarray(picture.convert("L"), dtype=np.float32) / 255.0
    mask = torch.from_numpy(gray)[None, None]
    mask = comfy.utils.common_upscale(mask, width, height, "bilinear", "center")
    return mask[0, 0].clamp(0, 1)


def load_source(still):
    """The still's source picture, [1, H, W, 3]."""
    return media.load_picture(MediaRef("picture", still.source_id, still.source))


def _grow(mask, pixels):
    m = mask[None, None]
    return F.max_pool2d(m, 2 * pixels + 1, stride=1, padding=pixels)[0, 0] if pixels else mask


def _soft(mask, pixels):
    """The mask grown by `pixels` and faded over as many: 1 inside, 0 where the source stays."""
    m = _grow((mask > 0.5).float(), pixels)[None, None]
    kernel = torch.ones(1, 1, 2 * pixels + 1, 2 * pixels + 1) / float((2 * pixels + 1) ** 2)
    return F.conv2d(F.pad(m, (pixels,) * 4, mode="replicate"), kernel)[0, 0].clamp(0, 1)


def still_latent(width, height, vae=None, source=None, mask=None):
    """One latent frame for the canvas. With a source and a mask: the source encoded, and a noise mask that samples only
    the (grown) masked latent cells again. Without a mask the latent is empty: the source then is a reference only."""
    device = comfy.model_management.intermediate_device()
    lh, lw = height // 16, width // 16
    audio = torch.zeros([1, 32, 2, AUDIO_STEPS], device=device)
    if source is None or mask is None:
        return {"samples": comfy.nested_tensor.NestedTensor((torch.zeros([1, 24, 1, lh, lw], device=device), audio))}
    video = vae.encode(_canvas(source, lw * 16, lh * 16)).to(device, torch.float32)
    cells = F.adaptive_max_pool2d(_grow(mask, EDGE_GROW)[None, None], (lh, lw))
    noise_mask = (cells > 0.5).float().reshape(1, 1, 1, lh, lw).to(device)
    return {"samples": comfy.nested_tensor.NestedTensor((video, audio)),
            "noise_mask": comfy.nested_tensor.NestedTensor((noise_mask, torch.ones([1, 1, 2, AUDIO_STEPS], device=device)))}


def decode(vae, latent):
    """The picture of a one-frame latent, [1, H, W, 3]."""
    video = latent["samples"].unbind()[0] if latent["samples"].is_nested else latent["samples"]
    images = vae.decode(video[:, :, :1])
    return images.reshape(-1, *images.shape[-3:])[:1].float()


def paste_back(image, source, mask):
    """The source's own pixels outside the soft edge of the mask; the sampled ones inside it."""
    height, width = image.shape[1], image.shape[2]
    keep = _canvas(source, width, height).to(image)
    soft = _soft(mask, EDGE_SOFT).to(image)[None, :, :, None]
    return keep * (1 - soft) + image * soft


def save(image, name):
    """Write the picture to input/h3-director-stills/<name>_<time>.png; returns the name an Image card uses."""
    folder = os.path.join(folder_paths.get_input_directory(), FOLDER)
    os.makedirs(folder, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    file = "%s_%s.png" % (name, stamp)
    pixels = (image[0].clamp(0, 1).cpu().numpy() * 255.0).round().astype(np.uint8)
    Image.fromarray(pixels).save(os.path.join(folder, file))
    return "%s/%s" % (FOLDER, file)
