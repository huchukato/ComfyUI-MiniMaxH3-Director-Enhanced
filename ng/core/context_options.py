"""Editable media roles, retention details and selected source interval."""
import json
from dataclasses import dataclass

from . import fields

PROPERTIES = ("identity", "face", "hair", "outfit", "body", "pose", "style", "background", "lighting", "composition")
STRENGTHS = ("ignore", "low", "medium", "high", "keep")
CONTROL_KINDS = ("canny", "pose", "depth", "mask")


@dataclass(frozen=True)
class ContextOptions:
    preserve: tuple = ()
    start_s: float = 0.0
    end_s: float = 0.0
    anchor_s: float = -1.0
    video_audio: str = "ignore"
    lyrics: str = ""            # audio: timed lyrics as LRC text, "[mm:ss.xx] line", seconds in the file
    control_kind: str = "canny"
    control_original: str = ""
    control_result: str = ""
    control_mask: str = ""
    mask_prompt: str = "person"
    mask_shape: str = "box"
    mask_grow: int = 16
    edit_mask: str = ""         # image: white = the part a picture of the Director's Pictures output changes
    SCHEMA_VERSION = 1

    def to_dict(self):
        data = {"schema_version": 1, "preserve": dict(self.preserve), "start_s": self.start_s,
                "end_s": self.end_s, "anchor_s": self.anchor_s, "video_audio": self.video_audio}
        if self.lyrics:
            data["lyrics"] = self.lyrics
        if self.control_kind != "canny" or self.control_original or self.control_result:
            data.update(control_kind=self.control_kind, control_original=self.control_original, control_result=self.control_result)
        if self.control_kind == "mask" or self.control_mask:
            data.update(control_mask=self.control_mask, mask_prompt=self.mask_prompt, mask_shape=self.mask_shape, mask_grow=self.mask_grow)
        if self.edit_mask:
            data["edit_mask"] = self.edit_mask
        return data

    @classmethod
    def from_dict(cls, data, path="context.options"):
        fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        if set(data) - set(cls(lyrics="-", control_original="-", control_kind="mask", edit_mask="-").to_dict()):
            raise ValueError("Unknown context option; use supported role, retention and source timing controls.")
        preserve = fields.need_dict(data.get("preserve", {}), path + ".preserve")
        if set(preserve) - set(PROPERTIES) or any(value not in STRENGTHS for value in preserve.values()):
            raise ValueError("Choose a supported preserve property and strength.")
        start = float(fields.read_number(data, "start_s", path, 0.0, minimum=0))
        end = float(fields.read_number(data, "end_s", path, 0.0, minimum=0))
        if end and end <= start:
            raise ValueError("Source end must be later than source start; 0 means the file end.")
        grow = fields.read_number(data, "mask_grow", path, 16, minimum=0)
        if int(grow) != grow:
            raise ValueError("Mask grow must be a whole number of pixels.")
        return cls(tuple(preserve.items()), start, end, float(fields.read_number(data, "anchor_s", path, -1.0, minimum=-1)),
                   fields.read_choice(data, "video_audio", path, ("ignore", "reference"), "ignore"),
                   fields.read_str(data, "lyrics", path, ""),
                   fields.read_choice(data, "control_kind", path, CONTROL_KINDS, "canny"),
                   fields.read_str(data, "control_original", path, ""), fields.read_str(data, "control_result", path, ""),
                   fields.read_str(data, "control_mask", path, ""), fields.read_str(data, "mask_prompt", path, "person"),
                   fields.read_choice(data, "mask_shape", path, ("box", "outline"), "box"),
                   int(grow), fields.read_str(data, "edit_mask", path, ""))

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text)) if text else cls()


def roles(text, fallback):
    if not text:
        return (fallback,) if fallback else ()
    data = json.loads(text)
    if not isinstance(data, list) or not all(isinstance(value, str) and value for value in data):
        raise ValueError("Context roles must be a list of nonempty names.")
    return tuple(dict.fromkeys(data))


def retention_note(options):
    words = {"ignore": "allow to change", "low": "weak reference", "medium": "partially preserve",
             "high": "fully preserve", "keep": "preserve"}
    return "; ".join("%s: %s" % (name, words[value]) for name, value in options.preserve)
