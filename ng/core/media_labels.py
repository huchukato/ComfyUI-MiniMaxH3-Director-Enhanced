"""Resolve named media and frame guides against actual native H3 presentation."""
from .mentions import replace_mentions
from . import fields
from .issues import Issue


def media_labels(context, refs):
    """Native H3 numbers video soundtracks before standalone audio references."""
    labels = []
    videos = [ref for ref in refs if ref.kind == "video"]
    audio_number = 0
    for number, ref in enumerate(videos, 1):
        labels.append(("<Video %d>" % number, ref.ctx_id))
        item = context.item(ref.ctx_id)     # a video of a removed or ID-less card has no card: no soundtrack label (BUG-032)
        if item is not None and item.options.video_audio == "reference":
            audio_number += 1
            labels.append(("<Audio %d>" % audio_number, ref.ctx_id))
    for number, ref in enumerate((ref for ref in refs if ref.kind == "audio"), audio_number + 1):
        labels.append(("<Audio %d>" % number, ref.ctx_id))
    return tuple(labels)


def resolve_media_mentions(prompt, context, refs):
    # A video's @name denotes its picture stream, rather than its paired soundtrack.
    labels = {identity: label for label, identity in reversed(media_labels(context, refs))}
    names = {item.name:labels[item.id] for item in context.items if item.id in labels}
    return replace_mentions(prompt, names, (item.name for item in context.items))


def resolve_lock_mentions(prompt, context, refs):
    locked = {ref.ctx_id for ref in refs if ref.kind == "lock"}
    issues = []
    for item in context.by_media("audio"):
        if "lock" not in item.effective_usage or not item.source:
            continue
        active = item.id in locked
        label = item.description.strip().rstrip(".") or ("the locked audio" if active else item.name)
        resolved = replace_mentions(prompt, {item.name: label}, (candidate.name for candidate in context.items))
        if resolved != prompt:
            code = "audio_lock_mention_prose" if active else "audio_lock_mention_unavailable"
            reason = "has locked audio but no numbered reference token" if active else "is not locked in this chunk"
            issues.append(Issue(code, "'%s' %s; its named mention uses prose. Use an audio reference role "
                                "if it must have a numbered audio reference." % (item.name, reason), item.name))
        prompt = resolved
    return prompt, tuple(issues)


def prompt_labels(result, mapping, context, refs):
    pictures = [ref for ref in refs if ref.kind == "picture"]
    if result.get("mode") == "fl2va":
        # First then last frame are tokenized first even though neither is a Ref2VA reference; references follow them.
        pictures = [ref for kind in ("first_frame", "last_frame", "picture") for ref in refs if ref.kind == kind]
    labels = [("<Picture %d>" % number, ref.ctx_id) for number, ref in
              enumerate(pictures, 1)]
    labels += [("<Subject %d>" % subject, mapping.slot_items[slot - 1]) for slot, subject in result["subject_of_slot"].items()]
    for slot in result["ref_image_slots"]:
        if slot.get("source") == "timeline" and slot.get("subject"):
            source = slot["event"]["seg"].get("imageFile", "")
            labels.append(("<Subject %d>" % slot["subject"], mapping.media_id(slot["event"]["seg"], source)))
    return tuple(labels) + media_labels(context, refs)


def _shown_in(text, name, label):
    """The first mention of a frame picture says where it is shown, later ones use the name: the guide writes "the young
    woman shown in <Picture 1> remains ...", while "<Picture 1> stands in the hall" made the picture the actor."""
    pieces = text.split("\x00")
    if len(pieces) == 1:
        return text
    rest = pieces[1]
    first = "%s, shown in %s%s" % (name, label, "" if not rest or rest[0] in ".,;:!?\n" else ",")
    return pieces[0] + first + rest + "".join(name + piece for piece in pieces[2:])


def resolve_guide_mentions(prompt, context, refs, labels):
    pictures = {identity: label for label, identity in reversed(labels) if label.startswith("<Picture ")}
    unnumbered = {ref.ctx_id: ref for ref in refs if ref.kind in ("keyframe", "continue_video")}
    issues = []
    for item in context.items:
        guide = (item.media == "image" and set(item.effective_usage) & {"first_frame", "last_frame", "keyframe", "storyboard"}) or (
            item.media == "video" and "continue" in item.effective_usage)
        if not guide or not item.source:
            continue
        ref = unnumbered.get(item.id)
        fallback = "the continuation frame" if ref and ref.kind == "continue_video" else "the guide image"
        label = pictures.get(item.id) or item.description.strip().rstrip(".") or (fallback if ref else item.name)
        names = [candidate.name for candidate in context.items]
        if item.id in pictures:
            resolved = _shown_in(replace_mentions(prompt, {item.name: "\x00"}, names), item.name, label)
        else:
            resolved = replace_mentions(prompt, {item.name: label}, names)
        if resolved != prompt and item.id not in pictures:
            code = "guide_mention_prose" if ref else "guide_mention_unavailable"
            reason = "has frame conditioning but no numbered reference token" if ref else "is not presented in this chunk"
            issues.append(Issue(code, "'%s' %s; its named mention uses prose. Keep it as Reference or Motion "
                                "if it must remain a numbered visual reference." % (item.name, reason), item.name))
        prompt = resolved
    return prompt, tuple(issues)


def read_prompt_labels(data, path):
    labels = fields.need_dict(data.get("prompt_labels", {}), path + ".prompt_labels")
    return tuple((label, fields.read_str(labels, label, path + ".prompt_labels")) for label in labels)
