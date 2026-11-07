"""Fun ControlNet-Union for a render part: the part's own window of a control video, mask and source video.

The control video runs on the story timeline (24 fps, frame 0 = the video's start). A part samples its pinned head plus its
new frames, so it gets the control frames of exactly that span; the head's frames are the ones it was made with in the part
before. ComfyUI's MiniMaxH3FunControlNetApply then fits them to the part (a short window holds its last frame).

A mask can be turned into its bounding box: with the figure's own outline (SAM3) the region outside a new, differently shaped
figure stayed grey (the fill of the hole) in ComfyUI's own workflow as well; with the box the grey rim was gone (real tests
2026-10-13, ControlNet-Union 2.0, 4 steps)."""
import torch
import torch.nn.functional as F

MASK_SHAPES = ("box", "outline")


def window(job):
    """(first story frame, frame count) the part samples, its pinned head included."""
    return job.chunk.story_start_f - job.chunk.head_frames, job.chunk.sampled_frames


def part_frames(frames, job):
    """The part's slice of a frame batch on the story timeline; None when the batch ends before the part."""
    if frames is None:
        return None
    start, count = window(job)
    if start >= frames.shape[0]:
        return None
    return frames[start:start + count]


def shaped(mask, shape="box", grow=16):
    """The region to regenerate: per frame the mask's bounding box or its own outline, grown by `grow` pixels."""
    hole = mask > 0.5
    if shape == "box":
        out = torch.zeros_like(mask, dtype=torch.float32)
        rows, cols = hole.any(dim=2), hole.any(dim=1)
        for frame in range(mask.shape[0]):
            ys, xs = rows[frame].nonzero(), cols[frame].nonzero()
            if len(ys):
                top, bottom = max(0, int(ys[0]) - grow), int(ys[-1]) + grow + 1
                left, right = max(0, int(xs[0]) - grow), int(xs[-1]) + grow + 1
                out[frame, top:bottom, left:right] = 1.0
        return out
    if grow:
        return F.max_pool2d(hole.float()[:, None], 2 * grow + 1, stride=1, padding=grow)[:, 0]
    return hole.float()


def apply(mm, model, model_patch, vae, job, strength, start_percent, end_percent, control_video=None, mask=None, source_video=None,
          mask_shape="box", mask_grow=16):
    control, hole = part_frames(control_video, job), part_frames(mask, job)
    if hole is not None:
        hole = shaped(hole, mask_shape, mask_grow)
    source = part_frames(source_video, job) if hole is not None else None
    out = mm.MiniMaxH3FunControlNetApply.execute(model=model, model_patch=model_patch, vae=vae, strength=strength,
                                                 start_percent=start_percent, end_percent=end_percent,
                                                 control_video=control, mask=hole, source_video=source)
    return getattr(out, "args", out)[0]
