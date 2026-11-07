"""Versioned media inputs shared by compiler and native guide planning."""
from dataclasses import dataclass
from . import fields

KINDS = ("picture", "video", "audio", "lock", "first_frame", "last_frame", "keyframe", "continue_video")


@dataclass(frozen=True)
class MediaRef:
    kind: str
    ctx_id: str
    source: str
    start_f: int = 0
    length_f: int = 0
    trim_start_f: int = 0
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "kind": self.kind, "ctx_id": self.ctx_id, "source": self.source,
                "start_f": self.start_f, "length_f": self.length_f, "trim_start_f": self.trim_start_f}

    @classmethod
    def from_dict(cls, data, path="ref"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        return cls(kind=fields.read_choice(data, "kind", path, KINDS, None), ctx_id=fields.read_str(data, "ctx_id", path),
                   source=fields.read_str(data, "source", path), start_f=int(fields.read_number(data, "start_f", path, 0)),
                   length_f=int(fields.read_number(data, "length_f", path, 0)), trim_start_f=int(fields.read_number(data, "trim_start_f", path, 0)))
