"""Timed lyrics of a song card and where the song sings them on the story.

The words live on the Audio card as LRC text ("[00:12.40] I still wait where your shadow stayed."), in seconds of the file;
an empty stamped line ends the line before it (a pause). Where the card plays exactly (lock or copy, on an audio lane, a
Shot or the whole project), each line is sung at a known story time, so every render part gets exactly the lines sung in
it instead of the whole song. The 27 s elf song put all eight lines into each of its three 9 s parts.
"""
import difflib
import re
from dataclasses import dataclass

from .audio_timing import clip_windows, shot_windows, source_window
from .frames import seconds_to_frames

STAMP_RE = re.compile(r"^\s*\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")
LANGUAGE_RE = re.compile(r"^\s*\[la:\s*([^\]]*)\]\s*$", re.IGNORECASE)
LAST_LINE_SECONDS = 4.0     # a final line without a closing stamp is taken to last this long
SINGER = "the singer"


@dataclass(frozen=True)
class LyricLine:
    start: float    # seconds in the file
    end: float
    text: str


def parse(text):
    """(language, lines) from LRC text. Lines without a stamp are not timed and are left out."""
    language, stamped = "", []
    for raw in (text or "").splitlines():
        found = LANGUAGE_RE.match(raw)
        if found:
            language = found.group(1).strip()
            continue
        times = []
        while True:
            stamp = STAMP_RE.match(raw)
            if not stamp:
                break
            times.append(int(stamp.group(1)) * 60 + float(stamp.group(2).replace(":", ".")))
            raw = raw[stamp.end():]
        stamped.extend((time, raw.strip()) for time in times)
    stamped.sort(key=lambda entry: entry[0])
    lines = []
    for index, (start, words) in enumerate(stamped):
        if not words:
            continue
        end = stamped[index + 1][0] if index + 1 < len(stamped) else start + LAST_LINE_SECONDS
        lines.append(LyricLine(start, max(end, start), words))
    return language, tuple(lines)


def stamp(seconds):
    minutes, rest = divmod(max(0.0, seconds), 60)
    return "[%02d:%05.2f]" % (minutes, rest)


def to_lrc(language, lines):
    """LRC text for lines; a pause longer than a second before the next line gets its own empty stamp."""
    out = ["[la:%s]" % language] if language else []
    for index, line in enumerate(lines):
        out.append("%s %s" % (stamp(line.start), line.text))
        following = lines[index + 1].start if index + 1 < len(lines) else None
        if following is None or following - line.end > 1.0:
            out.append(stamp(line.end))
    return "\n".join(out)


def plain_lines(text):
    """The words of each lyric line, stamps and language tag removed; empty lines dropped."""
    out = []
    for raw in (text or "").splitlines():
        if LANGUAGE_RE.match(raw):
            continue
        while STAMP_RE.match(raw):
            raw = raw[STAMP_RE.match(raw).end():]
        if raw.strip():
            out.append(raw.strip())
    return out


def _tokens(text):
    return re.findall(r"\w+", text.lower())


def align(known, words, duration=0.0):
    """Give the user's own lines the times of the recognised words: [(word, start, end)] from speech recognition.

    The words stay the user's (recognition mishears sung words); only the timing comes from the recogniser. A line none of
    whose words were heard is placed between its neighbours by its share of the words; lines after the last heard one
    share the rest of the file (`duration` seconds). Without it, 41 lines of a song collapsed onto one instant."""
    tokens = [(index, token) for index, line in enumerate(known) for token in _tokens(line)]
    heard = [(token, start, end) for word, start, end in words for token in _tokens(word)]
    matcher = difflib.SequenceMatcher(None, [t for _, t in tokens], [t for t, _, _ in heard], autojunk=False)
    spans = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            line = tokens[block.a + offset][0]
            _, start, end = heard[block.b + offset]
            first, last = spans.get(line, (start, end))
            spans[line] = (min(first, start), max(last, end))
    counts = [max(1, len(_tokens(line))) for line in known]
    times = [spans.get(index) for index in range(len(known))]
    total_end = max([end for _, _, end in heard] + [duration], default=0.0) or LAST_LINE_SECONDS * len(known)
    for index, found in enumerate(times):
        if found:
            continue
        before = next((times[i][1] for i in range(index - 1, -1, -1) if times[i]), 0.0)
        after_index = next((i for i in range(index + 1, len(known)) if times[i]), None)
        after = times[after_index][0] if after_index is not None else total_end
        gap = range(index, after_index if after_index is not None else len(known))
        share = max(0.0, after - before) / float(sum(counts[i] for i in gap))
        start = before
        for i in gap:
            times[i] = (start, start + share * counts[i])
            start = times[i][1]
    lines, previous = [], 0.0
    for line, (start, end) in zip(known, times):
        start = max(start, previous)
        lines.append(LyricLine(round(start, 2), round(max(end, start), 2), line))
        previous = start
    return tuple(lines)


def _spans(context, item):
    """(story start f, story end f, file frame at story start) where this card plays its own signal."""
    lanes = clip_windows(context, ("lock", "copy"))
    if item.id in lanes:
        return lanes[item.id]
    if not set(item.effective_usage) & {"lock", "copy"}:
        return []
    source = seconds_to_frames(item.options.start_s)
    bound = (shot_windows(context) or {}).get(item.id)
    if bound is not None:
        return _played([(start, end, source + offset) for start, end, offset in bound], item)
    return _played([(0, seconds_to_frames(context.project_seconds), source)], item)


def _played(spans, item):
    """Only as long as the card's End or its file lasts: past it the song is silent, and its lines were sung into
    parts without any song (BUG-085)."""
    start, available = source_window(item)
    if available is None:
        return spans
    out = []
    for story_start, story_end, offset in spans:
        story_end = min(story_end, story_start + max(0, start + available - offset))
        if story_end > story_start:
            out.append((story_start, story_end, offset))
    return out


@dataclass(frozen=True)
class StoryLine:
    start_f: int        # story frames where the song sings it
    end_f: int
    middle_f: int
    speaker: str        # the card's speaker (a figure's context id) or ""
    language: str
    text: str
    song: str           # the card's name


def story_lines(context):
    """Every timed line of every exactly played song, at its story time, in time order."""
    out = []
    for item in context.by_media("audio"):
        language, lines = parse(item.options.lyrics)
        if not lines:
            continue
        for origin, end, offset in _spans(context, item):
            for line in lines:
                start = origin + seconds_to_frames(line.start) - offset
                # a line runs at most to where the played window ends (the card's End, the file's end): the last line
                # of a trimmed song otherwise had its middle past the window and was dropped (BUG-085)
                stop = min(origin + seconds_to_frames(line.end) - offset, end)
                middle = (start + stop) // 2
                if origin <= middle < end:
                    out.append(StoryLine(max(origin, start), stop, middle, item.speaker, language or "English", line.text, item.name))
    return sorted(out, key=lambda line: line.start_f)


def sung_lines(context, chunk):
    """[(local frame where the line is sung, speaker item id, language, text)] for this chunk, in time order.

    A line belongs to the part where its middle is sung; a part's carried-over head was rendered by the part before."""
    window = chunk.story_start_f - chunk.head_frames
    return [(line.middle_f - window, line.speaker, line.language, line.text) for line in story_lines(context)
            if chunk.story_start_f <= line.middle_f < chunk.story_end_f]
