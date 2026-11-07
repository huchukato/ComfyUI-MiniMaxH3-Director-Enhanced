"""Context items (what the user's pictures, clips, sounds and notes MEAN) and the Director Context that gathers them.

A ContextItem separates CONTENT (what is in the medium) from USAGE (what H3 should do with it), as the spec asks. Both are
open vocabularies with known values; an unknown value is kept and reported, never silently mapped to something else.
"""
from dataclasses import dataclass

from . import fields
from .issues import Issue, SchemaError
from .context_options import ContextOptions

MEDIA = ("image", "video", "audio", "text")
PRESERVE = ("low", "medium", "high")

CONTENT_KINDS = ("character", "face", "animal", "object", "outfit", "prop", "environment", "location", "style", "pose",
                 "action", "shot", "expression", "lighting", "effect", "composition",
                 "voice", "dialogue", "singing", "music", "ambience", "sound_effect", "camera_motion", "motion", "rules", "shot_rhythm", "identity", "control")
# Which content roles each medium can actually hold. A card is one medium, so offering it a role
# from another medium is not a suggestion - it is a card that can never render. This lived in the
# node module, which meant the analysis prompt and the parse could not ask what a card really
# allows and said yes to whatever CONTENT_KINDS held.
CONTENT_BY_MEDIA = {
    "image": ("character", "face", "animal", "object", "outfit", "prop", "environment", "location", "style",
              "pose", "composition"),
    "video": ("motion", "camera_motion", "environment", "shot_rhythm", "identity", "action", "effect", "style", "control"),
    "audio": ("voice", "dialogue", "music", "ambience", "sound_effect", "singing"),
    # A text note describes a whole video, so it carries what the video is made of: the shot, the
    # dialogue and - the reason these are here - the sound. overall_soundscape and
    # non_diegetic_music are two of the three fields the model is asked to write, and a note that
    # cannot name voice, ambience, music or a sound effect cannot feed them.
    "text": ("shot", "action", "dialogue", "voice", "ambience", "music", "sound_effect",
             "camera_motion", "character", "outfit", "environment", "lighting", "style", "rules"),
}

USAGE_BY_MEDIA = {
    "image": ("reference", "first_frame", "keyframe", "last_frame", "storyboard"),
    "video": ("motion", "camera", "continue", "structure", "control"),
    "audio": ("voice", "copy", "lock", "music_style", "rhythm", "sound_reference"),
    "text": ("style", "rule", "character", "world", "scene", "camera", "dialogue", "constraint", "instruction"),
}


@dataclass(frozen=True)
class ContextItem:
    id: str
    name: str
    media: str
    source: str = ""            # file path relative to the ComfyUI input folder; for text items the text itself
    content: tuple = ()
    usage: tuple = ()
    preserve: str = "high"
    description: str = ""       # what the item is, in one sentence (the compiler writes it into the definition line)
    speaker: str = ""           # audio: id of the item whose voice this is
    length_s: float = 0.0       # audio/video: duration in seconds when known (0 = unknown)
    color: str = ""             # "" = assigned automatically
    options: ContextOptions = ContextOptions()
    subject_ids: tuple = ()    # owning Subject context IDs for an image, motion reference or scoped text
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "id": self.id, "name": self.name, "media": self.media,
                "source": self.source, "content": list(self.content), "usage": list(self.usage), "preserve": self.preserve,
                "description": self.description, "speaker": self.speaker, "length_s": self.length_s, "color": self.color,
                "options": self.options.to_dict(), "subject_ids": list(self.subject_ids)}

    @classmethod
    def from_dict(cls, data, path="context"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        media = fields.read_choice(data, "media", path, MEDIA, None)
        return cls(id=fields.read_str(data, "id", path), name=fields.read_str(data, "name", path), media=media,
                   source=fields.read_str(data, "source", path, ""), content=fields.read_texts(data, "content", path),
                   usage=fields.read_texts(data, "usage", path),
                   preserve=fields.read_choice(data, "preserve", path, PRESERVE, "high"),
                   description=fields.read_str(data, "description", path, ""),
                   speaker=fields.read_str(data, "speaker", path, ""), length_s=float(fields.read_number(data, "length_s", path, 0.0, minimum=0)),
                   color=fields.read_str(data, "color", path, ""),
                   options=ContextOptions.from_dict(data["options"], path + ".options") if "options" in data else ContextOptions(),
                   subject_ids=fields.read_texts(data, "subject_ids", path))

    @property
    def effective_usage(self):
        """The usage the compiler acts on: what the user set, else the default role of the medium."""
        return self.usage or (USAGE_BY_MEDIA[self.media][0],)

    @property
    def uses_video_reference(self):
        roles = set(self.effective_usage)
        return self.media == "video" and bool(roles & {"motion", "camera", "structure"})


def check_item(item):
    """Soft problems with one item. Hard problems are SchemaError at load time."""
    issues = []
    for value in item.content:
        if value not in CONTENT_KINDS:
            issues.append(Issue("content_unknown", "'%s' is not a known content kind; kept as written." % value, item.name))
    for value in item.usage:
        if value not in USAGE_BY_MEDIA[item.media]:
            issues.append(Issue("usage_unknown", "'%s' is not a usage for %s items; the compiler will ignore it."
                                % (value, item.media), item.name))
        elif item.media == "image" and value == "keyframe" and item.options.anchor_s < 0:
            issues.append(Issue("usage_pending", "Set a scene time for '%s'; this image is not sent for that role until timed." % value, item.name))
    if item.media != "text" and not item.source:
        issues.append(Issue("source_missing", "has no file; it cannot be sent to the model.", item.name))
    if item.media == "text" and not item.source.strip():
        issues.append(Issue("text_empty", "is empty.", item.name))
    return tuple(issues)


def require_unique(items):
    seen = {}
    names = set()
    for item in items:
        if item.id in seen:
            raise SchemaError("context.%s" % item.id, "id used twice (%s and %s): two cards share one ID, as a copied card or a "
                              "preset loaded twice does; reload the workflow (the later card gets its own ID) or remove one"
                              % (seen[item.id], item.name))
        seen[item.id] = item.name
        name = item.name.casefold()
        if name in names:
            raise SchemaError("context.name", "name used twice: %s; use distinct names for @mentions and speakers" % item.name)
        names.add(name)


@dataclass(frozen=True)
class DirectorContext:
    idea: str = ""
    project_seconds: float = 10.0
    width: int = 768
    height: int = 1152
    mode: str = "auto"          # auto | fl2va | ref2va
    shots_text: str = ""        # "0-8: text" lines; empty = the idea carries the whole project
    soundscape: str = ""
    music: str = ""
    prepend_text: str = ""
    items: tuple = ()
    style: str = ""
    prompt_override: str = ""
    SCHEMA_VERSION = 1

    def __post_init__(self):
        # The optional STRING inputs arrive as None from a bypassed or None-producing node (BUG-062): that means "empty".
        # Required widgets (style, ...) keep failing on None in plan_project: there it is a real defect upstream.
        for name in ("prepend_text", "prompt_override"):
            if getattr(self, name) is None:
                object.__setattr__(self, name, "")
        if self.mode not in ("auto", "fl2va", "ref2va"):
            raise ValueError("mode must be auto, fl2va or ref2va, got %r" % (self.mode,))

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "idea": self.idea, "project_seconds": self.project_seconds,
                "width": self.width, "height": self.height, "mode": self.mode, "shots_text": self.shots_text,
                "soundscape": self.soundscape, "music": self.music, "prepend_text": self.prepend_text,
                "items": [i.to_dict() for i in self.items], "style": self.style, "prompt_override": self.prompt_override}

    @classmethod
    def from_dict(cls, data, path="director"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        items = tuple(ContextItem.from_dict(d, "%s.items[%d]" % (path, n)) for n, d in enumerate(fields.read_list(data, "items", path)))
        require_unique(items)
        return cls(idea=fields.read_str(data, "idea", path, ""),
                   project_seconds=fields.read_number(data, "project_seconds", path, 10.0, minimum=0.1),
                   width=int(fields.read_number(data, "width", path, 768, minimum=32)),
                   height=int(fields.read_number(data, "height", path, 1152, minimum=32)),
                   mode=fields.read_choice(data, "mode", path, ("auto", "fl2va", "ref2va"), "auto"),
                   shots_text=fields.read_str(data, "shots_text", path, ""), soundscape=fields.read_str(data, "soundscape", path, ""),
                   music=fields.read_str(data, "music", path, ""), prepend_text=fields.read_str(data, "prepend_text", path, ""),
                   items=items, style=fields.read_str(data, "style", path, ""), prompt_override=fields.read_str(data, "prompt_override", path, ""))

    def item(self, item_id):
        for found in self.items:
            if found.id == item_id:
                return found
        return None

    def by_media(self, media):
        return tuple(i for i in self.items if i.media == media)
