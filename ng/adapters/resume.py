"""Pick up a render after a crash: every finished render part's raw latent is kept on disk and reused when the same plan is
queued again, so a run that died after hours only samples the parts it had not finished.

A part's key covers what it was made from: its own plan (chunk, prompt, references and the files behind them), the render
settings, and the keys of every part before it, because a continued part is pinned to the one before. Changing part 5
renders part 5 and everything after it again; parts 1 to 4 come from disk. The models themselves are not in the key: after
swapping a checkpoint, delete the folder. The folder is under ComfyUI's output folder, because ComfyUI empties its temp
folder at every start, which is exactly when a resume is needed."""
import hashlib
import json
import os
import time

import torch
import folder_paths
from comfy.nested_tensor import NestedTensor

from ..core.project import jobs
from ..core.turbo_profiles import part_settings
from ..core import control_timing
from ..core.places import is_place
from .continuation_latent import uses_sound_prefix
from .paths import input_path

FOLDER = "h3-director-resume"
KEEP_DAYS = 14


def folder():
    return os.path.join(folder_paths.get_output_directory(), FOLDER)


def _file(source):
    path = input_path(source) if source else None
    if not path or not os.path.isfile(path):
        return None
    stat = os.stat(path)
    return [stat.st_size, stat.st_mtime_ns]


def _place(job, context_id):
    place = next(p for p in job.project.places if p.context_id == context_id)
    return ["rendered", place.kind, place.view]


def _own(job, settings):
    compiled, chunk, context = job.compiled, job.chunk, job.project.context
    own = {"chunk": chunk.to_dict(), "mode": compiled.mode, "prompt": compiled.prompt, "size": [context.width, context.height],
            "continuity": job.project.plan.continuity.mode,
            # a Place picture is written anew by every render (adapters/places.py); the earlier part it comes from is in the chain
            "refs": [[r.kind, r.ctx_id, r.source, r.start_f, r.length_f, r.trim_start_f,
                      _place(job, r.ctx_id) if is_place(r.ctx_id) else _file(r.source)] for r in compiled.refs]}
    if uses_sound_prefix(job):
        own["continuation_audio"] = "held_prefix_no_guide_v1"
    controls = []
    for clip, a, b, source in control_timing.spans(job) if settings.get("control_strength", 1.0) else ():
        item = context.item(clip.context_id)
        controls.append([item.source, _file(item.source), item.options.control_kind, item.options.end_s, item.length_s, a, b, source])
        if item.options.control_kind == "mask":
            controls[-1].extend([item.options.control_mask, _file(item.options.control_mask), item.options.mask_shape, item.options.mask_grow])
    if controls:
        own["control"] = controls
        own["control_settings"] = [settings.get("control_strength", 1.0), settings.get("control_start", 0.0), settings.get("control_end", 1.0)]
    return own


def part_key(job, settings):
    """Hex key of this part, chained over every part before it."""
    base = {k: v for k, v in settings.items() if not k.startswith("control_")}
    key = hashlib.sha256(json.dumps(base, sort_keys=True, default=str).encode()).hexdigest()
    for earlier in jobs(job.project)[:job.index + 1]:
        key = hashlib.sha256((key + json.dumps(_own(earlier, settings), sort_keys=True, default=str)).encode()).hexdigest()
    return key[:32]


def _path(key):
    return os.path.join(folder(), key + ".pt")


def has(key):
    return os.path.isfile(_path(key))


def load(key):
    data = torch.load(_path(key), map_location="cpu", weights_only=True)
    return {"samples": NestedTensor((data["video"], data["audio"]))}


def save(key, latent):
    os.makedirs(folder(), exist_ok=True)
    video, audio = latent["samples"].unbind()
    tmp = _path(key) + ".part"
    torch.save({"video": video.detach().cpu(), "audio": audio.detach().cpu()}, tmp)
    os.replace(tmp, _path(key))
    _prune()


def forget(chunks, settings):
    """The whole video is put together: its parts are no longer needed for a resume."""
    for job in chunks:
        key = part_key(job, part_settings(job.compiled.mode, settings))
        if has(key):
            os.remove(_path(key))


def _prune():
    """Parts older than KEEP_DAYS are no run's resume any more."""
    limit = time.time() - KEEP_DAYS * 86400
    for name in os.listdir(folder()):
        path = os.path.join(folder(), name)
        if name.endswith(".pt") and os.path.getmtime(path) < limit:
            os.remove(path)
