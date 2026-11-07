"""Write the Place pictures (core/places.py) inside the render loop: right after a part is sampled, the frames that later
shots take their place from are decoded and saved to ComfyUI's input folder, where the later part loads them like any
picture card.

Only a window of the part is decoded: the video VAE decodes 17-frame clips of 5 steps and blends each clip with the one
before, so the window starts one clip early (as collect.delivered_pictures does for the whole video).

"clean" and "view" pictures use ComfyUI's own nodes: SAM3 Detect ("person") picks the candidate with the least person in it,
Qwen Image 2.1 (as the Storyboard builds it, js/ng/h3b_queue.js) paints a person out or paints the new view. Each model is
loaded only when it is needed; without SAM3 the frame 1 s in is used, without Qwen the picture stays as rendered. Which files:
the Director's Models menu, else the official names (adapters/model_files.py)."""
import hashlib
import logging
import os

import numpy as np
import torch
from PIL import Image

import folder_paths
import nodes
from comfy_extras.nodes_qwen import QwenImage21Cache, TextEncodeQwenImage21
from comfy_extras.nodes_sam3 import SAM3_Detect

from ..core import pin
from ..core.places import in_chunk
from . import model_files
from .collect import VAE_CLIP_FRAMES, VAE_CLIP_STEPS
from .latents import split_av

PERSON_SHARE = 0.003        # of the picture: below this nobody is in it (SAM3 leaves a few stray pixels)
REMOVE = ("Remove every person and every character from <image1> and fill in what was behind them. Keep the place, its furniture, "
          "materials, colours, light, camera and style exactly the same. No people.")
# "seen from the opposite side: the camera is ..." turned the tavern around (bar on the other side, the door beside the fireplace);
# "seen from another camera" or "a new photograph from ..." kept its layout (Qwen tests 2026-10-18, ort-test/view_try_ab.jpg)
VIEW = ("The same place as in <image1>, with exactly the same furniture, materials and light, but seen from the opposite side: the "
        "camera is %s. Same style, same lighting, cinematic film still. No people, no text.")


def path_of(place):
    return os.path.join(folder_paths.get_input_directory(), *place.source.split("/"))


def window(local_frame, total_steps):
    """(first step, stop step, index of the frame in the decoded window) for one frame of a part's sampled timeline."""
    clip = local_frame // VAE_CLIP_FRAMES
    start = max(clip - 1, 0) * VAE_CLIP_STEPS
    stop = min((clip + 1) * VAE_CLIP_STEPS + 2, total_steps)
    return start, stop, local_frame - start // VAE_CLIP_STEPS * VAE_CLIP_FRAMES


def candidate_pictures(video, local_frames, decode_video):
    """The candidate frames [N,H,W,3], from one decoded window that covers them all."""
    start, _, _ = window(min(local_frames), video.shape[2])
    _, stop, _ = window(max(local_frames), video.shape[2])
    decoded = decode_video(video[:, :, start:stop])
    if decoded.shape[0] != pin.pixel_frames(stop - start):
        raise ValueError("a place picture window of %d steps decoded to %d frames" % (stop - start, decoded.shape[0]))
    offset = start // VAE_CLIP_STEPS * VAE_CLIP_FRAMES
    return decoded[[f - offset for f in local_frames]]


def person_shares(images, models):
    """The share of each picture SAM3 sees a person in, or None without a SAM3 checkpoint."""
    checkpoint = model_files.find("sam3", models.get("sam3"))
    if checkpoint is None:
        return None
    model, clip, _ = nodes.CheckpointLoaderSimple().load_checkpoint(checkpoint)[:3]
    text = nodes.CLIPTextEncode().encode(clip, "person")[0]
    masks = SAM3_Detect.execute(model=model, image=images, conditioning=text, threshold=0.5, refine_iterations=2,
                                individual_masks=False).args[0]
    return [float(mask.float().mean()) for mask in masks]


def qwen_files(models):
    """{image, encoder, vae: file or None}."""
    return {key: model_files.find("qwen_" + key, models.get("qwen_" + key)) for key in ("image", "encoder", "vae")}


def qwen_edit(files, picture, prompt, seed):
    """Qwen Image 2.1 with `picture` as <image1>, at its shape, 25 steps Euler CFG 1 like the official template."""
    model = QwenImage21Cache.execute(model=nodes.UNETLoader().load_unet(files["image"], "default")[0], device="auto", dtype="default").args[0]
    clip = nodes.CLIPLoader().load_clip(files["encoder"], type="qwen_image")[0]
    vae = nodes.VAELoader().load_vae(files["vae"])[0]
    positive, negative, latent = TextEncodeQwenImage21.execute(clip=clip, prompt=prompt, negative_prompt="", vae=vae, resolution=1024,
                                                                images={"image_1": picture}).args
    sampled = nodes.common_ksampler(model, seed, 25, 1.0, "euler", "simple", positive, negative, latent)[0]
    return nodes.VAEDecode().decode(vae, sampled)[0][:, :, :, :3]


def picture(place, images, models):
    """The picture of one place from its candidate frames (the frame 1 s in comes first), and what was done to it."""
    if place.kind == "raw":
        return images[:1], "as rendered"
    shares = person_shares(images, models)
    best = 0 if shares is None else min(range(len(shares)), key=lambda n: (shares[n] >= PERSON_SHARE, shares[n], n))
    chosen, steps = images[best:best + 1], ["frame %d of %d" % (best + 1, len(images))]
    needs_removal = shares is not None and shares[best] >= PERSON_SHARE
    if not needs_removal and place.kind != "view":
        return chosen, ", ".join(steps + ["nobody in it" if shares is not None else "no SAM3, not checked"])
    files = qwen_files(models)
    lacking = [model_files.missing("qwen_" + key) for key, name in files.items() if name is None]
    if lacking:
        logging.warning("[H3 Director] the place picture is used as rendered: %s", " ".join(lacking))
        return chosen, ", ".join(steps + ["no Qwen Image 2.1"])
    seed = int(hashlib.sha1(place.source.encode()).hexdigest()[:8], 16)
    if needs_removal:
        chosen = qwen_edit(files, chosen, REMOVE, seed)
        steps.append("person painted out (%.0f%% of the picture)" % (shares[best] * 100))
    if place.kind == "view":
        chosen = qwen_edit(files, chosen, VIEW % (place.view or "at the other end of the place, looking back"), seed + 1)
        steps.append("new view: %s" % (place.view or "opposite side"))
    return chosen, ", ".join(steps)


def write(job, latent, decode_video, models=None):
    """Save every Place picture this part shows. Returns [(path, what was done)]. `models`: {purpose: file} chosen by the user."""
    wanted = in_chunk(job.project.places, job.chunk)
    if not wanted:
        return []
    video, _ = split_av(latent)
    written = []
    for place, local_frames in wanted:
        made, how = picture(place, candidate_pictures(video, local_frames, decode_video), models or {})
        target = path_of(place)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        pixels = (made[0].float().clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
        Image.fromarray(np.ascontiguousarray(pixels)).save(target)
        written.append((target, how))
    return written
