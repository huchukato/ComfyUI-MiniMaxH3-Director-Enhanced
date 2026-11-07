"""Subject ownership is separate from a media card; native picture ordinals still identify each card."""
from dataclasses import dataclass, replace

from .issues import Issue
from .context import ContextItem


@dataclass(frozen=True)
class SubjectGroup:
    root: ContextItem
    images: tuple


def _root(item):
    return item.media == "image" and "reference" in item.effective_usage and bool(item.source) and not item.subject_ids


def resolve_subjects(items):
    """Store stable root IDs; invalid/chained ownership is reported and the asset remains independent."""
    names = {item.name.casefold(): item.id for item in items}
    roots = {item.id for item in items if _root(item)}
    ids = {item.id for item in items}
    out, issues = [], []
    for item in items:
        selected = []
        for value in item.subject_ids:
            target = value.strip()
            identity = target if target in ids else names.get(target.casefold())
            if item.media not in ("image", "video", "text") or identity not in roots or identity == item.id:
                issues.append(Issue("subject_target_invalid", "Cannot assign '%s' to a connected, independent reference image. "
                                    "Choose a Subject; this unresolved assignment is not applied." % target, item.name))
            elif identity not in selected:
                selected.append(identity)
        out.append(replace(item, subject_ids=tuple(selected)))
    return tuple(out), issues


def subject_groups(context):
    images = [item for item in context.by_media("image") if "reference" in item.effective_usage and item.source]
    return tuple(SubjectGroup(root, (root,) + tuple(asset for asset in images if root.id in asset.subject_ids))
                 for root in images if not root.subject_ids)
