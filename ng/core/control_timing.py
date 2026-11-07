"""Control clips on story time, independent of Shots; native H3 applies a hint to a whole render part."""
from dataclasses import dataclass

from . import fields
from .frames import seconds_to_frames
from .issues import Issue, SchemaError
from .shot_document import _load


@dataclass(frozen=True)
class ControlClip:
    id: str
    context_id: str
    start: float
    end: float
    offset: float = 0.0
    lane: str = "control"
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": 1, "id": self.id, "context_id": self.context_id, "start": self.start,
                "end": self.end, "offset": self.offset, "lane": self.lane}

    @classmethod
    def from_dict(cls, data, path):
        fields.need_dict(data, path)
        fields.check_version(data, path, 1)
        identity, context_id = fields.read_str(data, "id", path), fields.read_str(data, "context_id", path)
        start, end = fields.read_number(data, "start", path, minimum=0), fields.read_number(data, "end", path, minimum=0)
        if not identity.strip() or not context_id.strip() or end <= start:
            raise SchemaError(path, "use unique clip ids, a connected control card and end after start")
        return cls(identity, context_id, float(start), float(end), float(fields.read_number(data, "offset", path, 0.0, minimum=0)),
                   fields.read_str(data, "lane", path, "control"))


def clips(context):
    data = _load(context.shots_text) or {}
    out = tuple(sorted((ControlClip.from_dict(c, "shots.control[%d]" % i)
                        for i, c in enumerate(fields.read_list(data, "control", "shots"))), key=lambda c: c.start))
    if len({c.id for c in out}) != len(out):
        raise SchemaError("shots.control", "clip ids must be unique")
    previous = None
    for clip in out:
        item = context.item(clip.context_id)
        if item is None or item.media != "video" or "control" not in item.effective_usage:
            raise SchemaError("shots.control", "'%s' needs a connected Video card with Use as: Control video" % clip.context_id)
        if not item.source:
            raise SchemaError("shots.control", "'%s' has no video yet: choose or upload one on its card" % item.name)
        if item.options.control_kind == "mask" and not item.options.control_mask:
            raise SchemaError("shots.control", "'%s': generate or choose a mask video on the Inpaint card" % item.name)
        if item.options.control_kind == "mask" and item.options.control_result and item.options.control_result != item.source:
            raise SchemaError("shots.control", "'%s': the source changed; regenerate or choose its matching mask" % item.name)
        if previous and seconds_to_frames(clip.start) < seconds_to_frames(previous.end):
            raise SchemaError("shots.control", "control clips must not overlap; move or trim '%s'" % clip.id)
        if seconds_to_frames(clip.end) <= seconds_to_frames(clip.start):
            raise SchemaError("shots.control", "a control clip must contain at least one frame")
        selected_end = item.options.end_s or item.length_s
        if clip.offset < item.options.start_s or (selected_end and clip.offset >= selected_end):
            raise SchemaError("shots.control", "'%s' starts outside its card's selected source range" % clip.id)
        previous = clip
    return out


def spans(job):
    """(clip, story start/end, first frame in source). No clip in the delivered range means no ControlNet work."""
    entries = clips(job.project.context)
    chunk = job.chunk
    if not any(seconds_to_frames(c.start) < chunk.story_end_f and seconds_to_frames(c.end) > chunk.story_start_f for c in entries):
        return ()
    first = chunk.story_start_f - chunk.head_frames
    out = []
    for clip in entries:
        a, b = max(first, seconds_to_frames(clip.start)), min(chunk.story_end_f, seconds_to_frames(clip.end))
        if b > a:
            out.append((clip, a, b, seconds_to_frames(clip.offset) + a - seconds_to_frames(clip.start)))
    return tuple(out)


def issues(context, chunks):
    entries = clips(context)
    out = []
    for item in context.by_media("video"):
        if "control" in item.effective_usage and not any(c.context_id == item.id for c in entries):
            out.append(Issue("control_unplaced", "Drop this control video on the Studio control lane to use it.", item.name))
    for chunk in chunks:
        active = [c for c in entries if seconds_to_frames(c.start) < chunk.story_end_f and seconds_to_frames(c.end) > chunk.story_start_f]
        if not active:
            continue
        # the frames H3's grid adds after the project's end (10 s delivers 10.1 s) are no gap worth a warning
        start, end = chunk.story_start_f, min(chunk.story_end_f, seconds_to_frames(context.project_seconds))
        covered = start
        for clip in active:
            if seconds_to_frames(clip.start) > covered:
                break
            covered = max(covered, seconds_to_frames(clip.end))
        if covered < end:
            out.append(Issue("control_hold", "Control covers only part of this render part. H3 holds edge frames across gaps "
                             "and to the part edges; steering can extend beyond the clip. Shorter render parts reduce this.", "Render part %d" % (chunk.index + 1)))
    for clip in entries:
        item = context.item(clip.context_id)
        end = item.options.end_s or item.length_s
        rendered_end = chunks[-1].story_end_f
        if seconds_to_frames(clip.start) >= rendered_end:
            out.append(Issue("control_outside_project", "This control clip starts after the rendered video; move it earlier or extend the project.", clip.id))
        elif seconds_to_frames(clip.end) > rendered_end:
            out.append(Issue("control_clipped", "This control clip ends after the rendered video; only its overlapping range is used.", clip.id))
        if end and clip.offset + clip.end - clip.start > end + 1 / 24:
            out.append(Issue("control_source_hold", "The control clip outlasts its selected source; its last frame is held.", item.name))
    return out
