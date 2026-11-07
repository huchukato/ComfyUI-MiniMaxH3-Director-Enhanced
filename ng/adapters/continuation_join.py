"""Compensate the source/VAE reconstruction difference across six delivered frames."""
import math

import cv2
import numpy as np
import torch

from comfy_extras import nodes_minimax_h3 as native

from ..core.continuation import source_end
from . import video_end


def compensate(source, known, future):
    """Warp the reconstruction residual with the new motion; leave frame seven onward untouched."""
    length = min(6, len(future) - 1)
    if length <= 0:
        return future
    height, width = known.shape[:2]
    size = (max(1, width // 2), max(1, height // 2))
    source = (source.detach().float().cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)
    known = (known.detach().float().cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)
    head = (future[:length].detach().float().cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)
    residual = source.astype(np.float32) - known.astype(np.float32)
    known_gray = cv2.resize(cv2.cvtColor(known, cv2.COLOR_RGB2GRAY), size)
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    for index, image in enumerate(head):
        gray = cv2.resize(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), size)
        flow = cv2.calcOpticalFlowFarneback(gray, known_gray, None, .5, 3, 21, 3, 5, 1.2, 0)
        flow = cv2.resize(flow, (width, height))
        flow *= np.array([width / size[0], height / size[1]], dtype=np.float32)
        correction = cv2.remap(residual, grid_x + flow[:, :, 0], grid_y + flow[:, :, 1], cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REFLECT_101)
        strength = .5 + .5 * math.cos(math.pi * index / length)
        head[index] = np.clip(np.rint(image.astype(float) + strength * correction), 0, 255).astype(np.uint8)
    future[:length].copy_(torch.from_numpy(head).to(device=future.device, dtype=future.dtype).div_(255))
    return future


def smooth(job, known, future):
    item = job.project.context.item(job.chunk.continuation_id)
    source = video_end.tail_frames(item.source, item.options.start_s, source_end(item), 1)
    # AddGuide encodes a center-cropped source; compare against the same canvas.
    source = native._resize(source, future.shape[2], future.shape[1], "center")[0]
    return compensate(source, known, future)
