"""What a render part's prompt is made from, for the Studio's "Prompts per render part": which shot, card, Look, rule and
setting gave which text. The prompt itself is the legacy planner's; this only names its sources, so a user sees where to
change something (user, 2026-10-18: "where do I see what is used, and where").

Each source is {"kind", "id", "label", "text"}: kind is manual | shot | look | rule | picture | video | audio | setting."""
from .legacy_bridge import RULE_USAGES
from .shot_document import has_shots, read_document, read_look

KIND_OF_REF = {"picture": "picture", "first_frame": "picture", "last_frame": "picture", "keyframe": "picture", "video": "video",
               "audio": "audio"}


def _source(kind, label, text, identity=""):
    return {"kind": kind, "id": identity, "label": label, "text": " ".join(str(text or "").split())}


def prompt_sources(context, chunk, refs, segments):
    """The sources of one compiled part. `segments` are the planner's text segments, one per shot of the chunk first."""
    if context.prompt_override.strip():
        return (_source("manual", "Manual prompt", context.prompt_override),)
    out = []
    structured = read_document(context.shots_text) is not None
    look = read_look(context.shots_text) if structured else ""
    if look.strip():
        out.append(_source("look", "Look", look))
    elif not structured and context.idea.strip():
        out.append(_source("look", "Prompt", context.idea))
    for shot, segment in zip(chunk.shots, segments):
        text = segment.get("prompt", "") if isinstance(segment, dict) else ""
        out.append(_source("shot", "Shot %d" % shot.shot_index, text or "(no text)", shot.shot_id))
    for item in context.by_media("text"):
        if structured and has_shots(context.shots_text) and item.effective_usage == ("scene",):
            continue
        if item.source.strip() and set(item.effective_usage) & RULE_USAGES:
            out.append(_source("rule", item.name or "Text", item.source, item.id))
    seen = set()
    for ref in refs:
        item = context.item(ref.ctx_id)
        if not item or ref.ctx_id in seen:
            continue
        seen.add(ref.ctx_id)
        roles = ", ".join(item.effective_usage)
        out.append(_source(KIND_OF_REF.get(ref.kind, ref.kind), item.name or ref.ctx_id,
                           "%s%s" % (roles, (": " + item.description) if item.description.strip() else ""), item.id))
    if context.style and context.style != "None":
        out.append(_source("setting", "Style", context.style))
    for label, value in (("Ambience", context.soundscape), ("Music", context.music)):
        if value and value.strip() and value.strip() != "N/A":
            out.append(_source("setting", label, value))
    return tuple(out)
