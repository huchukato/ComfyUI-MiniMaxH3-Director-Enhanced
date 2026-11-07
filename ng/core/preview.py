"""The plan as plain data for the editor's live panel: no media is loaded and nothing is rendered."""
from . import fields, frames
from .chunks import ContinuityPlan
from .context import DirectorContext
from .context_build import distinct, item_from_widgets
from .issues import SchemaError
from .limits import DEFAULT_SOUNDSCAPE, PIN_AUDIO_DEFAULT, FPS
from .project import plan_project
from .stills import plan_stills

DIRECTOR_DEFAULTS = {"idea": "", "shots": "", "project_seconds": 10.0, "chunk_seconds": 0.0, "width": 768, "height": 1152, "mode": "auto",
                     "continuity": "video_audio", "pin_frames": "22", "soundscape": DEFAULT_SOUNDSCAPE, "music": "", "prepend_text": "", "output": "video"}


def _items(contexts, probe):
    items = []
    for entry in contexts or []:
        fields.need_dict(entry, "contexts[]")
        media, widgets = entry.get("media"), entry.get("widgets", {})
        fields.need_dict(widgets, "contexts[].widgets")
        length = probe(widgets.get(media, "")) if probe and media in ("audio", "video") else 0.0
        items.append(item_from_widgets(media, widgets, length))
    return distinct(items)


def _name(context, ref):
    found = context.item(ref.ctx_id)
    return found.name if found else ref.source


def _chunk_view(chunk, compiled, context, picture=False):
    return {"index": chunk.index, "picture": picture, "start_s": round(frames.frames_to_seconds(chunk.story_start_f), 3),
            "end_s": round(frames.frames_to_seconds(chunk.story_end_f), 3), "delivered_frames": chunk.delivered_frames,
            "story_start_f": chunk.story_start_f, "story_end_f": chunk.story_end_f,
            "sampled_frames": chunk.sampled_frames, "head_frames": chunk.head_frames, "mode": compiled.mode, "prompt": compiled.prompt,
            "prompt_key": compiled.key, "prompt_source": compiled.source,
            "refs": [{"kind": r.kind, "ctx_id": r.ctx_id, "name": _name(context, r)} for r in compiled.refs],
            "prompt_labels": dict(compiled.prompt_labels), "shots": [s.to_dict() for s in chunk.shots], "sources": list(compiled.sources)}


def plan_preview(payload, probe=None, image_size=None):
    """payload: {"director": {widget values}, "contexts": [{"media": "image", "widgets": {...}}, ...]}. Never raises on bad user input."""
    try:
        fields.need_dict(payload, "request")
        director = fields.need_dict(payload.get("director", {}), "director")
        values = {**DIRECTOR_DEFAULTS, **director}
        fields.read_list(payload, "contexts", "request")
        context = DirectorContext(idea=values["idea"], project_seconds=float(values["project_seconds"]), width=int(values["width"]),
                                  height=int(values["height"]), mode=values["mode"], shots_text=values["shots"], soundscape=values["soundscape"],
                                  music=values["music"], prepend_text=values["prepend_text"], items=_items(payload.get("contexts"), probe),
                                  style=values.get("style", ""), prompt_override=values.get("prompt_override", ""))
        continuity = ContinuityPlan(mode=values["continuity"], video_frames=int(values["pin_frames"]), audio_frames=PIN_AUDIO_DEFAULT)
        if values.get("output") == "images":
            project = plan_stills(context, image_size)
        else:
            project = plan_project(context, float(values["chunk_seconds"]), continuity, image_size)
    except (SchemaError, KeyError, ValueError, TypeError, OverflowError) as error:
        return {"ok": False, "error": str(error)}
    return {"ok": True, "width": project.context.width, "height": project.context.height, "total_s": round(frames.frames_to_seconds(project.plan.total_frames), 3), "total_frames": project.plan.total_frames,
            "fps": FPS, "requested_frames": project.plan.requested_frames,
            "mode": project.compiled[0].mode if project.compiled else context.mode, "output": project.output, "chunks": [_chunk_view(c, k, project.context, project.output == "images")
                                                                       for c, k in zip(project.plan.chunks, project.compiled)],
            "director_context": project.context.to_dict(),
            "issues": [i.to_dict() for i in project.issues]}
