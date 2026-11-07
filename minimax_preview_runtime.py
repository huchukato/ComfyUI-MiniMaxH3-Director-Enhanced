"""Attached native TAEHV decoding and bounded CPU preview transport."""

import base64
import io
import logging
import threading
import time
import types
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from PIL import Image

import comfy.utils
from comfy.taesd.taehv import TAEHV
import latent_preview
import server

EVENT = "minimax_h3_preview"
MODEL_FPS = 24.0
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewOptions:
    max_resolution: int = 768
    preview_fps: float = 24.0
    jpeg_quality: int = 90
    every_n_steps: int = 1
    max_preview_overhead: int = 25
    suppress_default_preview: bool = True

    @classmethod
    def from_values(cls, values):
        return cls(
            max_resolution=max(128, min(2048, int(values.get("max_resolution", 768)))),
            preview_fps=max(1.0, min(MODEL_FPS, float(values.get("preview_fps", 24)))),
            jpeg_quality=max(50, min(100, int(values.get("jpeg_quality", 90)))),
            every_n_steps=max(1, int(values.get("every_n_steps", 1))),
            max_preview_overhead=max(0, min(100, int(values.get("max_preview_overhead", 25)))),
            suppress_default_preview=bool(values.get("suppress_default_preview", True)),
        )


def video_stream(x0, latent_shapes=None):
    if x0 is None:
        return None
    if getattr(x0, "is_nested", False):
        return x0.tensors[0]
    if getattr(x0, "ndim", None) == 5:
        return x0
    if latent_shapes and len(latent_shapes) > 1:
        return comfy.utils.unpack_latents(x0, list(latent_shapes))[0]
    return None


def resize_latent(video, max_resolution):
    """Bound spatial decoder work without changing temporal neighbours or upscaling."""
    height, width = video.shape[-2:]
    scale = min(1.0, max_resolution / (16 * max(height, width)))
    if scale == 1.0:
        return video
    size = (max(1, int(height * scale)), max(1, int(width * scale)))
    frames = video[0].movedim(1, 0)
    resized = F.interpolate(frames, size=size, mode="bilinear", align_corners=False)
    return resized.movedim(0, 1).unsqueeze(0)


def require_taehv(vae):
    stage = getattr(vae, "first_stage_model", None)
    if not isinstance(stage, TAEHV) or stage.latent_channels != 24 or stage.patch_size != 2:
        raise ValueError("Live Preview requires the connected H3-TAEHV-VAE from taeh3.safetensors; "
                         "a full video VAE is not supported.")
    return vae


def encode_frames(images, options):
    if images.ndim == 5:
        images = images[0]
    duration = len(images) / MODEL_FPS
    count = min(len(images), max(1, int(len(images) * options.preview_fps / MODEL_FPS)))
    frames = []
    for position in range(count):
        index = position * len(images) // count
        pixels = images[index].clamp(0, 1).mul(255).round().to(torch.uint8).cpu().numpy()
        image = Image.fromarray(pixels)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=options.jpeg_quality)
        frames.append(base64.b64encode(buffer.getvalue()).decode("ascii"))
    return {"frames": frames, "duration": duration, "fps": count / duration,
            "requested_fps": options.preview_fps,
            "width": int(images.shape[-2]), "height": int(images.shape[-3])}


def throttle_gap(cost_seconds, percent):
    return cost_seconds * (100 / percent - 1) if percent > 0 else 0.0


class PreviewWorker:
    """Decode on the sampler thread; one pending RGB buffer feeds a CPU JPEG worker."""

    def __init__(self, node_id, options, run_id, vae):
        self.options = options
        self.vae = require_taehv(vae)
        self.identity = {"node_id": node_id, "run_id": run_id,
                         "sequence_id": uuid.uuid4().hex, "decoder": "TAEHV", "source_fps": MODEL_FPS}
        self.condition = threading.Condition()
        self.pending = None
        self.finishing = False
        self.failed = False
        self.thread = None
        self.deadline = 0.0
        self.client_id = getattr(server.PromptServer.instance, "client_id", None)

    def send(self, data):
        server.PromptServer.instance.send_sync(EVENT, {**self.identity, **data}, self.client_id)

    def offer(self, step, x0, total_steps, latent_shapes=None):
        final = step + 1 >= total_steps
        if self.failed or self.finishing or (step % self.options.every_n_steps and not final):
            return
        if time.monotonic() < self.deadline and not final:
            return
        video = video_stream(x0, latent_shapes)
        if video is None or video.ndim != 5 or video.shape[1] != 24 or any(size <= 0 for size in video.shape):
            return
        start = time.monotonic()
        self.send({"status": "Updating TAEHV…", "step": int(step) + 1, "total_steps": int(total_steps)})
        # Native VAE.decode owns device/dtype/offload. Keep it on the sampler thread:
        # model management must not run concurrently with the active H3 DiT.
        images = self.vae.decode(resize_latent(video[:1].detach(), self.options.max_resolution))
        snapshot = images.detach().to(device="cpu", copy=True)
        cost = time.monotonic() - start
        with self.condition:
            self.pending = (snapshot, int(step) + 1, int(total_steps), cost)
            self.deadline = time.monotonic() + throttle_gap(cost, self.options.max_preview_overhead)
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, name="H3-TAEHV-preview", daemon=True)
                self.thread.start()
            self.condition.notify()

    def next_snapshot(self):
        with self.condition:
            while not self.finishing and self.pending is None:
                self.condition.wait()
            snapshot, self.pending = self.pending, None
            return snapshot

    def run(self):
        try:
            while (snapshot := self.next_snapshot()) is not None:
                start = time.monotonic()
                images, step, total_steps, decode_cost = snapshot
                data = encode_frames(images, self.options)
                cost = decode_cost + time.monotonic() - start
                self.send({**data, "step": step, "total_steps": total_steps, "ms": round(cost * 1000)})
                with self.condition:
                    self.deadline = max(self.deadline, time.monotonic() + throttle_gap(cost, self.options.max_preview_overhead))
                del images, snapshot
        except Exception as error:
            self.failed = True
            log.warning("[MiniMaxDirector] TAEHV preview failed: %s", error, exc_info=True)
            self.send({"error": str(error), "status": "TAEHV preview unavailable"})
        finally:
            with self.condition:
                self.pending = None

    def finish(self, cancel=False):
        with self.condition:
            self.finishing = True
            if cancel:
                self.pending = None
            self.condition.notify()
        if self.thread is not None:
            self.thread.join()
        self.thread = None
        self.vae = None


def callback_previewers(callback):
    """Find only this callback's native preview instance, including Comfy's AV wrapper."""
    pending, seen = [callback], set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, latent_preview.LatentPreviewer):
            yield item
        elif isinstance(item, types.FunctionType):
            for cell in item.__closure__ or ():
                try:
                    pending.append(cell.cell_contents)
                except ValueError:
                    pass


@contextmanager
def suppress_preview(callback, suppress):
    saved = []
    if suppress:
        for previewer in callback_previewers(callback):
            name = "decode_latent_to_preview_image"
            saved.append((previewer, name, previewer.__dict__.get(name)))
            setattr(previewer, name, lambda *args, **kwargs: None)
    try:
        yield
    finally:
        for previewer, name, original in saved:
            if original is None:
                delattr(previewer, name)
            else:
                setattr(previewer, name, original)


class OuterSamplePreview:
    def __init__(self, node_id, options, vae):
        self.node_id = node_id
        self.options = options
        self.vae = require_taehv(vae)
        self.run_id = uuid.uuid4().hex

    def __call__(self, executor, noise, latent_image, sampler, sigmas, denoise_mask,
                 callback, disable_pbar, seed, **kwargs):
        worker = PreviewWorker(self.node_id, self.options, self.run_id, self.vae)
        shapes = kwargs.get("latent_shapes")

        def combined(step, x0, x, total_steps):
            try:
                worker.offer(step, x0, total_steps, shapes)
            except Exception as error:
                if not worker.failed:
                    worker.failed = True
                    log.warning("[MiniMaxDirector] TAEHV snapshot failed: %s", error)
                    worker.send({"error": str(error)})
            if callback is not None:
                callback(step, x0, x, total_steps)

        cancelled = True
        try:
            with suppress_preview(callback, self.options.suppress_default_preview):
                output = executor(noise, latent_image, sampler, sigmas, denoise_mask,
                                  combined, disable_pbar, seed, **kwargs)
            cancelled = False
            return output
        finally:
            worker.finish(cancel=cancelled)
