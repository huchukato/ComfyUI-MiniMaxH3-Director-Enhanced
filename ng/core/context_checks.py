"""Cross-item diagnostics before legacy compilation; never hide ambiguous or discarded inputs."""
import re

from .issues import Issue
from . import frames
from .shot_document import bound_media_ids


_COMMON = set("with and the a an of in on her his their its wearing holding shown from into".split())


def _words(text):
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _COMMON}


def look_alikes(subjects):
    """Pairs of independent Subject pictures whose descriptions are mostly the same words: probably one figure. As two
    Subjects H3 switched between the pictures (Ref2VA minute 2026-10-20: three views of one elf, three Subjects)."""
    out, named = [], set()
    for n, first in enumerate(subjects):
        for second in subjects[n + 1:]:
            a, b = _words(first.description), _words(second.description)
            if second.id not in named and first.id not in named and len(a) >= 4 and len(b) >= 4 and len(a & b) >= 0.6 * min(len(a), len(b)):
                out.append((first, second))
                named.add(second.id)        # each picture is named once, with the first figure it resembles
    return out


def check_context(context):
    issues = []
    bound = bound_media_ids(context.shots_text)
    subjects = {i.id for i in context.by_media("image") if "reference" in i.effective_usage and i.source and not i.subject_ids}
    for role in ("first_frame", "last_frame"):
        items = [i for i in context.by_media("image") if i.id not in bound and role in i.effective_usage and i.source]
        if len(items) > 1:
            # H3 takes one frame per slot, so exactly the first one is sent. The warning has to say which one won,
            # otherwise the user cannot tell why their second image seems to be ignored.
            issues.append(Issue("anchor_multiple", "Only one %s is sent to the model; '%s' is used and these are "
                                "ignored: %s. Remove the unused ones or keep them as Reference."
                                % (role.replace("_", " "), items[0].name, ", ".join(i.name for i in items[1:]))))
    roots = [i for i in context.by_media("image") if i.id in subjects and "character" in i.content]
    for first, second in look_alikes(roots):
        issues.append(Issue("subject_look_alike", "'%s' and '%s' look like the same figure. If they are, set 'Belongs to: %s' on "
                            "'%s'; as two figures H3 switches between them." % (first.name, second.name, first.name, second.name),
                            second.name))
    sources = {}
    for item in context.items:
        if item.media != "text" and item.source:
            key = item.source
            if key in sources:
                issues.append(Issue("source_shared", "Shares a file with %s; each card keeps its own role and source selection."
                                    % sources[key], item.name))
            sources.setdefault(key, item.name)
        if item.media == "audio" and len(item.effective_usage) > 1:
            issues.append(Issue("audio_roles", "Only the first supported audio usage is applied; use one role per card.", item.name))
        if item.media == "audio" and "voice" in item.effective_usage and item.speaker and item.speaker not in subjects:
            issues.append(Issue("voice_unbound", "Speaker is not a reference image; this voice is sent as an unbound audio reference.", item.name))
        # an image reference is used in fl2va too (ng.core.fl2va_refs); video and audio references are not
        reference = item.uses_video_reference or (
            item.media == "audio" and bool(set(item.effective_usage) & {"voice", "copy", "music_style", "rhythm", "sound_reference"}))
        if context.mode == "fl2va" and reference:
            text = ("Choose auto or ref2va for video references; Continue still uses its selected tail and enabled sound."
                    if item.media == "video" and "continue" in item.effective_usage else
                    "Is omitted by explicit fl2va mode; choose auto or ref2va to use it.")
            issues.append(Issue("reference_disabled", text, item.name))
    return issues


def check_guide_times(context, total_frames):
    issues = []
    for item in context.by_media("image"):
        if not item.source or "keyframe" not in item.effective_usage or item.options.anchor_s < 0:
            continue
        if frames.seconds_to_frames(item.options.anchor_s) >= total_frames:
            issues.append(Issue("guide_outside_project", "Scene time %.3fs is outside the rendered video; choose %.3fs "
                                "or earlier, or extend the project." % (item.options.anchor_s,
                                                                      frames.frames_to_seconds(total_frames - 1)), item.name))
    return issues
