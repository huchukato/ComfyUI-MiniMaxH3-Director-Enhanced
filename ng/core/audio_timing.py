"""Intersect selected source audio with normalized Shot, audio-lane and sampled-chunk time."""
from .frames import seconds_to_frames
from .issues import Issue
from .shots import parse_shots
from .shot_document import read_audio_clips, read_document


def source_window(item):
    start = seconds_to_frames(item.options.start_s)
    ends = [value for value in (item.options.end_s, item.length_s) if value > 0]
    return start, max(0, seconds_to_frames(min(ends)) - start) if ends else None


def file_window(item):
    """An audio-lane clip's offset is a second in the file itself (the Studio's "From second in file"), not within the
    card's selected range; only the end of the file limits it."""
    return 0, seconds_to_frames(item.length_s) if item.length_s > 0 else None


def shot_windows(context):
    """{context id: [(story start, story end, source offset)]} for Shot bindings; None for timed text."""
    if read_document(context.shots_text) is None:
        return None
    shots, _ = parse_shots(context.shots_text, seconds_to_frames(context.project_seconds))
    windows = {}
    for shot in shots:
        for identity in dict.fromkeys(binding.context_id for binding in shot.media):
            windows.setdefault(identity, []).append((shot.start_f, shot.end_f, 0))
    return windows


def clip_windows(context, modes):
    """The same spans for audio-lane clips of the given modes, clipped to the project's end. A lane plays one clip at a
    time: where a later clip overlaps an earlier one on its lane, only the earlier one plays (clip_issues names it)."""
    total, windows, lanes = seconds_to_frames(context.project_seconds), {}, {}
    for clip in sorted(read_audio_clips(context.shots_text), key=lambda c: c.start):
        start, end = seconds_to_frames(clip.start), min(seconds_to_frames(clip.end), total)
        if end <= start:
            continue
        span = (start, end, seconds_to_frames(clip.offset))
        pieces = outside([span], lanes.get(clip.lane, ())) if clip.lane else [span]
        if clip.lane:
            lanes.setdefault(clip.lane, []).append(span)
        if clip.mode in modes:
            windows.setdefault(clip.context_id, []).extend(pieces)
    return windows


def locked_spans(context):
    """Story spans (start f, end f) whose sound is pinned to a file by Lock: on an audio lane, a Shot, or the whole project,
    each ending where its file ends."""
    spans = []
    for identity, windows in clip_windows(context, ("lock",)).items():
        item = context.item(identity)
        if not item or item.media != "audio" or not item.source:
            continue
        _, available = file_window(item)
        for start, end, offset in windows:
            last = min(end, start + available - offset) if available is not None else end
            if last > start:
                spans.append((start, last))
    laned, bound = set(clip_windows(context, ("lock", "copy", "ref"))), shot_windows(context) or {}
    total = seconds_to_frames(context.project_seconds)
    for item in context.by_media("audio"):
        if item.id in laned or "lock" not in item.effective_usage or not item.source:
            continue
        _, available = source_window(item)
        last = available if available is not None else total
        spans += [(start, min(end, start + last)) for start, end, _ in bound.get(item.id, [(0, total, 0)]) if last > 0]
    return spans


def covers(spans, total, slack=0):
    """Whether the spans together cover story frames 0..total, apart from `slack` frames at the very end."""
    reached = 0
    for start, end in sorted(spans):
        if start > reached:
            return False
        reached = max(reached, end)
    return reached >= total - slack


def outside(spans, taken):
    """The parts of (start, end, offset) spans that no taken (start, end, _) span covers; a later piece keeps its place in the
    source, so cutting never restarts the sound."""
    pieces = list(spans)
    for cut_start, cut_end, _ in taken:
        kept = []
        for start, end, offset in pieces:
            if cut_end <= start or cut_start >= end:
                kept.append((start, end, offset))
                continue
            if start < cut_start:
                kept.append((start, cut_start, offset))
            if cut_end < end:
                kept.append((cut_end, end, offset + cut_end - start))
        pieces = kept
    return pieces


def clip_issues(context):
    """Nothing is cut silently: a clip overlapping an earlier one on its lane, past the project's end, or with an offset past its file's end is named."""
    issues, last_end = [], {}
    for clip in sorted(read_audio_clips(context.shots_text), key=lambda c: c.start):
        if clip.lane and clip.start < last_end.get(clip.lane, 0):
            issues.append(Issue("audio_clip_overlap", "overlaps an earlier clip on its lane; a lane plays one clip at a time, "
                                "so the overlap plays only the earlier clip.", clip.id))
        if clip.lane:
            last_end[clip.lane] = max(last_end.get(clip.lane, 0), clip.end)
        item = context.item(clip.context_id)
        if item is not None and item.length_s > 0 and clip.offset >= item.length_s:
            issues.append(Issue("audio_clip_past_file", "starts at %.2fs in the file, but the file is only %.2fs long; it plays nothing."
                                % (clip.offset, item.length_s), clip.id))
        elif clip.start >= context.project_seconds:
            issues.append(Issue("audio_clip_after_end", "starts after the project ends and is not played.", clip.id))
        elif clip.end > context.project_seconds:
            issues.append(Issue("audio_clip_clipped", "runs past the project end and stops at %.2fs." % context.project_seconds, clip.id))
    return issues


def timed_segments(item, chunk, windows, retention, in_file=False):
    source_start, available = file_window(item) if in_file else source_window(item)
    window_start = chunk.story_start_f - chunk.head_frames
    origins = windows.get(item.id) if windows is not None else None
    spans = origins if origins is not None else [(0, chunk.story_end_f, 0)]
    out = []
    for origin, end, offset in spans:
        first = max(origin, window_start)
        if chunk.continuation_id and retention == "lock" and origin == chunk.story_start_f:
            # Earlier source samples provide hidden VAE context for the known
            # prefix. The delivered audio still begins at the selected offset.
            first = max(window_start, origin - source_start - offset)
        last = min(end, chunk.story_end_f, origin + available - offset if available is not None else end)
        if last <= first:
            continue
        start, length = first - window_start, last - first
        segment = {"type": "audio", "audioFile": item.source, "fileName": item.name, "start": start, "length": length,
                   "trimStart": source_start + offset + first - origin, "retention": retention, "ng_item": item.id, "ng_start": start,
                   "ng_in_file": in_file}
        if origins is not None and retention == "fully_copy":
            segment.update(retention="partially_copy", refNote="Copy this selected clip only at %.3f-%.3fs in the target video; "
                           "its first sample starts at %.3fs. Generate the other sound outside this interval."
                           % (start / 24, (start + length) / 24, start / 24))
        out.append(segment)
    return out
