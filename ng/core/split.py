"""AI: split into shots. The Prompt becomes timed Shots with real spoken lines, plus one Look that every render part shares.

The earlier split answered in timed text with the dialogue as a prose line ("@Mage says: My master ..."), so a song of eight
lines became one sung line and seven lines of prose, all in one Shot over three render parts (elf song, 2026-10-05).
"""
import json
import re

from . import fields
from .context_build import card_id, widget_text
from .context_options import roles
from .shot_draft import plain_mentions
from .shot_share import BEAT_MIN_S, tidy_beats

DELIVERIES = ("says", "sings", "whispers", "shouts", "murmurs")
FORMAT = "h3-director-shots"
DELIMITERS = re.compile(r"[\r\n\[\]():]")

# MiniMax's H3 prompt guide (base-en 4.3): motion type + amplitude + speed, "holds a static shot" for a still camera. Said
# explicitly, it also keeps 4-step turbo from drifting into a close-up (measured 2026-10-13: a shot that only said "stable
# framing" pushed in and brightened).
CAMERA_RULE = ("camera: one English sentence of how the camera moves inside the shot: the motion (push in, pull out, pan, truck, "
               "tilt, pedestal up or down, arc, tracking, zoom, shake), with small or large amplitude and slow or fast speed when "
               "they matter, e.g. 'The camera pushes in with small amplitude at slow speed.' When it does not move, write 'The "
               "camera holds a static shot.' Never 'cuts': a cut is a new shot.")
# Every shot has beats, and the answer's example shows a 10 s shot with two and a 3 s shot with one. With one long example shot
# qwen3.5:9b gave beats to the first long shot only (2026-10-13, 4 of 5 answers); with "beats":[] in it, to none.
BEAT = '{"from_s":%s,"to_s":%s,"action":"...","camera":"..."}'
BEAT_RULE = ("beats: every shot has beats, in seconds from the shot's own start (0 is where the shot begins), that together cover "
             "its whole length. The number of beats is the shot's length divided by %d, rounded up: a 3 s or 5 s shot has 1 beat, "
             "a 6 s to 10 s shot 2, an 11 s to 15 s shot 3, a 16 s to 20 s shot 4. Each beat begins with its framing, then what "
             "happens in it; its camera says how the camera moves or that it holds a static shot. Each beat is a new moment: never "
             "repeat an earlier beat's words, and say the camera only in camera, never in action." % BEAT_MIN_S)


def shots_example(extra="", line=""):
    """The "shots" list of the answer's example: a 10 s shot with two beats and a 3 s shot with one. extra: more fields of
    each shot (',"uses":[]'); line: the first shot's example spoken line, or "" for none."""
    shot = '{"start_s":%s,"end_s":%s,"action":"...","camera":"...","beats":[%s]%s,"lines":[%s]}'
    return "[%s,%s]" % (shot % (0, 10, ",".join((BEAT % (0, 5), BEAT % (5, 10))), extra, line),
                        shot % (10, 13, BEAT % (0, 3), extra, ""))


def _seconds(value):
    return ("%.1f" % value).rstrip("0").rstrip(".")


def _mentions(meanings):
    """The @names the answer may use, spelled out; with a placeholder ("@Name") Qwen3-VL 4B wrote "@Name" into the shots."""
    names = [entry["name"] for entry in meanings if entry.get("name")]
    if not names:
        return "There is no Content to mention: write no @ mentions."
    return "Mention Content only by these exact names: %s." % ", ".join("@" + name for name in names)


def split_prompt(idea, seconds, meanings, parts=(), sung=()):
    """parts: [(start s, end s)] of the render parts; sung: [(start s, end s, song name, words)] placed by the compiler."""
    rules = [
        "Split the Idea into shots for a %s second video. Return only JSON: "
        '{"look":"...","shots":%s,"soundscape":"...","music":"..."}.' % (
            _seconds(seconds), shots_example(line='{"speaker":"","delivery":"says","language":"English","text":"..."}')),
        "look: one or two English sentences with what every shot shares: visual style, place, light. No action, no spoken words.",
        "action: English, what is visible in this shot: begin with the framing (e.g. 'A full-body shot of ...'), then who is "
        "where in the frame, what they do, with which expression, and the light. " + _mentions(meanings),
        CAMERA_RULE,
        BEAT_RULE,
        # base-en 4.2: "A cut should introduce new information ... If only the distance or a slight angle needs to change,
        # prefer camera motion." Split by line, the elf song became nine static shots of the same face.
        "Start a new shot only when the view changes: another framing, angle, place or time. A slow change of distance or "
        "angle stays inside one shot as camera movement.",
        "lines: each line the Idea gives to be spoken or sung, word for word in its own language, one entry per line, in the shot "
        "where it is heard. speaker is the exact Content name of who says it, or empty for a narrator; delivery is one of %s. "
        "Invent no words; use [] when nobody speaks." % ", ".join(DELIVERIES),
        "Shots are ordered, do not overlap and together cover 0 to %s s." % _seconds(seconds),
        "subject_ids bind assets to Subjects identified by context_id; keep those meanings instead of inventing independent "
        "figures for linked assets.",
        "soundscape: one or two English sentences of ambient and physical sound, no speech. music: the score only the audience hears "
        "(instruments, tempo), or N/A.",
        "Do not claim generation or media analysis has occurred.",
    ]
    if len(parts) > 1:
        rules.append("The video is rendered in separate parts with hard cuts between them: %s. A shot may run across a part boundary; a cut fits best at one."
                     % ", ".join("%s-%s s" % (_seconds(a), _seconds(b)) for a, b in parts))
    if sung:
        rules.append("These sung lines are already placed at their times, so do NOT put them into lines; let the action follow them: %s."
                     % "; ".join('%s-%s s "%s"' % (_seconds(a), _seconds(b), words) for a, b, _, words in sung))
    return " ".join(rules) + "\nIdea: %s\nContexts: %s" % (idea, json.dumps(meanings, ensure_ascii=False))


def _sentence(text):
    return text if text.endswith((".", "!", "?")) else text + "."


def beat_text(raw, seconds):
    """The shot text of the AI's beats ("0–5s: ... 5–10s: ..."), fitted to the shot's real length; None when the shot is
    short or the beats are not usable (then action and camera are the text). Beat ends are kept in proportion: the AI may
    have planned the shot a little longer or shorter than it ends up."""
    beats = []
    for beat in raw if isinstance(raw, list) and seconds > BEAT_MIN_S else ():
        try:
            start, end = float(beat["from_s"]), float(beat["to_s"])
            action = str(beat.get("action") or "").strip()
        except (KeyError, TypeError, ValueError):
            return None
        if end <= start or not action:
            return None
        beats.append((start, end, " ".join(_sentence(v) for v in (action, str(beat.get("camera") or "").strip()) if v)))
    if len(beats) < 2:
        return None
    beats.sort()
    scale, start, out = seconds / beats[-1][1], 0.0, []
    for number, (_, end, text) in enumerate(beats):
        stop = seconds if number == len(beats) - 1 else round(end * scale, 1)
        if stop <= start:
            return None
        out.append("%s–%ss: %s" % (_seconds(start), _seconds(stop), text))
        start = stop
    return tidy_beats(" ".join(out))


def _norm(text):
    return " ".join(re.findall(r"\w+", text.lower()))


def _speaks(entry):
    """Only a figure picture (Reference, not "Belongs to" another) holds a voice slot; an audio, text or video card, or a
    First / Last frame or Keyframe picture of the same name, speaks as a described voice (BUG-087/088)."""
    widgets = entry.get("widgets", {})
    if entry.get("media") != "image":
        return False
    try:
        usage = roles(widgets.get("usage_roles") or "", widgets.get("usage") or "reference")
        owners = roles(widgets.get("subject_ids") or "", "")
    except ValueError:
        return False
    return not set(usage) & {"first_frame", "last_frame", "keyframe", "storyboard"} and not owners


def _owner(speaker, contexts):
    """(speaker_id, voice) for a line: a named figure speaks with its own voice, anyone else is a described voice."""
    name = speaker.strip().lstrip("@").casefold()
    for entry in contexts or ():
        widgets = entry.get("widgets", {})
        if name and widget_text(widgets, "name").casefold() == name and _speaks(entry):
            return card_id(entry), "a narrator"
    voice = " ".join(DELIMITERS.sub(" ", speaker.lstrip().lstrip("@")).split())
    return "", voice or "a narrator"


def _lines(raw, path, contexts, sung):
    out = []
    for number, line in enumerate(fields.read_list(raw, "lines", path) if isinstance(raw, dict) else ()):
        here = "%s.lines[%d]" % (path, number)
        fields.need_dict(line, here)
        speaker_id, voice = _owner(fields.read_str(line, "speaker", here, ""), contexts)
        delivery = fields.read_str(line, "delivery", here, "says").strip().lower()
        language = " ".join(DELIMITERS.sub(" ", fields.read_str(line, "language", here, "English")).split()) or "English"
        # qwen3.5:9b copied the example's line where nobody speaks, with "text":[] or "text":"[]" (2026-10-13): a line
        # without a word is no line; a list of strings is one line each.
        text = line.get("text")
        text = "\n".join(str(item) for item in text) if isinstance(text, list) else fields.read_str(line, "text", here, "")
        for words in text.splitlines():
            if re.search(r"\w", words) and _norm(words) not in sung:
                out.append({"schema_version": 1, "text": words.strip(), "speaker_id": speaker_id, "voice": voice,
                            "language": language, "delivery": delivery if delivery in DELIVERIES else "says"})
    return out


def _keep(shots, keep, contexts):
    """The user's own lines ("@Mage says: ...", "Narrator says: ...") replace the AI's lines of that speaker, in the shot
    where the AI first gave that speaker a line, else in the last shot. Returns the user's lines the AI did not have."""
    own, spelled = {}, {}
    for line in (keep or "").splitlines():
        # "@Mage [German] whispers: ..." - every delivery and an optional language, as the Studio writes lines (BUG-084)
        found = re.match(r"^\s*(@?)([^:\[\]]+?)\s*(?:\[([^\]]+)\])?\s+(%s):\s*(.+)$" % "|".join(DELIVERIES), line, re.IGNORECASE)
        if found:
            name = found.group(2).strip()
            narrator = name.casefold() == "narrator" and not (found.group(1) and _owner(name, contexts)[0])
            spelled.setdefault(name.casefold(), name)
            own.setdefault("" if narrator else name.casefold(), []).append(
                (found.group(5).strip(), (found.group(3) or "English").strip(), found.group(4).lower()))
    if not own:
        return []
    names = {card_id(entry): widget_text(entry["widgets"], "name").casefold() for entry in contexts or ()}
    # A figure without a card speaks with its own described voice: its key is that voice, not the narrator's (BUG-089).
    key = lambda line: names.get(line["speaker_id"], "") if line["speaker_id"] else (
        "" if line.get("voice", "a narrator").casefold() in ("a narrator", "narrator") else line["voice"].casefold())
    proposed = {_norm(line["text"]) for shot in shots for line in shot["spoken"]}
    for speaker, texts in own.items():
        target = next((shot for shot in shots if any(key(line) == speaker for line in shot["spoken"])), shots[-1])
        for shot in shots:
            shot["spoken"] = [line for line in shot["spoken"] if key(line) != speaker]
        speaker_id, voice = _owner(spelled[speaker], contexts) if speaker else ("", "a narrator")
        target["spoken"] += [{"schema_version": 1, "text": text, "speaker_id": speaker_id, "voice": voice, "language": language,
                              "delivery": delivery} for text, language, delivery in texts]
    return [text for texts in own.values() for text, _, _ in texts if _norm(text) not in proposed]


def parse_split(data, seconds, contexts=None, keep="", sung=()):
    """A checked Shot document from the AI's answer; nothing in it changes the project until the user accepts it."""
    raw = fields.read_list(data, "shots", "direction")
    if not 1 <= len(raw) <= 64:
        raise ValueError("Auto Direct needs between 1 and 64 shots.")
    sung_words = {_norm(words) for _, _, _, words in sung}
    shots, end, dropped, adjusted = [], 0.0, [], False
    for number, shot in enumerate(raw):
        path = "direction.shots[%d]" % number
        fields.need_dict(shot, path)
        start = float(fields.read_number(shot, "start_s", path, minimum=0))
        stop = float(fields.read_number(shot, "end_s", path, minimum=0))
        if end >= seconds - 0.001:
            adjusted = True  # the shots before already fill the project
            break
        if stop <= start or stop <= end + 0.001:
            raise ValueError("Auto Direct returned a shot that ends before it starts or before the previous one; try again or edit manually.")
        # Small models round, leave gaps or stop early; the shots are laid end to end over the project instead.
        placed = seconds if number == len(raw) - 1 else min(stop, seconds)
        adjusted = adjusted or abs(start - end) > 0.001 or abs(placed - stop) > 0.001
        action = fields.read_str(shot, "action", path).strip()
        if not action:
            raise ValueError("Each suggested shot needs an action.")
        camera = fields.read_str(shot, "camera", path, "").strip()
        beats = beat_text(shot.get("beats"), placed - end)
        text, unknown = plain_mentions(beats or " ".join(_sentence(v) for v in (action, camera) if v), contexts)
        dropped += [name for name in unknown if name not in dropped]
        shots.append({"id": "ai-%d" % (number + 1), "start": round(end, 3), "end": round(placed, 3), "text": text, "media": [],
                      "spoken": _lines(shot, path, contexts, sung_words), "locked_fields": [], "draft": None})
        end = placed
    kept = _keep(shots, keep, contexts)
    look = fields.read_str(data, "look", "direction", "").strip()
    result = {"shots": json.dumps({"format": FORMAT, "schema_version": 1, "shots": shots, "look": look}, ensure_ascii=False),
              "look": look, "soundscape": fields.read_str(data, "soundscape", "direction", ""),
              "music": fields.read_str(data, "music", "direction", "")}
    if kept:
        result["kept_dialogue"] = kept
    if dropped:
        result["unknown_mentions"] = dropped
    if adjusted:
        result["timing_adjusted"] = True
    return result
