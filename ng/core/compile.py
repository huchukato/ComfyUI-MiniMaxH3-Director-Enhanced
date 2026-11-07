"""Compile one chunk of a Director Context into what the model needs: the H3 prompt and the list of media to send, in label order.

The compiling itself is the legacy planner's (see legacy_bridge); this module turns its result into NG's own types, so nothing
above it depends on legacy dictionaries, and attaches NG's warnings.
"""
from dataclasses import dataclass, replace

from ... import minimax_plan as plan
from . import continuation, fields, limits
from .chunks import Chunk, ContinuityPlan
from .context import DirectorContext, check_item
from .issues import Issue
from .legacy_bridge import build_timeline, decide_mode
from .shot_share import effect_tokens, keep_effects, lines_here
from .media_labels import resolve_media_mentions, resolve_guide_mentions, resolve_lock_mentions, prompt_labels, read_prompt_labels
from .asset_prompt import apply_asset_relations
from .shot_bindings import scoped_context
from .media_ref import KINDS, MediaRef
from .guide_timing import plan_guides
from .fl2va_refs import add_references
from .part_prompt import prompt_key
from .shot_document import read_part_prompts
from .prompt_sources import prompt_sources


@dataclass(frozen=True)
class CompiledChunk:
    index: int
    mode: str                  # t2va | fl2va | ref2va
    prompt: str
    refs: tuple = ()           # MediaRef in the order the labels <Picture N>/<Video N>/<Audio N> number them
    issues: tuple = ()
    prompt_labels: tuple = ()  # (native label, owning context ID); optional display metadata for v1 saves
    key: str = ""              # of the compiled prompt; a part's own prompt is valid only for this key
    source: str = "compiled"   # compiled | ai | user (the part's own prompt) | manual (prompt_override)
    sources: tuple = ()        # what the prompt is made from (prompt_sources.py), display only
    SCHEMA_VERSION = 1

    def of_kind(self, kind):
        return tuple(r for r in self.refs if r.kind == kind)

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "index": self.index, "mode": self.mode, "prompt": self.prompt,
                "refs": [r.to_dict() for r in self.refs], "issues": [i.to_dict() for i in self.issues],
                "prompt_labels": dict(self.prompt_labels), "key": self.key, "source": self.source, "sources": list(self.sources)}

    @classmethod
    def from_dict(cls, data, path="compiled"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        return cls(index=int(fields.read_number(data, "index", path, minimum=0)), mode=fields.read_choice(data, "mode", path, ("t2va", "fl2va", "ref2va"), None),
                   prompt=fields.read_str(data, "prompt", path),
                   refs=tuple(MediaRef.from_dict(d, "%s.refs[%d]" % (path, n)) for n, d in enumerate(fields.read_list(data, "refs", path))),
                   issues=tuple(Issue.from_dict(d) for d in fields.read_list(data, "issues", path)),
                   prompt_labels=read_prompt_labels(data, path), key=fields.read_str(data, "key", path, ""),
                   source=fields.read_choice(data, "source", path, ("compiled", "ai", "user", "manual"), "compiled"),
                   sources=tuple(entry for entry in data.get("sources") or () if isinstance(entry, dict)))


def _picture_refs(result, mapping):
    refs = []
    for slot in result["ref_image_slots"]:
        if slot["source"] == "char":
            ctx = slot["image"].get("ng_item") or mapping.slot_items[slot["slot"]]
            refs.append(MediaRef("picture", ctx, slot["image"].get("name", "")))
        elif slot["source"] == "timeline":
            source = slot["event"]["seg"].get("imageFile", "")
            refs.append(MediaRef("picture", mapping.media_id(slot["event"]["seg"], source), source))
    return refs


def _timed(kind, seg, key, mapping):
    source = seg.get(key, "")
    return MediaRef(kind, mapping.media_id(seg, source), source, int(seg.get("ng_start", seg.get("start", 0) if kind == "lock" else 0)),
                    int(seg.get("length", 0)), int(seg.get("trimStart", 0)))


def _media_refs(result, mapping, context):
    refs = _picture_refs(result, mapping)
    refs += [_timed("video", s, "videoFile", mapping) for s in result["ref_video_segs"]]
    refs += [_selected_audio(context, _timed("audio", s, "audioFile", mapping), s) for s in result["ref_audio_segs"]]
    refs += [_timed("lock", s, "audioFile", mapping) for s in result["lock_audio_segs"]]
    return refs


def _issues(context, chunk, result, continuity):
    # a continued chunk deliberately has no spoken line for a shot that began earlier (see legacy_bridge._shot_text)
    # ... nor a shot that starts too late in it: the next part says its lines (legacy_bridge.lines_here)
    resumed = any(s.carried or not lines_here(s, chunk) for s in chunk.shots)
    out = [Issue("planner", text, "Render part %d" % (chunk.index + 1)) for text in result["ref_warnings"]
           if not (resumed and "has no spoken line" in text)]
    placed = {b.context_id for shot in chunk.shots for b in shot.media}     # a Keyframe on a shot has its time there
    for item in context.items:
        out.extend(i for i in check_item(item) if not (i.code == "usage_pending" and item.id in placed))
    # A manual prompt replaces the generated one, so a missing idea or shot text is no gap then; nor is it when a Text
    # card of this chunk carries the text (BUG-036: the note was in the prompt while the warning said "bare placeholder").
    noted = any(item.media == "text" and item.source.strip() for item in context.items)
    if not context.prompt_override.strip() and not context.idea.strip() and not noted and not any(
            s.text.strip() or any(line.text.strip() for line in s.spoken) for s in chunk.shots):
        out.append(Issue("no_text", "There is no text for this render part; the prompt falls back to a bare placeholder.", "Render part %d" % (chunk.index + 1)))
    if context.prompt_override.strip():
        out.append(Issue("prompt_override", "Manual prompt replaces every chunk prompt; references and timing remain as planned."))
    return out


def _selected_audio(context, ref, seg):
    """An audio reference plays the card's selected Start/End range; an audio-lane clip names its own file seconds instead."""
    item = context.item(ref.ctx_id)
    if not item or seg.get("ng_in_file"):
        return ref
    start = max(ref.trim_start_f, int(round(item.options.start_s * limits.FPS)))
    end = int(round(item.options.end_s * limits.FPS)) if item.options.end_s else 0
    length = min(ref.length_f, max(0, end - start)) if end else ref.length_f
    return MediaRef(ref.kind, ref.ctx_id, ref.source, ref.start_f, length, start)


def compile_chunk(context: DirectorContext, chunk: Chunk, continuity: ContinuityPlan) -> CompiledChunk:
    original = context
    context, binding_issues = scoped_context(context, chunk)
    mode = decide_mode(context)
    guide_context = replace(original, items=tuple(original.item(item.id) for item in context.items))
    item = context.item(chunk.continuation_id) if chunk.continuation_id else None
    wanted = continuation.preferred_frames(replace(original, mode=mode), item) if item else limits.CONTINUE_VIDEO_FRAMES
    guides, timing_issues = plan_guides(guide_context, chunk, mode, continue_frames=wanted)
    tdata, mapping, voice_notes = build_timeline(context, chunk, mode, guides)
    result = plan.plan_timeline(tdata, 0, chunk.sampled_frames, float(limits.FPS), use_custom_audio=True, use_custom_motion=True,
                                prepend_text=context.prepend_text, prompt_format="minimax")
    refs = _media_refs(result, mapping, context) + list(guides)
    related_prompt, relation_issues = apply_asset_relations(result, mapping, context, refs)
    prompt = resolve_media_mentions(effect_tokens(related_prompt), context, refs)
    if mode == "fl2va" and context.prompt_override.strip() == "":
        prompt, refs = add_references(prompt, context, refs, chunk)
    labels = prompt_labels(result, mapping, context, refs)
    prompt, guide_issues = (prompt, ()) if context.prompt_override.strip() else resolve_guide_mentions(prompt, context, refs, labels)
    prompt, lock_issues = (prompt, ()) if context.prompt_override.strip() else resolve_lock_mentions(prompt, context, refs)
    final, source, own_issues = _own_prompt(original, chunk, prompt)
    return CompiledChunk(index=chunk.index, mode=result["mode"], prompt=final, refs=tuple(refs),
                         issues=binding_issues + timing_issues + tuple(voice_notes) + relation_issues + guide_issues + lock_issues + own_issues + tuple(_issues(context, chunk, result, continuity)),
                         prompt_labels=labels, key=prompt_key(prompt), source=source,
                         sources=prompt_sources(original, chunk, refs, tdata["segments"]))


def _own_prompt(context, chunk, compiled):
    """The prompt that goes to the sampler: the manual one, else the part's own if it was written from this very compiled
    prompt, else the compiled one. An own prompt from before a plan change is kept for the user but not used."""
    if context.prompt_override.strip():
        return context.prompt_override.strip(), "manual", ()
    own = read_part_prompts(context.shots_text).get(chunk.index)
    if own is None:
        return compiled, "compiled", ()
    key, text, by = own
    if key == prompt_key(compiled) and text.strip():
        return keep_effects(compiled, text.strip()), by, ()
    return compiled, "compiled", (Issue("part_prompt_outdated", "The plan changed after this part's own prompt was written, so the "
                                        "compiled prompt is used. Rewrite or edit it in Prompts per render part.", "Render part %d" % (chunk.index + 1)),)

