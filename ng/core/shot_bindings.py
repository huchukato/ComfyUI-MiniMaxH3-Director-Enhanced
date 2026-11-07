"""Select shot-bound contexts before invoking the existing H3 compiler.

Contexts not assigned to any shot retain their legacy global scope. A bound
context follows every chunk (including its pinned head) intersecting that shot.
Subject/voice dependencies remain available; no media is loaded here.
"""
import re
from dataclasses import replace

from .context import USAGE_BY_MEDIA
from .issues import Issue
from .frames import seconds_to_frames
from . import shot_share
from .limits import FPS
from .shot_document import read_audio_clips, read_document
from .subjects import subject_groups
from .context_checks import check_context

# a spoken line written into a shot's own text: "@Mage says: ..."
_INLINE_LINE = re.compile(r"\b(?:says|sings|whispers|shouts|murmurs)\b\s*[,:]", re.IGNORECASE)


def _add_roles(roles, identity, values):
    roles[identity] = tuple(dict.fromkeys((*roles.get(identity, ()), *values)))


def _select_clips(context, chunk, clips, selected, roles, issues):
    """Audio-lane clips take part in the chunks whose sampled window they touch, with their own mode as role."""
    window_start = chunk.story_start_f if chunk.continuation_id else chunk.story_start_f - chunk.head_frames
    end = chunk.story_end_f
    for clip in clips:
        item = context.item(clip.context_id)
        if item is None or item.media != "audio":
            issues.append(Issue("audio_clip_unknown", "Audio clip '%s' names a context that is not a connected audio card; "
                                "reconnect it or remove the clip." % clip.context_id, clip.id))
            continue
        if seconds_to_frames(clip.start) >= end or seconds_to_frames(clip.end) <= window_start:
            continue
        selected.add(item.id)
        if clip.mode in ("lock", "copy"):
            _add_roles(roles, item.id, (clip.mode,))
        else:
            _add_roles(roles, item.id, tuple(u for u in item.effective_usage if u not in ("lock", "copy")) or ("sound_reference",))


def scoped_context(context, chunk):
    records = read_document(context.shots_text)
    if records is None:
        return context, ()
    # Only Content placed on a shot is scoped to it. A figure that merely speaks in one shot stays in every part: counted
    # as bound, the mage who said one line in shot 1 lost her reference picture in every later part (2026-10-05).
    bound = {b["context_id"] for record in records for b in record.get("media", [])}
    clips = read_audio_clips(context.shots_text)
    bound.update(clip.context_id for clip in clips)
    selected = {item.id for item in context.items if item.id not in bound}
    roles, issues = {}, []
    _select_clips(context, chunk, clips, selected, roles, issues)
    for shot in chunk.shots:
        for binding in shot.media:
            item = context.item(binding.context_id)
            if item is None:
                issues.append(Issue("shot_context_unknown", "Bound context '%s' is disconnected; reconnect or remove this binding."
                                    % binding.context_id, shot.shot_id))
                continue
            selected.add(item.id)
            if binding.role == "context":
                _add_roles(roles, item.id, item.effective_usage)
            elif binding.role in USAGE_BY_MEDIA[item.media]:
                _add_roles(roles, item.id, (binding.role,))
            else:
                issues.append(Issue("shot_role_unknown", "Role '%s' is not valid for %s; the context's own role is used."
                                    % (binding.role, item.media), shot.shot_id))
                _add_roles(roles, item.id, item.effective_usage)
        selected.update(s.speaker_id for s in shot.spoken if context.item(s.speaker_id))
    # A scoped asset still needs its owning Subject; voice samples need the image
    # they speak for. Following only outward dependencies avoids pulling unused takes.
    pending = list(selected)
    while pending:
        item = context.item(pending.pop())
        if item is None:
            continue
        for identity in (*item.subject_ids, item.speaker):
            if identity and context.item(identity) and identity not in selected:
                selected.add(identity)
                pending.append(identity)
    items = tuple(replace(item, usage=roles[item.id]) if item.id in roles else item
                  for item in context.items if item.id in selected)
    scoped = replace(context, items=items)
    # A lane clip adds its mode to the card's roles for this chunk; lane and Shot binding both play, so that
    # second role is not the "only the first role is applied" case the check warns about.
    laned = {item.name for item in context.items if item.id in {clip.context_id for clip in clips} and len(item.effective_usage) <= 1}
    # A Keyframe placed on a shot has its time there (the shot's start, or its own time in the shot); "set a scene time"
    # is only for a card that is not on any shot.
    placed = {context.item(b.context_id).name for shot in chunk.shots for b in shot.media if context.item(b.context_id)}
    checked = [issue for issue in check_context(scoped) if not (issue.code == "audio_roles" and issue.ref in laned)
               and not (issue.code == "usage_pending" and issue.ref in placed)]
    return scoped, tuple(issues + checked)


def spoken_text(shot, context):
    """Translate active dialogue to the legacy compiler grammar, without an AI."""
    lines, issues = [], []
    subjects = {image.id: group.root for group in subject_groups(context) for image in group.images}
    for spoken in shot.spoken:
        if not spoken.text.strip():
            continue
        item = context.item(spoken.speaker_id) if spoken.speaker_id else None
        if spoken.speaker_id and not item:
            issues.append(Issue("shot_speaker_unknown", "Speaker '%s' is disconnected; the exact line is kept as a narrator."
                                % spoken.speaker_id, shot.shot_id))
        subject = subjects.get(spoken.speaker_id)
        voice = spoken.voice or "a narrator"
        # Each line is a sentence of its own: "... looks forward. A narrator (S1) whispers", not "a narrator".
        speaker = "@" + subject.name if subject else "@voice(%s)" % (voice[:1].upper() + voice[1:])
        if item and not subject:
            issues.append(Issue("shot_speaker_unbound", "Speaker '%s' has no image Subject; narrator voice is used." % item.name, shot.shot_id))
        lines.append("%s [%s] %s: %s" % (speaker, spoken.language or "English", spoken.delivery or "says", spoken.text))
    return "\n".join((shot.text, *lines)), tuple(issues)


def voices_heard(voices, context, chunk):
    """{subject: voice card} for one part: a figure's voice sample goes along where the figure speaks or where its card is
    placed (on a shot or an audio lane in this part). A sample sent to a part in which its figure said nothing was spoken
    anyway: H3 took a sentence out of it (GUI test 2026-10-25, Workflow 2: "The red cube moves slowly to the right" over a
    shot without a line). Timed text without structured shots keeps every voice."""
    # a line written into the shot text itself ("@Mage says: ...") has no speaker id: every voice stays
    if read_document(context.shots_text) is None or any(_INLINE_LINE.search(shot.text) for shot in chunk.shots):
        return voices
    roots = {image.id: group.root.id for group in subject_groups(context) for image in group.images}
    heard = {roots.get(line.speaker_id, line.speaker_id) for shot in chunk.shots if shot_share.lines_here(shot, chunk)
             for line in shot.spoken if line.text.strip()}
    window = (chunk.story_start_f - chunk.head_frames, chunk.story_end_f)
    placed = {binding.context_id for shot in chunk.shots for binding in shot.media} | {
        clip.context_id for clip in read_audio_clips(context.shots_text) if clip.start * FPS < window[1] and clip.end * FPS > window[0]}
    return {subject: voice for subject, voice in voices.items() if subject in heard or voice.id in placed}
