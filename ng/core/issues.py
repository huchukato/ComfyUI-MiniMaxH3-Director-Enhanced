"""One warning type for everything that is trimmed, replaced or ignored. Nothing is dropped without an Issue naming it."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    code: str
    text: str
    ref: str = ""
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "code": self.code, "text": self.text, "ref": self.ref}

    @classmethod
    def from_dict(cls, data):
        return cls(code=str(data["code"]), text=str(data["text"]), ref=str(data.get("ref", "")))

    def __str__(self):
        return "%s%s" % (self.text, " (%s)" % self.ref if self.ref else "")


class SchemaError(ValueError):
    """Persisted data does not match the schema. The message starts with the path of the offending field."""

    def __init__(self, path, message):
        super().__init__("%s: %s" % (path, message))
        self.path = path
