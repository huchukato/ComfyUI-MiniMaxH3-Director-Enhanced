"""The three assistance modes and what each one is allowed to change on its own.

Manual is the user's own typing, Assist fills a card only when the user applies a suggestion, and Auto Direct may
write a whole scene proposal. None of them runs without an explicit action, and none of them overwrites a field the
provider said nothing about.
"""
from dataclasses import dataclass
import json

from . import fields
from .analysis import ANALYSIS_FIELDS
from .context import CONTENT_KINDS, USAGE_BY_MEDIA

MODES = ("manual", "assist", "auto")


@dataclass(frozen=True)
class AssistState:
    """What the panel may offer right now. Persisted with the workflow so a reload restores the same mode."""
    mode: str = "assist"
    provider: bool = False
    busy: bool = False
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "mode": self.mode, "provider": self.provider, "busy": self.busy}

    @classmethod
    def from_dict(cls, data, path="assist"):
        fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        if set(data) - set(cls().to_dict()):
            raise ValueError("Unknown assistance setting; choose Manual, Assist or Auto.")
        return cls(mode=fields.read_choice(data, "mode", path, MODES, "assist"),
                   provider=_flag(data, "provider", path), busy=_flag(data, "busy", path))

    @property
    def can_analyze(self):
        """An analysis is an explicit request, so it is offered in every mode that has a provider."""
        return self.provider and not self.busy

    @property
    def can_auto_direct(self):
        """Auto Direct writes a whole scene, which only the Auto mode is allowed to start."""
        return self.provider and not self.busy and self.mode == "auto"

    def status(self):
        if not self.provider:
            return "AI off · connect H3 AI Loader to the Connector"
        if self.busy:
            return "Working · Cancel stops this request"
        return {"manual": "Manual · you type every field", "assist": "Assist · suggestions need Apply",
                "auto": "Auto · scene proposals need Apply"}[self.mode]


def _flag(data, key, path):
    """A flag the panel toggles: a text value there is a broken workflow, not a truthy shortcut."""
    value = data.get(key, False)
    if not isinstance(value, bool):
        raise ValueError("%s.%s must be true or false." % (path, key))
    return value


def field_changes(suggestion, selected, media, warnings=None):
    """The widget values an Apply writes, restricted to `selected` and checked against the medium's own roles.

    A suggested role the card does not offer is reported instead of written, so nothing is silently mapped.
    """
    if not isinstance(selected, (list, tuple)):
        raise ValueError("Select which fields the analysis may write.")
    unknown = [repr(name) for name in selected if not isinstance(name, str) or name not in ANALYSIS_FIELDS]
    if unknown:
        raise ValueError("Unknown analysis field: %s." % ", ".join(unknown))
    changes, notes = {}, list(warnings or [])
    allowed = USAGE_BY_MEDIA.get(media, ())
    for name in selected:
        value = str(getattr(suggestion, name, "") or "").strip()
        if not value:
            notes.append("The analysis had no %s; your text was kept." % name)
            continue
        if name in ("content", "usage"):
            choices = CONTENT_KINDS if name == "content" else allowed
            if value not in choices:
                notes.append("%s: '%s' is not a %s role for %s; your value was kept." % (name, value, name, media))
                continue
            changes[name + "_roles"] = json.dumps([value])
        changes[name] = value
    return changes, notes


def batch_plan(contexts, mode, provider_connected):
    """Which contexts Analyze All covers, and why each one is in or out.

    Returns the indices to analyze plus the reasons for the ones left alone, so the panel can show both.
    """
    entries = list(contexts or [])
    if mode not in MODES:
        raise ValueError("Choose Manual, Assist or Auto before analyzing.")
    if mode == "manual":
        return [], ["Manual mode: no analysis is sent. Switch to Assist or Auto."]
    if not provider_connected:
        return [], ["Connect H3 AI Loader to the Connector first."]
    targets, skipped = [], []
    for index, entry in enumerate(entries):
        widgets = entry.get("widgets") if isinstance(entry, dict) else None
        media = entry.get("media") if isinstance(entry, dict) else None
        if media not in ("image", "video", "audio", "text"):
            skipped.append((index, "no supported medium"))
            continue
        if media == "text" and not str(widgets.get("text", "")).strip():
            skipped.append((index, "the text is empty"))
            continue
        if media != "text" and not str(widgets.get(media, "")).strip():
            skipped.append((index, "no file chosen"))
            continue
        if widgets.get("analyzed"):
            skipped.append((index, "already analyzed"))
            continue
        targets.append(index)
    return targets, ["%s: %s" % (_label(entries, index), reason) for index, reason in skipped]


def _label(entries, index):
    widgets = entries[index].get("widgets") or {}
    return widgets.get("name") or entries[index].get("media") or "Context %d" % (index + 1)
