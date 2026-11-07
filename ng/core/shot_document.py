"""Versioned shot data in the existing String input; timed text remains readable.

IDs identify story units, never their current array index or chunk position. Drafts
and locks are editing metadata; only active text, media and spoken lines compile.
"""
import json
import re
from dataclasses import dataclass

from . import fields
from .issues import SchemaError

FORMAT = "h3-director-shots"
LOCK_FIELDS = ("timing", "text", "media", "spoken")
CLIP_MODES = ("lock", "copy", "ref")


@dataclass(frozen=True)
class MediaBinding:
    context_id: str
    role: str = "context"
    at_s: float = -1.0      # a Keyframe's time in seconds after the shot's start; -1 = not set
    SCHEMA_VERSION = 1

    def to_dict(self):
        data = {"schema_version": 1, "context_id": self.context_id, "role": self.role}
        if self.at_s >= 0:
            data["at_s"] = self.at_s
        return data

    @classmethod
    def from_dict(cls, data, path="binding"):
        fields.need_dict(data, path)
        fields.check_version(data, path, 1)
        identity = fields.read_str(data, "context_id", path)
        if not identity.strip():
            raise SchemaError(path + ".context_id", "must not be empty")
        at_s = fields.read_number(data, "at_s", path, -1.0)
        return cls(identity, fields.read_str(data, "role", path, "context"), float(at_s) if at_s >= 0 else -1.0)


@dataclass(frozen=True)
class SpokenLine:
    text: str
    speaker_id: str = ""
    voice: str = "a narrator"
    language: str = "English"
    delivery: str = "says"
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": 1, "text": self.text, "speaker_id": self.speaker_id,
                "voice": self.voice, "language": self.language, "delivery": self.delivery}

    @classmethod
    def from_dict(cls, data, path="spoken"):
        fields.need_dict(data, path)
        fields.check_version(data, path, 1)
        values = {key: fields.read_str(data, key, path, default) for key, default in
                  (("text", ""), ("speaker_id", ""), ("voice", "a narrator"),
                   ("language", "English"), ("delivery", "says"))}
        for key in ("speaker_id", "voice", "language", "delivery"):
            if any(c in values[key] for c in "\n\r[]():"):
                raise SchemaError(path + "." + key, "contains a dialogue syntax delimiter")
        if "\n" in values["text"] or "\r" in values["text"]:
            raise SchemaError(path + ".text", "one spoken line per entry; add another entry for another line")
        return cls(**values)


@dataclass(frozen=True)
class AudioClip:
    """Sound placed on a Studio audio lane: its own story range and source offset, independent of Shots."""
    id: str
    context_id: str
    start: float
    end: float
    offset: float = 0.0
    mode: str = "ref"
    lane: str = ""
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": 1, "id": self.id, "context_id": self.context_id, "start": self.start, "end": self.end,
                "offset": self.offset, "mode": self.mode, "lane": self.lane}

    @classmethod
    def from_dict(cls, data, path="clip"):
        fields.need_dict(data, path)
        fields.check_version(data, path, 1)
        identity, context_id = fields.read_str(data, "id", path), fields.read_str(data, "context_id", path)
        if not identity.strip() or not context_id.strip():
            raise SchemaError(path, "id and context_id must not be empty")
        start, end = fields.read_number(data, "start", path, minimum=0), fields.read_number(data, "end", path, minimum=0)
        if end <= start:
            raise SchemaError(path + ".end", "must be after start")
        return cls(identity, context_id, float(start), float(end), float(fields.read_number(data, "offset", path, 0.0, minimum=0)),
                   fields.read_choice(data, "mode", path, CLIP_MODES, "ref"), fields.read_str(data, "lane", path, ""))


def _load(text):
    if not text.lstrip().startswith("{"):
        return None
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as error:
        raise SchemaError("shots", "invalid JSON: %s" % error) from error
    fields.need_dict(data, "shots")
    if data.get("format") != FORMAT:
        raise SchemaError("shots.format", "expected " + FORMAT)
    fields.check_version(data, "shots", 1)
    return data


def read_audio_clips(text):
    """Audio lane clips of a structured document; () for timed text or a document without lanes."""
    data = _load(text)
    clips = tuple(AudioClip.from_dict(c, "shots.audio[%d]" % i) for i, c in enumerate(fields.read_list(data or {}, "audio", "shots")))
    if len({clip.id for clip in clips}) != len(clips):
        raise SchemaError("shots.audio", "clip ids must be unique")
    return clips


def read_look(text):
    """What every render part shares (style, place, light), written once beside the Shots; "" when there is none."""
    data = _load(text)
    return fields.read_str(data, "look", "shots", "").strip() if data else ""


PROMPT_SOURCES = ("ai", "user")


def read_part_prompts(text):
    """{render part index: (key of the compiled prompt it was written from, text, "ai" | "user")}."""
    data = _load(text)
    out = {}
    for index, entry in enumerate(fields.read_list(data or {}, "part_prompts", "shots")):
        path = "shots.part_prompts[%d]" % index
        fields.need_dict(entry, path)
        part = int(fields.read_number(entry, "index", path, minimum=0))
        out[part] = (fields.read_str(entry, "key", path), fields.read_str(entry, "text", path),
                     fields.read_choice(entry, "by", path, PROMPT_SOURCES, "user"))
    return out


def has_shots(text):
    """Whether the user wrote Shots. A document that only holds audio clips leaves the Prompt to carry the video."""
    data = _load(text)
    return bool(text.strip()) if data is None else bool(fields.read_list(data, "shots", "shots"))


def read_document(text):
    """None means legacy timed text. Invalid structured data is never downgraded."""
    data = _load(text)
    if data is None:
        return None
    records = fields.read_list(data, "shots", "shots")
    seen = set()
    for index, record in enumerate(records):
        path = "shots.shots[%d]" % index
        fields.need_dict(record, path)
        identity = fields.read_str(record, "id", path)
        if not identity.strip() or identity in seen:
            raise SchemaError(path + ".id", "must be nonempty and unique")
        seen.add(identity)
        fields.read_number(record, "start", path, minimum=0)
        fields.read_number(record, "end", path, minimum=0)
        fields.read_str(record, "text", path)
        metadata(record, path)
        if record.get("draft") is not None:
            fields.need_dict(record["draft"], path + ".draft")
    return records


_EFFECT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def effect_name(value):
    """A shot's effect embedding as the prompt names it ("minimaxh3_bullet_time"); "" for none or an unusable name."""
    name = str(value or "").strip().removeprefix("embedding:").removesuffix(".safetensors")
    return name if _EFFECT.match(name) else ""


def metadata(record, path="shot"):
    media = tuple(MediaBinding.from_dict(b, "%s.media[%d]" % (path, i))
                  for i, b in enumerate(fields.read_list(record, "media", path)))
    spoken = tuple(SpokenLine.from_dict(s, "%s.spoken[%d]" % (path, i))
                   for i, s in enumerate(fields.read_list(record, "spoken", path)))
    locks = fields.read_texts(record, "locked_fields", path)
    if any(value not in LOCK_FIELDS for value in locks):
        raise SchemaError(path + ".locked_fields", "expected timing, text, media or spoken")
    return {"id": record["id"], "media": media, "spoken": spoken, "locked_fields": locks, "effect": effect_name(record.get("effect"))}


def bound_media_ids(text):
    records = read_document(text)
    bound = {binding["context_id"] for record in records or () for binding in record.get("media", [])}
    return bound | {clip.context_id for clip in read_audio_clips(text)}
