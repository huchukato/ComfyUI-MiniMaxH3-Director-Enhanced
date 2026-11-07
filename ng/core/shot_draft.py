"""Validate ID-addressed proposals without editing the active shot document."""
import json
import re

from . import fields
from .context import USAGE_BY_MEDIA
from .context_build import card_id, widget_text
from .frames import seconds_to_frames
from .shot_document import LOCK_FIELDS, MediaBinding, SpokenLine, read_document
from .shots import parse_shots
from .shot_share import beat_marks, tidy_beats

FORMAT = "h3-director-draft"


def current_records(text, seconds):
    records = read_document(text)
    if records is not None:
        return records
    shots, issues = parse_shots(text, seconds_to_frames(seconds))
    if issues:
        raise ValueError("Repair the existing shot timing/text before requesting AI suggestions.")
    return [dict(id=s.id, start=s.start_f / 24, end=s.end_f / 24, text=s.text,
                 media=[], spoken=[], locked_fields=[]) for s in shots]


def draft_prompt(idea, seconds, meanings, records):
    shots = [{key: r.get(key, [] if key in ("media", "spoken", "locked_fields") else "")
              for key in ("id", "start", "end", "text", "media", "spoken", "locked_fields")} for r in records]
    # The beats of a long shot come from its own length, so the AI only fills them (qwen3.5:9b, told the rule alone, wrote
    # "holds a static shot for 2.5 seconds (0–2.5s)" into a 10 s shot, 2026-10-13).
    for shot in shots:
        marks = beat_marks(float(shot["end"] or 0) - float(shot["start"] or 0))
        if marks and "text" not in (shot["locked_fields"] or ()):
            shot["write_as_beats"] = marks
    return ("Improve the existing Shots from the Idea and Context descriptions. Return only JSON: "
            '{"format":"h3-director-draft","schema_version":1,"patches":[{"shot_id":"existing ID",'
            '"fields":{"text":"action and camera prose","media":[],"spoken":[]}}]}. '
            "The example lists allowed fields; omit every field that does not need changes. "
            "You may also propose media or spoken fields and project soundscape/music strings. "
            "Every shot keeps its start and end exactly: never propose timing. "
            "text: begin with the framing (e.g. 'A full-body shot of ...'), then who is where, what they do, their expression and "
            "the light, then how the camera moves with amplitude and speed, or 'The camera holds a static shot.' when it does not. "
            "A shot with write_as_beats gets its text as exactly those time beats, in that order, each beginning with its mark, "
            "e.g. for '0–5s, 5–10s': '0–5s: A full-body shot of ... The camera holds a static shot. 5–10s: A close-up of ... The "
            "camera pushes in with small amplitude at slow speed.'; each beat begins with its framing and says how the camera "
            "moves, in one camera sentence. Each beat is a new moment: never repeat an earlier beat's sentences. "
            "Include soundscape/music only for a concrete requested change; never copy schema placeholders. "
            "Use existing Shot IDs; never add, delete or reorder Shots. Respect locked_fields. "
            "Patch fields may contain only text, media and spoken; never copy id, draft or locked_fields into fields. "
            "Preserve every existing spoken entry and exact inline dialogue; new dialogue is optional. "
            "Media bindings use schema_version 1, context_id and a supported role, not filenames. "
            "Spoken entries use schema_version 1, speaker_id, voice, language, delivery and text. "
            "%sUse Context IDs for bindings. Do not claim generation or media analysis has occurred. "
            "Idea: %s\nContexts: %s\nExisting Shots: %s" %
            (mention_rule(meanings), idea, json.dumps(meanings, ensure_ascii=False), json.dumps(shots, ensure_ascii=False)))


def mention_rule(meanings):
    """The @names the answer may use, spelled out. With a placeholder ("@Name") in the instructions, Qwen3-VL 4B wrote
    "@Name" into the user's shots, and the whole proposal was refused for it."""
    names = [entry["name"] for entry in meanings if entry.get("name")]
    words = "Leave dialogue empty unless the Idea gives words to speak or sing"
    if not names:
        return "There is no Content to mention: write no @ mentions. %s. " % words
    # No sample line: a sample such as "says: exact words" was copied into the answer word for word.
    return ("Mention Content only by these exact names: %s. %s; then start the line with the speaker's @name and 'says:'. "
            % (", ".join("@" + name for name in names), words))


def plain_mentions(text, contexts):
    """An @mention of no supplied Content becomes a plain word instead of discarding the whole proposal; the user
    reviews a proposal before it changes anything. Returns the text and the names that were not Content."""
    if contexts is None:
        return text, []
    names = {widget_text(entry["widgets"], "name").casefold() for entry in contexts}
    known = sorted((re.escape(name) for name in names if name), key=len, reverse=True)
    pattern = r"@(" + "|".join(known + [r"voice\([^)]*\)", r"ref\d+", r"audio\d+", r"[\w-]+"]) + r")(?![\w])"
    unknown = []

    def keep(match):
        name = match.group(1)
        if name.casefold() in names or re.fullmatch(r"voice\([^)]*\)|ref\d+|audio\d+", name, re.I):
            return match.group(0)
        unknown.append(name)
        return name
    return re.sub(pattern, keep, text, flags=re.IGNORECASE), unknown


def keep_inline_words(proposed, original):
    lines = [line for line in original.splitlines() if line.strip().startswith("@") and ":" in line]
    if not lines:
        return proposed
    prose = [line for line in proposed.splitlines() if not (line.strip().startswith("@") and ":" in line)]
    return "\n".join([*prose, *lines])


def _field_value(key, value, record, seconds, contexts):
    by_id = {card_id(entry): entry for entry in contexts or ()}
    if key == "text":
        text = fields.read_str({key: value}, key, "draft.fields").strip()
        if not text:
            raise ValueError("A proposed action must not be empty.")
        return keep_inline_words(tidy_beats(plain_mentions(text, contexts)[0]), record["text"])
    entries = fields.read_list({key: value}, key, "draft.fields")
    parsed = [(MediaBinding if key == "media" else SpokenLine).from_dict(entry).to_dict() for entry in entries]
    existing = [(MediaBinding if key == "media" else SpokenLine).from_dict(entry).to_dict() for entry in record.get(key, [])]
    for entry in parsed:
        identity = entry["context_id"] if key == "media" else entry["speaker_id"]
        if key == "spoken" and identity in by_id and by_id[identity]["media"] != "image":
            # A line bound to an audio, text or video card is spoken by a voice of that name; refusing it left the whole
            # draft without usable changes (BUG-087).
            entry.update(speaker_id="", voice=widget_text(by_id[identity]["widgets"], "name") or entry["voice"])
            identity = ""
        # A spoken line already in the shot stays even if its speaker card is gone (lines are kept word for word); a media
        # binding to a card that is no longer connected is refused, also when the AI only echoes it (BUG-058).
        if identity and identity not in by_id and (key == "media" or entry not in existing):
            raise ValueError("The draft binds an unknown Context ID: %s." % identity)
        if key == "media" and identity in by_id:
            if entry["role"] != "context" and entry["role"] not in USAGE_BY_MEDIA[by_id[identity]["media"]]:
                raise ValueError("The draft uses an unsupported media role.")
    if key == "spoken" and parsed[:len(existing)] != existing:
        raise ValueError("Keep the existing spoken words and order; new lines may be appended.")
    return parsed


def _merged(patches):
    """Patches of one shot that change different fields become one: qwen3.5:9b sent a shot's text and its spoken line as
    two patches (2026-10-13), and the whole draft was refused for the repeated ID. The same field twice stays refused."""
    out, by_id = [], {}
    for patch in patches:
        earlier = by_id.get(patch.get("shot_id")) if isinstance(patch, dict) else None
        if earlier is not None and isinstance(patch.get("fields"), dict) and isinstance(earlier.get("fields"), dict) \
                and not set(patch["fields"]) & set(earlier["fields"]):
            earlier["fields"] = {**earlier["fields"], **patch["fields"]}
            continue
        if isinstance(patch, dict) and patch.get("shot_id") not in by_id:
            patch = by_id[patch.get("shot_id")] = dict(patch)
        out.append(patch)
    return out


def parse_draft(data, records, seconds, contexts):
    if data.get("format") != FORMAT:
        raise ValueError("Existing Shots need an ID-addressed draft, not a scene replacement.")
    fields.check_version(data, "draft", 1)
    if set(data) - {"format", "schema_version", "patches", "soundscape", "music"}:
        raise ValueError("Unexpected scene replacement fields in the Shot draft.")
    patches = _merged(fields.read_list(data, "patches", "draft"))
    if len(patches) > 64:
        raise ValueError("A draft can propose at most 64 Shot patches.")
    by_id, seen, validated, dropped = {record["id"]: record for record in records}, set(), [], []
    for patch in patches:
        fields.need_dict(patch, "draft.patch")
        identity = fields.read_str(patch, "shot_id", "draft.patch")
        if identity not in by_id or identity in seen:
            raise ValueError("Draft Shot IDs must exist and occur only once.")
        seen.add(identity)
        changes = fields.need_dict(patch.get("fields"), "draft.fields")
        if not changes or set(changes) - set(LOCK_FIELDS):
            raise ValueError("Draft fields must be timing, text, media or spoken.")
        # A field that fails its check is left out with its reason; the others stay. Gemma's "improve text" carried a
        # spoken line without schema_version, and the good text of the same patch was thrown away with it.
        kept, locked = {}, set(by_id[identity].get("locked_fields") or ())
        for key, value in changes.items():
            if key in locked:       # the user locked it in the Studio: the AI must not change it (BUG-086)
                dropped.append("%s of %s: locked in the Studio" % (key, identity))
                continue
            if key == "timing":     # the shot times are the user's; the AI writes the text to fit them
                dropped.append("timing of %s: shot times stay as set" % identity)
                continue
            try:
                kept[key] = _field_value(key, value, by_id[identity], seconds, contexts)
            except ValueError as error:
                dropped.append("%s of %s: %s" % (key, identity, error))
        if kept:
            validated.append(dict(shot_id=identity, fields=kept))
    result = dict(format=FORMAT, schema_version=1, patches=validated)
    for key in ("soundscape", "music"):
        if key in data:
            result[key] = fields.read_str(data, key, "draft")
    if dropped:
        result["dropped"] = dropped
    if not validated and not any(result.get(key, "").strip() for key in ("soundscape", "music")):
        raise ValueError("The draft has no usable changes" + (": " + "; ".join(dropped) if dropped else "."))
    return result
