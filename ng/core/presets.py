"""Versioned context presets contain a context item, never provider credentials."""
import json
from dataclasses import dataclass

from . import fields
from .context import ContextItem
from .issues import SchemaError


@dataclass(frozen=True)
class ContextPreset:
    name: str
    item: ContextItem
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "name": self.name, "item": self.item.to_dict()}

    @classmethod
    def from_dict(cls, data, path="preset"):
        fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        extra = set(data) - {"schema_version", "name", "item"}
        if extra:
            raise SchemaError(path, "unknown fields: " + ", ".join(sorted(extra)))
        name = fields.read_str(data, "name", path).strip()
        if not name or len(name) > 80:
            raise SchemaError(path + ".name", "use a name of 1 to 80 characters")
        return cls(name, ContextItem.from_dict(data.get("item"), path + ".item"))


def _own_id(item):
    """The card's own Context ID, or "" when the stored one was only derived from an empty field (BUG-018): written back,
    a derived `image_mage` turned the loading card into another object than its shot bindings expect."""
    from .context_build import card_id
    derived = card_id({"media": item.media, "widgets": {"name": item.name, item.media if item.media != "text" else "text": item.source}})
    return "" if item.id == derived else item.id


def widget_values(item):
    return {"context_id": _own_id(item), "name": item.name, "description": item.description,
            "content": item.content[0] if item.content else "", "usage": item.effective_usage[0], "preserve": item.preserve,
            item.media if item.media != "text" else "text": item.source, "speaker": item.speaker, "color": item.color,
            "content_roles": json.dumps(list(item.content)), "usage_roles": json.dumps(list(item.effective_usage)),
            "context_options": json.dumps(item.options.to_dict()), "subject_ids": json.dumps(list(item.subject_ids))}
