"""Story shots: the creative units of a project, in story time (frames at 24 fps), independent of how it is rendered in chunks.

Text format, one shot per header line, any number of text lines below it:

    0-8: A woman enters the station.
    8-22.5 She discovers the robot.
    @ref1 says: Hello?
    0:22.5-0:38: She examines the damage.

Times are seconds, `m:ss` or `m:ss.s`. Every correction made to the user's shots is returned as an Issue.
"""
import re
from dataclasses import dataclass

from .frames import seconds_to_frames
from .issues import Issue
from .shot_document import read_document, metadata

_TIME = r"(?:\d+:)?\d+(?:\.\d+)?s?"
_HEADER = re.compile(r"^\s*(?P<a>%s)\s*(?:-|–|—|to)\s*(?P<b>%s)\s*(?::|\s)\s*(?P<rest>.*)$" % (_TIME, _TIME))


@dataclass(frozen=True)
class Shot:
    index: int
    start_f: int
    end_f: int
    text: str
    id: str = ""
    media: tuple = ()
    spoken: tuple = ()
    locked_fields: tuple = ()
    effect: str = ""            # an effect embedding added to the shot's text where it starts (shot_document.effect_name)

    @property
    def frames(self):
        return self.end_f - self.start_f


def parse_time(token):
    token = token.strip().rstrip("s")
    if ":" in token:
        minutes, seconds = token.split(":", 1)
        return int(minutes) * 60 + float(seconds)
    return float(token)


def auto_shots(idea, project_frames):
    """No shots written: the idea carries the whole project as one shot."""
    return (Shot(1, 0, project_frames, idea.strip()),) if idea.strip() else ()


def _read_blocks(text):
    blocks, preamble = [], []
    for line in text.splitlines():
        match = _HEADER.match(line)
        if match:
            blocks.append([parse_time(match["a"]), parse_time(match["b"]), [match["rest"].strip()]])
        elif blocks:
            blocks[-1][2].append(line.rstrip())
        elif line.strip():
            preamble.append(line.strip())
    return blocks, preamble


def parse_shots(text, project_frames):
    """Parse the shot text. Returns (shots, issues). Text before the first timed line is returned as an issue, not discarded."""
    issues = []
    blocks, preamble = _read_blocks(text or "")
    records = read_document(text or "")
    if records is not None:
        blocks = [(r["start"], r["end"], [r.get("text", "")], metadata(r)) for r in records]
        preamble = []
    else:
        blocks = [(*block, {"id": "legacy-shot-%d" % (i + 1)}) for i, block in enumerate(blocks)]
    if preamble:
        issues.append(Issue("shots_preamble", "Text before the first timed shot was ignored: '%s'." % " ".join(preamble)[:80]))
    shots, previous_end = [], 0
    for number, (start_s, end_s, lines, extra) in enumerate(sorted(blocks, key=lambda b: b[0]), 1):
        start_f, end_f = seconds_to_frames(start_s), seconds_to_frames(end_s)
        body = "\n".join(l for l in lines if l.strip()).strip()
        ref = "shot %d" % number
        if end_f <= start_f:
            issues.append(Issue("shot_empty_range", "ends before it starts and was skipped.", ref))
            continue
        if start_f >= project_frames:
            issues.append(Issue("shot_after_end", "starts after the project ends and was skipped.", ref))
            continue
        if start_f < previous_end:
            issues.append(Issue("shot_overlap", "overlapped the previous shot; its start was moved to %.2fs." % (previous_end / 24.0), ref))
            start_f = previous_end
        if end_f > project_frames:
            issues.append(Issue("shot_clipped", "ran past the project end and was cut to %.2fs." % (project_frames / 24.0), ref))
            end_f = project_frames
        if start_f > previous_end and shots:
            issues.append(Issue("shot_gap", "there is a gap of %.2fs before it; nothing is described there." % ((start_f - previous_end) / 24.0), ref))
        if end_f > start_f:
            shots.append(Shot(len(shots) + 1, start_f, end_f, body, **extra))
            previous_end = end_f
    return tuple(shots), tuple(issues)
