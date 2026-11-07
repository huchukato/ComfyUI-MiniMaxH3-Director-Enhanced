"""Small atomic JSON files, scoped to the requesting ComfyUI user and media type."""
import hashlib
import json
import os
import tempfile

from ..core.presets import ContextPreset


def _path(root, name, media=None):
    identity = name if media is None else media + "\0" + name
    filename = "context_" + hashlib.sha256(identity.encode("utf8")).hexdigest() + ".json"
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, filename))
    if os.path.commonpath((base, path)) != base:
        raise ValueError("The preset file must stay inside the preset folder.")
    return path


def save(root, data):
    preset = ContextPreset.from_dict(data)
    os.makedirs(root, exist_ok=True)
    target = _path(root, preset.name, preset.item.media)
    handle, temporary = tempfile.mkstemp(prefix=".context_", suffix=".tmp", dir=root)
    try:
        with os.fdopen(handle, "w", encoding="utf8") as stream:
            json.dump(preset.to_dict(), stream, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return preset


def _read(path):
    with open(path, encoding="utf8") as stream:
        return ContextPreset.from_dict(json.load(stream))


def load(root, name, media=None):
    if media is None:
        # Older Python callers did not pass media. Keep an unambiguous name usable,
        # but never choose an arbitrary card when several media now share it.
        candidates = {}
        legacy = _path(root, name)
        if os.path.exists(legacy):
            preset = _read(legacy)
            candidates[preset.item.media] = preset
        for kind in ("image", "video", "audio", "text"):
            if os.path.exists(_path(root, name, kind)):
                candidates[kind] = load(root, name, kind)
        if len(candidates) > 1:
            raise ValueError("Choose a media type for this preset name.")
        if candidates:
            return next(iter(candidates.values()))
        return _read(legacy)
    target = _path(root, name, media)
    preset = _read(target if os.path.exists(target) else _path(root, name))
    if preset.name != name or preset.item.media != media:
        raise ValueError("Choose a preset for this context's media type.")
    return preset


def listing(root, media):
    if not os.path.isdir(root):
        return []
    records = set()
    for filename in sorted(os.listdir(root)):
        if not filename.startswith("context_") or not filename.endswith(".json"):
            continue
        path = os.path.realpath(os.path.join(root, filename))
        if os.path.commonpath((os.path.realpath(root), path)) != os.path.realpath(root):
            raise ValueError("The preset file must stay inside the preset folder.")
        preset = _read(path)
        if preset.item.media == media:
            records.add(preset.name)
    return sorted(records)
