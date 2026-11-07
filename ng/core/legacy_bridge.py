"""Translate a Director Context and one chunk into the legacy `timeline_data` that `minimax_plan.plan_timeline` understands.

The legacy planner is the one place that knows how H3 wants references labelled, retention markers worded, dialogue formatted and
limits enforced, and it has hundreds of checks behind it. NG reuses it as the prompt compiler instead of writing a second one;
this module is the only door into it. Anything legacy needs that NG does not model is filled with a neutral default here.
"""

import re

from ... import minimax_plan as plan
from .chunks import Chunk
from .context import DirectorContext
from .mentions import replace_mentions
from .context_options import retention_note
from .issues import Issue
from .subjects import subject_groups
from . import shot_share
from .shot_bindings import spoken_text, voices_heard
from .shot_document import has_shots, read_document, read_look
from .picture_segments import anchor_segments, storyboard_segments
from .lyrics import SINGER, sung_lines
from .audio_timing import clip_windows, file_window, outside, shot_windows, source_window, timed_segments

FAR_AWAY = 10 ** 6          # parked past any window: a reference, not part of the soundtrack
_KIND = {"character": "person", "face": "person", "animal": "animal", "object": "object", "outfit": "clothing", "prop": "prop",
         "environment": "environment", "location": "environment", "style": "style", "lighting": "style", "composition": "style",
         "pose": "pose", "action": "action", "expression": "expression", "effect": "effect"}
_RETENTION = {"high": "fully_preserved", "medium": "partially_preserved", "low": "weak_reference"}
_AUDIO_RETENTION = {"voice": "reference", "music_style": "weak_reference", "copy": "fully_copy", "lock": "lock",
                    "rhythm": "weak_reference", "sound_reference": "reference"}


class Mapping:
    """What each legacy slot or file stands for, so results can be translated back to context ids.

    `by_source` is only a fallback; planned guides already carry their Context IDs.
    """

    def __init__(self, slot_items, by_source, voice_items=None):
        self.slot_items = tuple(slot_items)   # context id per legacy subject slot (slot number - 1)
        self.by_source = dict(by_source)      # file path -> context id (first item wins)
        self.voice_items = dict(voice_items or {})     # 1-based subject slot -> voice context id

    def media_id(self, seg, source):
        return seg.get("ng_item") or self.voice_items.get(seg.get("voice_slot")) or self.by_source.get(source, "")

def has_references(context):
    for item in context.items:
        usage = item.effective_usage
        if item.media == "image" and "reference" in usage:
            return True
        if item.uses_video_reference or (item.media == "audio" and set(usage) & set(_AUDIO_RETENTION) - {"lock"}):
            return True
    return False


def decide_mode(context):
    """`context.mode` is the user's explicit choice; the actual per-chunk mode comes out of the legacy planner,
    which already treats a first/last frame guide as fl2va (minimax_plan.py, `has_keyframe`)."""
    if context.mode != "auto":
        return context.mode
    return "ref2va" if has_references(context) else "fl2va"


def _kind(item):
    for value in item.content:
        if value in _KIND:
            return _KIND[value]
    return "person"


def _subject_items(context):
    return [group.root for group in subject_groups(context)]


def _slot(item, voices, images):
    voice = voices.get(item.id)
    note = retention_note(item.options)
    if len(images) > 1 and not note:
        note = "Preserve the base identity; linked references control only their stated properties."
    return {"images": [{"name": image.source, "fileName": image.name, "ng_item": image.id} for image in images],
            "description": item.description, "shortName": item.name, "kind": _kind(item),
            "retention": _RETENTION[item.preserve], "retentionNote": note,
            "voice": {"audioFile": voice.source, "fileName": voice.name} if voice else None}


def _voices_by_speaker(context):
    """Voice items grouped by the subject they speak for: {subject id: [item, ...]} in project order.

    A subject may have more than one take. H3's slot takes a single voice file per subject, so the first take wins
    the slot and every further take stays an ordinary reference audio segment. Both facts are reported by
    `extra_voice_issues`, so a second take is never silently demoted to "some audio".
    """
    voices = {}
    subjects = {item.id for item in _subject_items(context)}
    inferred = _inferred_speakers(context, subjects)
    for item in context.by_media("audio"):
        speaker = item.speaker or inferred.get(item.id, "")
        if "voice" in item.effective_usage and speaker in subjects and item.source:
            voices.setdefault(speaker, []).append(item)
    return {subject: takes[0] for subject, takes in voices.items()}, \
           {subject: takes[1:] for subject, takes in voices.items() if len(takes) > 1}


def _inferred_speakers(context, subjects):
    """{voice card id: subject id} for a voice card without "Whose voice" that a shot names as the speaker of a line,
    when that shot shows exactly one figure: the line is spoken there, so the voice is that figure's. Without this the
    voice reached no slot and nothing said so (BUG-019)."""
    out = {}
    for record in read_document(context.shots_text) or []:
        figures = {b.get("context_id") for b in record.get("media", []) if b.get("context_id") in subjects}
        for line in record.get("spoken", []):
            item = context.item(line.get("speaker_id", ""))
            if item and item.media == "audio" and not item.speaker and len(figures) == 1:
                out.setdefault(item.id, next(iter(figures)))
    return out


def extra_voice_issues(extra, context=None):
    """One Issue per further take, naming the subject it was meant for; and one per voice whose figure was inferred."""
    out = []
    if context is not None:
        subjects = {item.id for item in _subject_items(context)}
        for voice, subject in _inferred_speakers(context, subjects).items():
            out.append(Issue("voice_speaker_inferred", "has no \"Whose voice\"; it speaks for '%s' because a shot showing only "
                             "that figure gives it a line. Set \"Whose voice\" on the card to make this fixed."
                             % context.item(subject).name, context.item(voice).name))
    for takes in extra.values():
        for item in takes:
            out.append(Issue("voice_extra_take",
                             "is a further voice take for the same figure; the first take keeps the subject's voice "
                             "slot and this one is sent as an additional reference.", item.name))
    return out


def _voiced(context, skip=()):
    """A picture card that speaks without a reference slot speaks as @voice(Name): a First / last frame figure in FL2VA,
    or one next to the Subjects in Ref2VA. "@Alice says: ..." stayed prose, without <d> tags, before (BUG-090)."""
    return {item.name: "@voice(%s)" % item.name for item in context.items if item.media == "image" and item.name and item.name not in skip}


_SPOKEN_AFTER_PROSE = re.compile(r"(?<=[.!?])\s+(?=@[^:.!?]*:)")


def _own_lines(text, known):
    """A spoken line written after prose on the same line ("The camera pushes in. @Alice says: Hurry!") goes on a line
    of its own; the compiler reads dialogue line by line and took the whole line for prose (BUG-090)."""
    out = []
    for line in text.splitlines():
        parts = _SPOKEN_AFTER_PROSE.split(line)
        while len(parts) > 1 and not any(parts[-1].startswith("@" + name) for name in known):
            parts[-2:] = [parts[-2] + " " + parts[-1]]
        out += [parts[0]] if len(parts) == 1 else [" ".join(parts[:-1]), parts[-1]]
    return "\n".join(out)


def _spoken_lines(text, voices, known):
    """Lines of the form "@Name [Language] says: ..." with a voiced Name get their speaker as @voice(Name)."""
    lines = []
    for line in _own_lines(text, known).splitlines():
        head, colon, rest = line.partition(":")
        bare = re.sub("|".join(re.escape("@" + name) for name in sorted(known, key=len, reverse=True)) or "$^", "", head)
        spoken = replace_mentions(head, voices, known) + colon + rest
        lines.append(spoken if colon and not re.search(r"[.!?]", bare) and plan.DIALOGUE_RE.match(spoken.strip()) else line)
    return "\n".join(lines)


def _tag_substitutor(slot_items, context):
    names = {context.item(i).name: "@ref%d" % n for n, i in enumerate(slot_items, 1)}
    known = [item.name for item in context.items]
    voices = _voiced(context, skip=names)
    return lambda text: replace_mentions(_spoken_lines(text, voices, known), names, known)


def _plain_substitutor(subjects, context):
    """Without reference slots there is no <Subject N> to point at: a mention is the name, a spoken line names its voice."""
    known = [item.name for item in context.items]
    names, voices = {s.name: s.name for s in subjects}, {**_voiced(context), **{s.name: "@voice(%s)" % s.name for s in subjects}}

    def substitute(text):
        lines = []
        for line in _own_lines(text, known).splitlines():
            head, colon, rest = line.partition(":")
            spoken = replace_mentions(head, voices, known) + colon + replace_mentions(rest, names, known)
            # "@Name [German] says: ..." is a spoken line; a sentence before the first colon (e.g. the Prompt followed
            # by "Visual style: ...") is prose, whatever the colon later in the line belongs to.
            bare = re.sub("|".join(re.escape("@" + name) for name in sorted(known, key=len, reverse=True)) or "$^", "", head)
            dialogue = colon and not re.search(r"[.!?]", bare) and plan.DIALOGUE_RE.match(spoken.strip())
            lines.append(spoken if dialogue else replace_mentions(line, names, known))
        return "\n".join(lines)
    return substitute


def _lane_references(item, chunk, spans):
    """A reference clip is not placed in the soundtrack; its whole file window is sent once to every chunk it touches.
    Two clips of one card with different windows are two references."""
    window_start = chunk.story_start_f - chunk.head_frames
    source_start, available = file_window(item)
    out = []
    for origin, end, offset in spans:
        if end <= window_start or origin >= chunk.story_end_f:
            continue
        length = end - origin if available is None else min(end - origin, available - offset)
        usage = next((u for u in item.effective_usage if u in _AUDIO_RETENTION and u not in ("copy", "lock")), "sound_reference")
        if length > 0:
            out.append({"type": "audio", "audioFile": item.source, "fileName": item.name, "start": FAR_AWAY, "length": length,
                        "trimStart": source_start + offset, "retention": _AUDIO_RETENTION[usage], "ng_item": item.id, "ng_in_file": True})
    return list({(segment["trimStart"], segment["length"]): segment for segment in out}.values())


def _shot_bound(item, chunk, windows, lanes, needs_reference):
    """A card on an audio lane may also be bound to Shots. Where its lane clips play, they win; elsewhere each Shot binding
    plays from the start of its Shot, with the card's own role (the scoped usage also carries the roles its lane clips added),
    so the same sound is never laid twice over the same time."""
    if not windows or item.id not in windows:
        return []
    lane_modes = {mode for mode in ("lock", "copy") if item.id in lanes[mode]}
    usage = [u for u in item.effective_usage if u in _AUDIO_RETENTION]
    usage = next(iter([u for u in usage if u not in lane_modes] or usage), "sound_reference")
    if usage in ("copy", "lock"):
        free = outside(windows[item.id], [span for mode in ("lock", "copy") for span in lanes[mode].get(item.id, ())])
        return timed_segments(item, chunk, {item.id: free}, _AUDIO_RETENTION[usage])
    window_start = chunk.story_start_f - chunk.head_frames
    if not needs_reference or not any(start < chunk.story_end_f and end > window_start for start, end, _ in windows[item.id]):
        return []
    source_start, available = source_window(item)
    return [{"type": "audio", "audioFile": item.source, "fileName": item.name, "start": FAR_AWAY, "length": available if available is not None else 48,
             "trimStart": source_start, "retention": _AUDIO_RETENTION[usage], "ng_item": item.id}]


def _audio_segments(context, chunk, voices):
    segments = []
    used = {v.id for v in voices.values()}
    windows = shot_windows(context)
    lanes = {mode: clip_windows(context, (mode,)) for mode in ("lock", "copy", "ref")}
    for item in context.by_media("audio"):
        if not item.source:
            continue
        if item.id in used:
            for mode in ("lock", "copy"):
                if item.id in lanes[mode]:
                    segments.extend(timed_segments(item, chunk, lanes[mode], _AUDIO_RETENTION[mode], in_file=True))
            segments.extend(_lane_references(item, chunk, lanes["ref"].get(item.id, ())))
            continue
        if any(item.id in spans for spans in lanes.values()):
            for mode in ("lock", "copy"):
                if item.id in lanes[mode]:
                    segments.extend(timed_segments(item, chunk, lanes[mode], _AUDIO_RETENTION[mode], in_file=True))
            references = _lane_references(item, chunk, lanes["ref"].get(item.id, ()))
            segments.extend(references + _shot_bound(item, chunk, windows, lanes, not references))
            continue
        usage = next((u for u in item.effective_usage if u in _AUDIO_RETENTION), None)
        if usage is None:
            continue
        if usage in ("copy", "lock"):
            segments.extend(timed_segments(item, chunk, windows, _AUDIO_RETENTION[usage]))
        else:
            source_start, available = source_window(item)
            segments.append({"type": "audio", "audioFile": item.source, "fileName": item.name, "start": FAR_AWAY,
                             "length": available if available is not None else 48, "trimStart": source_start,
                             "retention": _AUDIO_RETENTION[usage], "ng_item": item.id})
    return segments


def _motion_segments(context):
    out = []
    for item in context.by_media("video"):
        if item.source and item.uses_video_reference:
            source_start, available = source_window(item)
            length = available if available is not None else 120
            out.append({"type": "video", "videoFile": item.source, "fileName": item.name, "start": FAR_AWAY, "length": length,
                        "trimStart": source_start, "retention": _RETENTION[item.preserve],
                        "ng_item": item.id, "paired_audio": item.options.video_audio == "reference"})
    return out


CONTINUE_SCENE = "Continue the same scene and action from the preceding video, preserving the subject and setting. "


def _shot_text(shot, substitute, automatic=False, context=None, chunk=None):
    """A shot that began in an earlier chunk keeps its action but not its spoken lines: those belong to where the shot starts
    (or to the next part when it starts in a part's last two seconds, shot_share.lines_here). Nor its camera move: the part before already made it, and each part read "the camera pushes in" as a new push, so a
    20 s shot over three parts pushed in three times and lost its look (AUDIT-010, measured 2026-10-11).

    A shot over several parts gives each part only the action of its own share of the shot's time (ng.core.shot_share)."""
    text = substitute(spoken_text(shot, context)[0] if context else shot.text)
    if chunk is not None and not automatic and (shot.carried or shot.continues):
        prose = [line for line in text.splitlines() if not plan.DIALOGUE_RE.match(line.strip())]
        spoken = [line for line in text.splitlines() if plan.DIALOGUE_RE.match(line.strip())]
        shared = shot_share.share("\n".join(prose), shot.shot_start_f, shot.shot_end_f, max(shot.shot_start_f, chunk.story_start_f),
                                  min(shot.shot_end_f, chunk.story_end_f), chunk.story_start_f - chunk.head_frames)
        if shared == shot_share.HEAD_ONLY:
            return shared
        text = "\n".join([shared] + spoken)
    if not shot_share.lines_here(shot, chunk):
        text = "\n".join(line for line in text.splitlines() if not plan.DIALOGUE_RE.match(line.strip()))
    if not shot.carried:
        text = shot_share.with_effect(text, shot.effect, plan.DIALOGUE_RE)
    if shot.carried:
        if not automatic:
            text = shot_share.without_camera_moves(text, plan.DIALOGUE_RE)
        if text.strip():
            text = CONTINUE_SCENE + text
    return text


def _sung_line(line, speakers, context):
    _, speaker, language, text = line
    # Without a reference subject (First / last frame) the singer is named, not "the singer".
    named = context.item(speaker).name if speaker and context.item(speaker) else SINGER
    who = "@" + speakers[speaker].name if speaker in speakers else "@voice(%s)" % named
    return "%s [%s] sings: %s" % (who, language, text)


def _add_sung_lines(segments, context, chunk, groups, substitute):
    """The song's own lines go into the shot where they are sung, after what the shot itself says; a carried shot keeps
    them too, because they are timed, not tied to where the shot began."""
    lines = sung_lines(context, chunk)
    if not lines:
        return
    speakers = {image.id: group.root for group in groups for image in group.images}
    if not segments:
        segments.append({"type": "text", "start": 0, "length": chunk.sampled_frames, "prompt": ""})
    for line in lines:
        local = line[0]
        segment = next((seg for seg in segments if seg["start"] <= local < seg["start"] + seg["length"]),
                       min(segments, key=lambda seg: abs(seg["start"] - local)))
        segment["prompt"] = "\n".join(part for part in (segment["prompt"], substitute(_sung_line(line, speakers, context))) if part)


# Text card usages written into every part's prompt as a line of their own (a Scene note only without Shots, see below).
RULE_USAGES = frozenset(("style", "rule", "character", "world", "scene", "camera", "dialogue", "constraint", "instruction"))


def _global_prompt(context):
    # With structured Shots the Prompt is the story they were made from; what every part shares is the Look.
    # Timed text ("0-8: ...") predates both and keeps the Prompt as its global line.
    if read_document(context.shots_text) is not None:
        parts = [read_look(context.shots_text)]
    else:
        parts = [context.idea.strip()] if has_shots(context.shots_text) else []
    if context.style and context.style != "None":
        parts.append("Visual style: %s." % context.style)
    structured = read_document(context.shots_text) is not None
    for item in context.by_media("text"):
        # A Scene note is story: with Shots it reached H3 through them (AI: split into shots reads it), so it is not
        # pasted into every part again; the 27 s elf song carried its whole verse into each of three parts that way.
        if structured and has_shots(context.shots_text) and item.effective_usage == ("scene",):
            continue
        if item.source.strip() and set(item.effective_usage) & RULE_USAGES:
            owners = [context.item(identity).name for identity in item.subject_ids if context.item(identity)]
            prefix = "For %s: " % " and ".join("@" + name for name in owners) if owners else ""
            parts.append(prefix + item.source.strip())
    for item in context.by_media("video"):
        roles = set(item.effective_usage)
        if "camera" in roles:
            parts.append("Use %s as the camera movement reference. %s" % (item.name, item.description))
        if "structure" in roles:
            parts.append("Follow the overall scene structure and rhythm of %s. %s" % (item.name, item.description))
        if item.description.strip() and roles & {"motion", "continue"} and not roles & {"camera", "structure"}:
            parts.append("Video context %s: %s" % (item.name, item.description))
    for item in context.by_media("audio"):
        if "rhythm" in item.effective_usage:
            parts.append("Follow the rhythm of %s. %s" % (item.name, item.description))
    return " ".join(p for p in parts if p)


def build_timeline(context: DirectorContext, chunk: Chunk, mode: str, guides):
    """Return (timeline_data dict, Mapping, voice_notes) for one chunk."""
    groups = subject_groups(context)
    subjects = [group.root for group in groups]
    voices, extra_voices = _voices_by_speaker(context)
    heard = voices_heard(voices, context, chunk)      # the slots; every voice card is kept out of the general audio
    substitute = _tag_substitutor([s.id for s in subjects], context) if mode == "ref2va" else _plain_substitutor(subjects, context)
    segments = [{"type": "text", "start": s.local_start_f, "length": s.local_end_f - s.local_start_f,
                 "prompt": _shot_text(s, substitute, automatic=not has_shots(context.shots_text), context=context, chunk=chunk)}
                for s in chunk.shots]
    _add_sung_lines(segments, context, chunk, groups, substitute)
    ref_on = mode == "ref2va"
    texts = list(segments)
    segments += anchor_segments(context, chunk, guides, texts)
    if ref_on:
        segments += storyboard_segments(context, chunk, texts)
    tdata = {"reference_mode": "REF2VA" if ref_on else "OFF", "prompt_format": "minimax", "global_prompt": substitute(_global_prompt(context)),
             "segments": segments, "subjects": [_slot(group.root, heard, group.images) for group in groups] if ref_on else [],
             "subjectSlotCount": max(len(subjects), 1), "audioSegments": _audio_segments(context, chunk, voices),
             "motionSegments": _motion_segments(context) if ref_on else [], "overall_soundscape": context.soundscape, "opening_in_shot": True,
             "summary": shot_share.summary_sentence([s["prompt"] for s in texts], CONTINUE_SCENE, plan.DIALOGUE_RE) if ref_on else "",
             "non_diegetic_music": context.music}
    by_source = {}
    for item in context.items:
        if item.media == "text":
            continue
        by_source.setdefault(item.source, item.id)
    voice_items = {number: heard[s.id].id for number, s in enumerate(subjects, 1) if s.id in heard}
    notes = extra_voice_issues(extra_voices, context) + [issue for shot in chunk.shots for issue in spoken_text(shot, context)[1]]
    return tdata, Mapping([s.id for s in subjects], by_source, voice_items), notes
