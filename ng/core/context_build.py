"""Build a ContextItem from what a context node's widgets say. Shared by the nodes and by the preview endpoint, so both name things alike."""
import os
from dataclasses import replace

from . import fields
from .context import ContextItem
from .context_options import ContextOptions, roles
from .issues import SchemaError
from .project import slug


def _clean_source(source):
    return source.replace(" [input]", "").strip()


def widget_text(widgets, key):
    """Missing/null text from ComfyUI widgets or STRING links means unset; other types stay invalid."""
    if widgets.get(key) is None:
        return ""
    return fields.read_str(widgets, key, "context.widgets", "")


def _label(media, widgets, name):
    if media == "text":
        return name or str(widgets.get("text", "") or "")[:24].strip() or "note"
    return name or os.path.splitext(os.path.basename(_clean_source(str(widgets.get(media, "") or ""))))[0] or media


def card_id(entry):
    """The Context ID of a card as the Connector gives it: its own, or for an empty field `<media>_<slug of its label>`.

    The AI helpers (Make H3 prompt, part writer, split, shot draft) read the raw widget and lost every binding, speaker
    and description of a card whose ID field was empty (BUG-047/049/050/052/053/056)."""
    widgets, media = entry.get("widgets") or {}, entry.get("media") or "image"
    if widgets.get("context_id"):
        return str(widgets["context_id"])
    return "%s_%s" % (media, slug(_label(media, widgets, str(widgets.get("name") or "").strip())))


def distinct(items):
    """Cards whose name was only derived from their file (the Name field left empty) get a free name, "scene1 2", when
    another card already has it; an ID derived the same way follows. Two unnamed cards of one picture, or scene1.png and
    scene1.wav, stopped the Connector and the Studio plan with "name used twice" (BUG-067). Names a user typed must stay
    unique: those still fail in require_unique with that message."""
    names, ids, out = set(), set(), []
    for item in items:
        name, identity = item.name, item.id
        if name == _label(item.media, {item.media if item.media != "text" else "text": item.source}, "") and name.casefold() in names:
            n = 2
            while ("%s %d" % (item.name, n)).casefold() in names:
                n += 1
            name = "%s %d" % (item.name, n)
            if identity == "%s_%s" % (item.media, slug(item.name)) or identity in ids:
                identity = "%s_%s" % (item.media, slug(name))
            item = replace(item, name=name, id=identity)
        names.add(item.name.casefold())
        ids.add(item.id)
        out.append(item)
    return tuple(out)


def item_from_widgets(media, widgets, length_s=0.0):
    """`widgets` holds the node's widget values by name: name, description, content, usage, preserve and, per medium,
    image/video/audio (a file name), text, speaker."""
    if media not in ("image", "video", "audio", "text"):
        raise SchemaError("context.media", "choose image, video, audio or text")
    if not isinstance(widgets, dict):
        raise SchemaError("context.widgets", "expected an object")
    widgets = {key: "" if value is None and key in ("name", "description", "speaker", "color", "text") else value
               for key, value in widgets.items()}
    name = str(widgets.get("name", "")).strip()
    if media == "text":
        source = str(widgets.get("text", ""))
        label = name or source[:24].strip() or "note"
    else:
        source = _clean_source(str(widgets.get(media, "")))
        label = name or os.path.splitext(os.path.basename(source))[0] or media
    return ContextItem(id=str(widgets.get("context_id") or "%s_%s" % (media, slug(label))), name=label, media=media, source=source,
                       content=roles(widgets.get("content_roles", ""), widgets.get("content", "")),
                       usage=roles(widgets.get("usage_roles", ""), widgets.get("usage", "")),
                       preserve=widgets.get("preserve", "high"), description=str(widgets.get("description", "")).strip(),
                       speaker=str(widgets.get("speaker", "")).strip(), length_s=float(length_s), color=str(widgets.get("color", "")),
                       options=ContextOptions.from_json(widgets.get("context_options", "")),
                       subject_ids=roles(widgets.get("subject_ids", ""), ""))
