"""Pictures instead of a video: every shot becomes one still (the Director's "Output: Pictures").

H3 makes a still from ONE latent frame; the stock VAE decode of ComfyUI 0.41 decodes it well. A 5-frame context was worse
(stripes, a veil) and slower. Measured 2026-10-19, see _notes/NG/claude-h3-fortsetzung-2026-10-11/bild-test.

A shot's picture is planned like a render part of its own, with the same compiler, so its prompt and its references (the
cards bound to it, <Picture N>) are the ones the video would use. What changes for a still:
  - a First frame picture is the shot's SOURCE: it goes to H3 as a reference with the instruction to keep it and change only
    what the shot asks for (measured: the rest of the picture stays at the VAE's own limit); with an edit mask on its card
    only the masked area is sampled again (adapters/stills.py)
  - a Last frame or Keyframe picture is a plain reference; sound and video cards are not used
Plain arithmetic and planning, no torch, so it can be tested without a GPU."""
import json
from dataclasses import dataclass, replace

from . import frames
from .chunks import Chunk, ChunkShot, ContinuityPlan, SequencePlan
from .compile import compile_chunk
from .issues import Issue
from .project import ProjectPlan, _merge, _prepare, auto_canvas
from .context import USAGE_BY_MEDIA
from .shot_document import has_shots, read_document
from .shots import auto_shots, parse_shots

MIN_FRAMES = 5              # the planner writes a shot's prompt for a clip as long as the shot; H3's nodes take 5 frames at least
FRAME_ROLES = ("first_frame", "last_frame", "keyframe")
SOURCE_LINE = ("<Picture %d> is the picture to change: keep it exactly as it is - the same people, place, framing, light "
               "and colours - and change only this: ")
DESCRIPTION = "detailed_description: "
# A pose card is a guide: described like any card, H3 drew its skeleton into the picture (2026-10-19, Director test shot 6)
POSE_GUIDE = ("a pose guide (%s). Only the body pose is taken from it; the drawing itself - its lines, colours and "
              "background - never appears in the picture")


@dataclass(frozen=True)
class Still:
    """What one still is made from, besides its prompt: the source picture it changes, and the card's edit mask."""
    index: int
    shot_id: str = ""
    source_id: str = ""         # the context item whose picture is the source; "" = a new picture
    source: str = ""            # its file in the input folder
    mask: str = ""              # white = change; "" = the whole picture may change (the prompt keeps the rest)


def still_context(context):
    """The context with sound and video cards left out and every frame picture made a reference. Returns
    (context, the ids of the First frame cards, issues)."""
    kept, sources, issues = [], set(), []
    for item in context.items:
        if item.media in ("audio", "video"):
            issues.append(Issue("still_unused", "Pictures use no %s cards; this one is left out." % item.media, item.name))
            continue
        if item.media == "image" and "pose" in item.content:
            item = replace(item, description=POSE_GUIDE % (item.description.strip().rstrip(".") or "a figure's pose"))
        if item.media == "image":
            frame_roles = [r for r in item.effective_usage if r in FRAME_ROLES]
            if "first_frame" in frame_roles:
                sources.add(item.id)
            if frame_roles:
                item = replace(item, usage=tuple(dict.fromkeys("reference" if r in FRAME_ROLES else r for r in item.effective_usage)))
        kept.append(item)
    return replace(context, items=tuple(kept)), sources, issues


def shot_sources(context):
    """The shots document with every frame role on a picture made a reference, and per shot the First frame picture it
    changes (the binding's role, or for a plain binding the card's usage, as project._opens_on_picture reads it)."""
    if read_document(context.shots_text) is None:
        return context.shots_text, {}
    data, sources = json.loads(context.shots_text), {}
    for record in data["shots"]:
        for binding in record.get("media") or []:
            item = context.item(binding.get("context_id"))
            if item is None or item.media != "image":
                continue
            role = binding.get("role", "context")
            roles = (role,) if role in USAGE_BY_MEDIA["image"] else item.effective_usage
            if "first_frame" in roles and item.source:
                sources.setdefault(record["id"], item.id)
            if role in FRAME_ROLES:
                binding["role"] = "reference"
                binding.pop("at_s", None)
    return json.dumps(data), sources


def _chunk(index, shot, last):
    """The shot as a part of its own at its place on the timeline (the Studio draws "Picture N" under the shot)."""
    length = max(shot.end_f - shot.start_f, MIN_FRAMES)
    piece = ChunkShot(shot_index=shot.index, local_start_f=0, local_end_f=length, text=shot.text, carried=False,
                      continues=False, shot_id=shot.id, media=shot.media, spoken=(), locked_fields=shot.locked_fields,
                      shot_start_f=shot.start_f, shot_end_f=shot.start_f + length)
    return Chunk(index=index, story_start_f=shot.start_f, delivered_frames=length, head_frames=0, shots=(piece,), is_last=last)


def _with_source(compiled, source_id, override):
    """The source's <Picture N> named as the picture to change, at the start of the description (or of the prompt)."""
    pictures = [r.ctx_id for r in compiled.of_kind("picture")]
    if not source_id or source_id not in pictures or override:
        return compiled
    line = SOURCE_LINE % (pictures.index(source_id) + 1)
    prompt = compiled.prompt
    prompt = prompt.replace(DESCRIPTION, DESCRIPTION + line, 1) if DESCRIPTION in prompt else line + prompt
    return replace(compiled, prompt=prompt)


def plan_stills(context, image_size=None) -> ProjectPlan:
    """One still per shot (or one from the idea when there are no shots)."""
    context, canvas_issues = auto_canvas(context, image_size)
    shots_text, by_shot = shot_sources(context)
    context, sources, still_issues = still_context(replace(context, shots_text=shots_text))
    context, issues = _prepare(context)
    issues = list(canvas_issues) + still_issues + list(issues)
    total = frames.seconds_to_frames(context.project_seconds)
    if has_shots(context.shots_text):
        shots, shot_issues = parse_shots(context.shots_text, total)
        issues += list(shot_issues)
    else:
        shots = auto_shots(context.idea, total)
        if not shots and sources:
            shots = auto_shots("Change the picture as the cards describe.", total)
    if not shots:
        issues.append(Issue("no_text", "Write an idea or a shot: each shot becomes one picture."))
    continuity = ContinuityPlan(mode="none")
    chunks, compiled, stills = [], [], []
    for index, shot in enumerate(shots):
        source_id = by_shot.get(shot.id, "")
        if not source_id and not has_shots(context.shots_text) and len(sources) == 1:
            source_id = next(iter(sources))         # one picture to change and no shots: the idea changes it
        chunk = _chunk(index, shot, index == len(shots) - 1)
        one = _with_source(compile_chunk(context, chunk, continuity), source_id, context.prompt_override.strip())
        item = context.item(source_id) if source_id else None
        chunks.append(chunk)
        compiled.append(one)
        stills.append(Still(index, shot.id, source_id, item.source if item else "", item.options.edit_mask if item else ""))
        issues.extend(one.issues)
    plan = SequencePlan(requested_frames=max(1, total), continuity=continuity, chunks=tuple(chunks))
    return ProjectPlan(context=context, plan=plan, compiled=tuple(compiled), issues=_merge(issues, len(chunks)), stills=tuple(stills))
