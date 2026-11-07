"""The picture segments the legacy compiler reads besides the shot texts: native First / Last frame slots, and storyboard
pictures in References mode."""
from .context import USAGE_BY_MEDIA
from .shot_document import bound_media_ids, read_document


def _written_numbers(chunk, texts):
    """[Shot N] as the body numbers them: only shots that carry text count."""
    written = [s for s, seg in zip(chunk.shots, texts) if seg["prompt"].strip()]
    return {s.shot_id: n for n, s in enumerate(written, 1)}


def _shot_at(chunk, frame):
    for shot in chunk.shots:
        if shot.local_start_f <= frame < shot.local_end_f:
            return shot
    return chunk.shots[-1] if chunk.shots and frame >= chunk.shots[-1].local_end_f else None


def anchor_segments(context, chunk, guides, texts=None):
    """Only actual native edge slots become legacy first/last-frame declarations.

    With `texts` each carries the number of the shot it opens or ends ("shotNo"), so References mode words it as MiniMax's
    guide does: "<Picture 2> is the first frame of [Shot 1]". The segment has no text of its own, and without the number the
    compiler found no shot for it and fell back to "a composition anchor at 0s" (real test 2026-10-12)."""
    numbers = _written_numbers(chunk, texts) if texts is not None else {}
    out = []
    for ref in guides:
        item = context.item(ref.ctx_id)
        if ref.kind not in ("first_frame", "last_frame"):
            continue
        span = max(chunk.sampled_frames // 8, 1)
        if ref.kind == "first_frame":
            seg = {"type": "image", "imageFile": item.source, "fileName": item.name, "start": 0,
                   "length": span, "prompt": "", "ng_item": item.id}
            shot = _shot_at(chunk, ref.start_f)
        else:
            seg = {"type": "image", "imageFile": item.source, "fileName": item.name, "isEndFrame": True,
                   "start": chunk.sampled_frames - span, "length": span, "prompt": "", "ng_item": item.id}
            shot = _shot_at(chunk, max(ref.start_f, 1) - 1)
        if shot is not None and shot.shot_id in numbers:
            seg["shotNo"] = numbers[shot.shot_id]
        out.append(seg)
    return out


def storyboard_segments(context, chunk, texts):
    """References mode: a Storyboard picture plans the shots it lies on (viewpoint, subject placement, shot order), as
    MiniMax's guide words it: "<Picture 3> is a storyboard reference for [Shot 1] and [Shot 2]". It is no frame of the
    video; before 2026-10-12 it became a keyframe guide at each shot's start and the sketch itself was pushed into the
    picture. A storyboard card on no shot plans the whole target video."""
    number = _written_numbers(chunk, texts)
    planned, bound = {}, bound_media_ids(context.shots_text)
    for shot in chunk.shots:
        for binding in shot.media:
            if _plans(context, binding) and shot.shot_id in number:
                planned.setdefault(binding.context_id, {})[number[shot.shot_id]] = shot.shot_id
    for item in context.by_media("image"):
        if item.source and item.id not in bound and "storyboard" in item.effective_usage:
            planned.setdefault(item.id, {})
    out = []
    for i, shots in planned.items():
        nos = sorted(shots)
        seg = {"type": "image", "imageFile": context.item(i).source, "fileName": context.item(i).name, "start": 0, "length": 1,
               "prompt": "", "refRole": "storyboard", "shotNos": nos, "ng_item": i}
        panels = _panels(context, i)
        if nos and len(panels) > len(nos):
            # A render part sees the whole storyboard but numbers its own shots from [Shot 1]; without the panel numbers a later
            # part read panels 1 and 2 again (compiled 2026-10-12, user's 30 s storyboards).
            seg["panelNos"] = [panels.index(shots[n]) + 1 if shots[n] in panels else None for n in nos]
        out.append(seg)
    return out


def _plans(context, binding):
    item = context.item(binding.context_id)
    roles = (binding.role,) if binding.role in USAGE_BY_MEDIA["image"] else (item.effective_usage if item else ())
    return bool(item and item.media == "image" and item.source and "storyboard" in roles)


def _panels(context, item_id):
    """The project's shots this storyboard plans, in story order: panel N of the picture is the N-th of them."""
    records = sorted(read_document(context.shots_text) or (), key=lambda r: (float(r.get("start", 0)), float(r.get("end", 0))))
    out = []
    for record in records:
        for binding in record.get("media", []):
            if binding.get("context_id") == item_id and _plans(context, _Binding(binding)):
                out.append(record["id"])
                break
    return out


class _Binding:
    def __init__(self, record):
        self.context_id, self.role = record.get("context_id"), record.get("role", "context")
