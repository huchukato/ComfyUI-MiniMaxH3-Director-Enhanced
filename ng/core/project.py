"""Plan a whole project: shots, chunks and the compiled prompt of every chunk, with every correction collected as an Issue.

This is what the Director node does with its inputs, kept free of ComfyUI so it can be tested and reused by a preview endpoint.
"""
import json
import math
import re
from dataclasses import dataclass, replace

from . import frames, limits
from .chunks import ChunkOpening, ContinuityPlan, SequencePlan, plan_chunks
from .compile import compile_chunk
from .context import USAGE_BY_MEDIA, ContextItem, DirectorContext
from .context_checks import check_context, check_guide_times
from .issues import Issue
from .legacy_bridge import decide_mode
from .shots import auto_shots, parse_shots
from .subjects import resolve_subjects
from .shot_document import has_shots, read_document
from .audio_timing import clip_issues, covers, locked_spans
from . import control_timing, continuation, places

CANVAS_MULTIPLE = 32
H3_SHORT_EDGE, H3_MAX_PIXELS = 768, 768 * 1344
DEFAULT_CANVAS = (1344, 768)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "item"


def resolve_speakers(items):
    """A speaker is written as a name or an id; store ids. Returns (items, issues)."""
    by_name = {i.name.casefold(): i.id for i in items}
    ids = {i.id for i in items}
    out, issues = [], []
    for item in items:
        speaker = item.speaker.strip()
        if speaker and speaker not in ids:
            found = by_name.get(speaker.casefold())
            if found is None:
                issues.append(Issue("speaker_unknown", "names '%s' as the speaker, but no context item has that name." % speaker, item.name))
            item = ContextItem.from_dict({**item.to_dict(), "speaker": found or ""})
        out.append(item)
    return tuple(out), issues


def snap_canvas(width, height):
    snapped = tuple(max(CANVAS_MULTIPLE, int(round(v / float(CANVAS_MULTIPLE))) * CANVAS_MULTIPLE) for v in (width, height))
    issues = []
    if snapped != (width, height):
        issues.append(Issue("canvas_snapped", "The size %dx%d was changed to %dx%d: H3 needs multiples of %d."
                            % (width, height, snapped[0], snapped[1], CANVAS_MULTIPLE)))
    return snapped, issues


def h3_canvas(width, height):
    """H3's own canvas for a source picture, as comfy_extras.nodes_minimax_h3.adapt_canvas: 768 short edge, 768*1344 area, /32."""
    ratio = width / float(height)
    w, h = (H3_SHORT_EDGE * ratio, H3_SHORT_EDGE) if ratio >= 1.0 else (H3_SHORT_EDGE, H3_SHORT_EDGE / ratio)
    if w * h > H3_MAX_PIXELS:
        scale = math.sqrt(H3_MAX_PIXELS / (w * h))
        w, h = w * scale, h * scale
    return tuple(max(CANVAS_MULTIPLE, int(round(v / CANVAS_MULTIPLE)) * CANVAS_MULTIPLE) for v in (w, h))


def auto_canvas(context, image_size):
    """Width or height 0 asks for the size of the first picture: the first frame if there is one, else the first image."""
    if context.width > 0 and context.height > 0:
        return context, []
    images = [i for i in context.by_media("image") if i.source]
    source = next((i for i in images if "first_frame" in i.effective_usage), images[0] if images else None)
    size = image_size(source.source) if source and image_size else None
    if size:
        width, height = h3_canvas(*size)
        issue = Issue("canvas_from_image", "The video is %dx%d, taken from '%s'." % (width, height, source.name))
    else:
        width, height = DEFAULT_CANVAS
        issue = Issue("canvas_default", "No picture to take the size from; the video is %dx%d." % DEFAULT_CANVAS)
    return replace(context, width=width, height=height), [issue]


@dataclass(frozen=True)
class ProjectPlan:
    context: DirectorContext
    plan: SequencePlan
    compiled: tuple
    issues: tuple
    places: tuple = ()          # core/places.Place: pictures of earlier shots the render loop writes for later shots
    stills: tuple = ()          # core/stills.Still per part when the Director makes pictures instead of a video

    @property
    def output(self):
        return "images" if self.stills else "video"


@dataclass(frozen=True)
class ChunkJob:
    """One chunk of a planned project: what travels through the loop, one per iteration."""
    project: ProjectPlan
    index: int

    @property
    def chunk(self):
        return self.project.plan.chunks[self.index]

    @property
    def compiled(self):
        return self.project.compiled[self.index]


def jobs(project: ProjectPlan):
    return [ChunkJob(project, n) for n in range(len(project.plan.chunks))]


_CHUNK_REF = re.compile(r"Render part (\d+)$")


def _merge(issues, chunk_count):
    """One entry per distinct problem: the same text found in several chunks is listed once, with the chunks it applies to."""
    order, numbers, first = [], {}, {}
    for issue in issues:
        match = _CHUNK_REF.match(issue.ref)
        key = (issue.code, issue.text, None if match else issue.ref)
        if key not in first:
            first[key], numbers[key] = issue, []
            order.append(key)
        if match:
            numbers[key].append(int(match.group(1)))
    out = []
    for key in order:
        found = sorted(set(numbers[key]))
        ref = key[2] if key[2] is not None else ("" if len(found) == chunk_count else "Render part " + ", ".join(map(str, found)))
        out.append(Issue(first[key].code, first[key].text, ref))
    return tuple(out)


def _prepare(context):
    related, relationship_issues = resolve_subjects(context.items)
    items, issues = resolve_speakers(related)
    (width, height), canvas_issues = snap_canvas(context.width, context.height)
    ctx = DirectorContext.from_dict({**context.to_dict(), "items": [i.to_dict() for i in items], "width": width, "height": height})
    # Structured scenes diagnose roles after selecting their chunk's bindings.
    checks = check_context(ctx) if read_document(ctx.shots_text) is None else []
    return ctx, relationship_issues + issues + canvas_issues + checks


def _opens_on_picture(context, shot):
    """A First frame picture is bound to the shot, by the binding's role or, for a plain binding, by the card's usage."""
    for binding in shot.media:
        item = context.item(binding.context_id)
        if item and item.media == "image" and item.source:
            roles = (binding.role,) if binding.role in USAGE_BY_MEDIA["image"] else item.effective_usage
            if "first_frame" in roles:
                return True
    return False


def _keyframes(context, shot):
    """The shot's Keyframe pictures that carry a time of their own (seconds after the shot's start), earliest first."""
    out = []
    for binding in shot.media:
        item = context.item(binding.context_id)
        if item and item.media == "image" and item.source and binding.at_s >= 0:
            roles = (binding.role,) if binding.role in USAGE_BY_MEDIA["image"] else item.effective_usage
            if "keyframe" in roles:
                out.append(binding)
    return sorted(out, key=lambda b: b.at_s)


def _shortest(head):
    """The shortest part that can follow an edge, with this pin."""
    low, high = frames.delivered_bounds(head)
    return min(frames.delivered_candidates(low, head, low, high))


def _edge(previous, previous_head, wanted):
    """The grid frame nearest to `wanted` at which a part that started at `previous` (with that pin) can end."""
    residue, step = frames.delivered_residue(previous_head), limits.GRID_STEP
    low = previous + residue + (wanted - previous - residue) // step * step
    return min((low, low + step), key=lambda f: (abs(f - wanted), f))


def _place_edge(shot, start, previous, previous_head, until):
    """The cut at which a shot in the place of an earlier one opens its own part, or None; with the issue to report."""
    join = _edge(previous, previous_head, start)
    if join - previous < _shortest(previous_head) or until - join < _shortest(0):
        return None, Issue("place_too_close", "starts too close to the previous render part or the end for a part of its own, "
                           "which the place picture of an earlier shot needs; it is not used.", "shot %d" % shot.index)
    if join == start:
        return join, None
    return join, Issue("place_moved", "starts at %.2fs instead of %.2fs so that it opens a render part of its own for its place "
                       "picture." % (frames.frames_to_seconds(join), frames.frames_to_seconds(shot.start_f)), "shot %d" % shot.index)


def _part_edges(context, shots, total, head, place_targets=()):
    """Source openings and FL2VA picture edges: (cuts, joins, moved shot starts, moved keyframes, issues).

    A shot opening on its own First frame picture starts an unpinned part (cut): inside a pinned part H3 took such a
    picture as the end of the running take and cut one frame later (measured 2026-10-11). A Keyframe picture inside a
    shot ends a part on its last frame, the trained place for a picture; the next part keeps its pin (join), so the
    shot runs on. Parts start on H3's grid, so a shot start or keyframe moves to the nearest grid frame.
    A shot in the place of an earlier shot (`place_targets`) is a cut back to that place: its Place picture comes from the
    render of an earlier part (core/places.py); pinned, H3 kept the market square running (2026-10-18). One that cannot get
    a part of its own goes into `place_targets.dropped`."""
    initial = continuation.initial_opening(context, shots)
    cuts, joins, moved, moved_keys, issues = ({0: initial} if initial else {}), [], {}, {}, []
    previous, previous_head = 0, initial.head_frames if initial else 0
    frame_mode = decide_mode(context) == "fl2va"
    for number, shot in enumerate(shots):
        start = shot.start_f
        following = shots[number + 1] if number + 1 < len(shots) else None
        external = continuation.opening(continuation.shot_source(context, shot), context, shot)
        own_picture = frame_mode and _opens_on_picture(context, shot)
        # the next part edge after this shot's keyframes: the next shot's own opening, else the end of the video
        until = following.start_f if following and (continuation.shot_source(context, following) or
                                                    (frame_mode and _opens_on_picture(context, following))) else total
        if start > 0 and (external or own_picture):
            cut = _edge(previous, previous_head, start)
            if cut - previous < (1 if external else _shortest(previous_head)) or total - cut < (1 if external else _shortest(0)):
                issues.append(Issue("opening_too_close", "has an opening source too close to the previous opening "
                                    "or the end for a render part of its own; it is used inside the running part.", "shot %d" % shot.index))
            else:
                cuts[cut] = external or ChunkOpening()
                previous, previous_head = cut, external.head_frames if external else 0
                if cut != start:
                    moved[shot.id] = start = cut
                    issues.append(Issue("opening_moved", "starts at %.2fs instead of %.2fs so that its source opens a render part."
                                        % (frames.frames_to_seconds(cut), frames.frames_to_seconds(shot.start_f)), "shot %d" % shot.index))
        elif start > 0 and shot.id in place_targets:
            cut, issue = _place_edge(shot, start, previous, previous_head, until)
            issues += [issue] if issue else []
            if cut is None:
                place_targets.dropped.add(shot.id)
            else:
                cuts[cut] = ChunkOpening()
                previous, previous_head = cut, 0
                if cut != start:
                    moved[shot.id] = start = cut
        for binding in _keyframes(context, shot) if frame_mode else ():
            name = context.item(binding.context_id).name
            wanted = start + frames.seconds_to_frames(binding.at_s) + 1      # the part ends on the keyframe; the next one starts after it
            join = _edge(previous, previous_head, wanted)
            if join - previous < _shortest(previous_head) or until - join < _shortest(head):
                issues.append(Issue("keyframe_too_close", "'%s' at %.2fs is too close to the shot's start, end or another picture to end a "
                                    "render part there; it is used inside the running part, where H3 may cut right after it."
                                    % (name, frames.frames_to_seconds(wanted - 1)), "shot %d" % shot.index))
                continue
            joins.append(join)
            previous, previous_head = join, head
            if join != wanted:
                moved_keys[(shot.id, binding.context_id)] = frames.frames_to_seconds(join - 1 - start)
                issues.append(Issue("keyframe_moved", "'%s' is shown at %.2fs instead of %.2fs: a render part ends on it, and parts end on H3's grid."
                                    % (name, frames.frames_to_seconds(join - 1), frames.frames_to_seconds(wanted - 1)), "shot %d" % shot.index))
    return cuts, joins, moved, moved_keys, issues


class _Targets(dict):
    """The shots that take the place of an earlier one, with the ones that could not get a render part of their own."""
    def __init__(self, chosen):
        super().__init__(chosen)
        self.dropped = set()


def _move_shot_starts(shots_text, moved, moved_keys=None):
    """The shots document with the given shots starting at a new frame (the shot before each one ends there) and the
    given keyframes at a new time after their shot's start."""
    data = json.loads(shots_text)
    records = sorted(data["shots"], key=lambda r: float(r["start"]))
    for before, record in zip([None] + records[:-1], records):
        for binding in record.get("media") or []:
            if (record["id"], binding.get("context_id")) in (moved_keys or {}):
                binding["at_s"] = moved_keys[(record["id"], binding["context_id"])]
        if record["id"] not in moved:
            continue
        old, new = float(record["start"]), frames.frames_to_seconds(moved[record["id"]])
        if before is not None and (float(before["end"]) >= new or abs(float(before["end"]) - old) < 1e-6):
            before["end"] = new
        record["start"] = new
    return json.dumps(data)


def _fl2va_pictures(context):
    """First / last frame mode: a Reference picture stays a reference (ng.core.fl2va_refs) and never becomes the First frame
    (the user's choice, 2026-10-12; from 2026-10-11 it had opened its shot when the shot had no picture). A storyboard plans
    shots in References mode only."""
    if context.mode != "fl2va":
        return context, []
    issues = []
    planned = [item.name for item in context.by_media("image") if "storyboard" in item.effective_usage] + sorted(
        {context.item(b.get("context_id")).name for record in read_document(context.shots_text) or [] for b in record.get("media", [])
         if b.get("role") == "storyboard" and context.item(b.get("context_id"))})
    if planned:
        issues.append(Issue("storyboard_unused", "A storyboard plans shots in References mode only; First / last frame mode does not "
                            "use it: %s." % ", ".join(dict.fromkeys(planned))))
    return context, issues


def plan_project(context: DirectorContext, chunk_seconds, continuity: ContinuityPlan, image_size=None) -> ProjectPlan:
    context, canvas_issues = auto_canvas(context, image_size)
    context, fallback_issues = _fl2va_pictures(context)
    canvas_issues = canvas_issues + fallback_issues
    context, issues = _prepare(context)
    issues = canvas_issues + issues
    total = frames.seconds_to_frames(context.project_seconds)
    cuts = joins = ()
    if has_shots(context.shots_text):
        shots, shot_issues = parse_shots(context.shots_text, total)
        chosen, place_issues = places.links(context.shots_text, shots)
        issues = issues + place_issues
        targets = _Targets(chosen)
        if (continuity.head and decide_mode(context) == "fl2va") or continuation.initial_opening(context, shots) or any(
                continuation.shot_source(context, shot) for shot in shots) or chosen:
            cuts, joins, moved, moved_keys, edge_issues = _part_edges(context, shots, total, continuity.head, targets)
            issues = issues + edge_issues
        else:
            moved, moved_keys = {}, {}
        if moved or moved_keys:
            context = replace(context, shots_text=_move_shot_starts(context.shots_text, moved, moved_keys))
            shots, shot_issues = parse_shots(context.shots_text, total)
        planned_places = places.plan_places(context, shots, {k: v for k, v in chosen.items() if k not in targets.dropped})
        if planned_places:
            # the Place cards are references the user did not add: they must not turn an automatic First / last frame
            # project into a References one
            context = places.add_cards(replace(context, mode=decide_mode(context)), planned_places, shots)
            shots, shot_issues = parse_shots(context.shots_text, total)
    else:
        planned_places = ()
        shots, shot_issues = auto_shots(context.idea, total), ()
        initial = continuation.initial_opening(context, shots)
        cuts = {0: initial} if initial else ()
    chunk_frames = frames.seconds_to_frames(chunk_seconds or limits.DEFAULT_CHUNK_SECONDS)
    longest = limits.max_frames(context.width, context.height)
    plan = plan_chunks(total, chunk_frames, continuity, shots, cuts, joins, longest)
    if chunk_frames > longest - continuity.head and longest < limits.LONG_PART_FRAMES:      # shortened by the size, not by 30 s
        issues = list(issues) + [Issue("part_capped", "Render parts are at most %.1f s at %dx%d; a smaller size allows longer ones "
                                       "(up to 30 s at 640x352)." % (frames.frames_to_seconds(longest - continuity.head), context.width,
                                                                     context.height))]
    # A song locked over the whole video is put back into every part from its file, so a long chain does not dull it
    # (elf song: 0.97-0.98 against the song in every part). A last second past the song's end is no chain.
    if covers(locked_spans(context), plan.total_frames, limits.FPS):
        plan = replace(plan, issues=tuple(i for i in plan.issues if i.code != "audio_dulling"))
    compiled = tuple(compile_chunk(context, chunk, continuity) for chunk in plan.chunks)
    issues = list(issues) + list(shot_issues) + list(plan.issues) + check_guide_times(context, plan.total_frames) + clip_issues(context)
    issues.extend(control_timing.issues(context, plan.chunks))
    for one in compiled:
        issues.extend(one.issues)       # the same problem repeats per chunk; _merge lists it once
    return ProjectPlan(context=context, plan=plan, compiled=compiled, issues=_merge(issues, len(plan.chunks)), places=planned_places)


def describe(project: ProjectPlan) -> str:
    """Plain-text summary of the plan, for a preview node."""
    plan = project.plan
    lines = ["%d chunk(s), %.2fs in total (%d frames), continuity: %s" % (
        len(plan.chunks), frames.frames_to_seconds(plan.total_frames), plan.total_frames, plan.continuity.mode)]
    for chunk, compiled in zip(plan.chunks, project.compiled):
        lines.append("  chunk %d: %.2f-%.2fs, %d frames (sampled %d, head %d), %s, %d reference(s), %d shot(s)" % (
            chunk.index + 1, frames.frames_to_seconds(chunk.story_start_f), frames.frames_to_seconds(chunk.story_end_f),
            chunk.delivered_frames, chunk.sampled_frames, chunk.head_frames, compiled.mode, len(compiled.refs), len(chunk.shots)))
    return "\n".join(lines)
