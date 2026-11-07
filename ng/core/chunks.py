"""Chunk planning: split a story of any length into H3 runs that are each on the model's frame grid.

Story time and render time are different things. A shot can run across several chunks and a chunk can hold several shots.
A continued chunk is sampled with the previous clip's tail pinned in front of it (the "head"), then the head is cut off again:

    sampled = head + delivered, sampled on the 17k+5 grid   ->   delivered = 17m for the pin windows 5/22/39/56

Everything here is plain arithmetic over frames, so it can be tested without a GPU.
"""
from dataclasses import dataclass, replace

from . import fields, frames, limits
from .boundaries import align_to_shots
from .issues import Issue, SchemaError
from .shot_document import MediaBinding, SpokenLine

CONTINUITY_MODES = ("none", "video", "video_audio")


@dataclass(frozen=True)
class ContinuityPlan:
    mode: str = "video_audio"
    video_frames: int = limits.PIN_VIDEO_DEFAULT
    audio_frames: int = limits.PIN_AUDIO_DEFAULT
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if self.mode not in CONTINUITY_MODES:
            raise ValueError("continuity must be one of %s, got %r" % (", ".join(CONTINUITY_MODES), self.mode))
        if self.video_frames not in limits.PIN_VIDEO_WINDOWS:
            raise ValueError("pin frames must be one of %s, got %r" % (limits.PIN_VIDEO_WINDOWS, self.video_frames))

    @property
    def head(self):
        """Frames in front of every continued chunk that are sampled but not delivered."""
        return 0 if self.mode == "none" else self.video_frames

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "mode": self.mode, "video_frames": self.video_frames,
                "audio_frames": self.audio_frames}

    @classmethod
    def from_dict(cls, data, path="continuity"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        window = int(fields.read_number(data, "video_frames", path, limits.PIN_VIDEO_DEFAULT))
        if window not in limits.PIN_VIDEO_WINDOWS:
            raise SchemaError("%s.video_frames" % path, "must be one of %s" % (limits.PIN_VIDEO_WINDOWS,))
        return cls(mode=fields.read_choice(data, "mode", path, CONTINUITY_MODES, "video_audio"), video_frames=window,
                   audio_frames=int(fields.read_number(data, "audio_frames", path, limits.PIN_AUDIO_DEFAULT, minimum=3)))


@dataclass(frozen=True)
class ChunkShot:
    shot_index: int
    local_start_f: int      # inside the sampled clip, head included
    local_end_f: int
    text: str
    carried: bool           # began before this chunk's delivered part
    continues: bool         # goes on into the next chunk
    shot_id: str = ""
    media: tuple = ()
    spoken: tuple = ()
    locked_fields: tuple = ()
    shot_start_f: int = -1  # the whole shot on the story timeline; -1 = unknown (data from before 2026-10-13)
    shot_end_f: int = -1
    effect: str = ""
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "shot_index": self.shot_index, "local_start_f": self.local_start_f,
                "local_end_f": self.local_end_f, "text": self.text, "carried": self.carried, "continues": self.continues,
                "shot_id": self.shot_id, "media": [b.to_dict() for b in self.media],
                "spoken": [s.to_dict() for s in self.spoken], "locked_fields": list(self.locked_fields),
                "shot_start_f": self.shot_start_f, "shot_end_f": self.shot_end_f, "effect": self.effect}

    @classmethod
    def from_dict(cls, data, path="chunk_shot"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        return cls(shot_index=int(fields.read_number(data, "shot_index", path)), local_start_f=int(fields.read_number(data, "local_start_f", path)),
                   local_end_f=int(fields.read_number(data, "local_end_f", path)), text=fields.read_str(data, "text", path, ""),
                   carried=bool(data.get("carried", False)), continues=bool(data.get("continues", False)),
                   shot_id=fields.read_str(data, "shot_id", path, ""),
                   media=tuple(MediaBinding.from_dict(b) for b in fields.read_list(data, "media", path)),
                   spoken=tuple(SpokenLine.from_dict(s) for s in fields.read_list(data, "spoken", path)),
                   locked_fields=fields.read_texts(data, "locked_fields", path),
                   shot_start_f=int(data.get("shot_start_f", -1)), shot_end_f=int(data.get("shot_end_f", -1)),
                   effect=str(data.get("effect", "")))


@dataclass(frozen=True)
class Chunk:
    index: int
    story_start_f: int
    delivered_frames: int
    head_frames: int
    shots: tuple = ()
    is_last: bool = False
    continuation_id: str = ""
    SCHEMA_VERSION = 1

    @property
    def sampled_frames(self):
        return self.delivered_frames + self.head_frames

    @property
    def story_end_f(self):
        return self.story_start_f + self.delivered_frames

    @property
    def is_first(self):
        return self.index == 0

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "index": self.index, "story_start_f": self.story_start_f,
                "delivered_frames": self.delivered_frames, "head_frames": self.head_frames, "is_last": self.is_last,
                "shots": [s.to_dict() for s in self.shots], "continuation_id": self.continuation_id}

    @classmethod
    def from_dict(cls, data, path="chunk"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        shots = tuple(ChunkShot.from_dict(d, "%s.shots[%d]" % (path, n)) for n, d in enumerate(fields.read_list(data, "shots", path)))
        return cls(index=int(fields.read_number(data, "index", path, minimum=0)), story_start_f=int(fields.read_number(data, "story_start_f", path)),
                   delivered_frames=int(fields.read_number(data, "delivered_frames", path, minimum=1)),
                   head_frames=int(fields.read_number(data, "head_frames", path, minimum=0)), shots=shots, is_last=bool(data.get("is_last", False)),
                   continuation_id=fields.read_str(data, "continuation_id", path, ""))


@dataclass(frozen=True)
class ChunkOpening:
    head_frames: int = 0
    context_id: str = ""


@dataclass(frozen=True)
class SequencePlan:
    requested_frames: int
    continuity: ContinuityPlan
    chunks: tuple
    issues: tuple = ()
    SCHEMA_VERSION = 1

    @property
    def total_frames(self):
        return sum(c.delivered_frames for c in self.chunks)

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "requested_frames": self.requested_frames,
                "continuity": self.continuity.to_dict(), "chunks": [c.to_dict() for c in self.chunks],
                "issues": [i.to_dict() for i in self.issues]}

    @classmethod
    def from_dict(cls, data, path="plan"):
        data = fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        return cls(requested_frames=int(fields.read_number(data, "requested_frames", path, minimum=1)),
                   continuity=ContinuityPlan.from_dict(data.get("continuity", {"schema_version": 1}), path + ".continuity"),
                   chunks=tuple(Chunk.from_dict(d, "%s.chunks[%d]" % (path, n)) for n, d in enumerate(fields.read_list(data, "chunks", path))),
                   issues=tuple(Issue.from_dict(d) for d in fields.read_list(data, "issues", path)))


def _delivered_options(head, minimum=limits.SAMPLED_MIN_FRAMES, maximum=limits.SAMPLED_MAX_FRAMES):
    """Every delivered length whose sampled clip is inside H3's trained range, for a chunk with this head."""
    lo = max(minimum - head, 1)
    hi = maximum - head
    return frames.delivered_candidates(0, head, lo, hi)


def _pick(options, ideal):
    return min(options, key=lambda v: (abs(v - ideal), v))


def plan_lengths(total_frames, chunk_target_frames, head, first_head=0, minimum=limits.SAMPLED_MIN_FRAMES, maximum=limits.SAMPLED_MAX_FRAMES):
    """Delivered frames per chunk. Error diffusion: each chunk takes the grid length nearest to what is still needed per chunk.

    `first_head` is the first chunk's own pin: 0 at the start of the video or of an unpinned part, `head` after a join."""
    first_options, next_options = _delivered_options(first_head, minimum, maximum), _delivered_options(head, minimum, maximum)
    longest = max(next_options)
    # One grid step over the target is no reason for another part: a keyframe at 10 s with 10 s parts ends its part on
    # H3's grid at 10.08 s, and 243 of 240 frames made two parts of 5 s instead of one (2026-10-11).
    count = max(1, -(-(total_frames - limits.GRID_STEP) // max(min(chunk_target_frames, longest), 1)))
    # The target is a preference; it cannot require more minimum-size clips
    # than the project fits, or fewer clips than its maximum lengths can hold.
    least = max(1, 1 + -(-(total_frames - max(first_options)) // longest))
    most = max(1, 1 + (total_frames - min(first_options)) // min(next_options))
    count = max(least, min(count, most))
    lengths, remaining = [], total_frames
    for position in range(count):
        options = first_options if position == 0 else next_options
        ideal = remaining / float(count - position)
        lengths.append(_pick(options, ideal))
        remaining -= lengths[-1]
    return lengths


def _shots_for_chunk(shots, story_start, story_end, head, external=False):
    window_start = story_start if external else story_start - head
    sample_start = story_start - head
    out = []
    for shot in shots:
        if shot.end_f <= window_start or shot.start_f >= story_end:
            continue
        local_start = 0 if external and shot.start_f <= story_start else max(shot.start_f, window_start) - sample_start
        out.append(ChunkShot(shot_index=shot.index, local_start_f=local_start,
                             local_end_f=min(shot.end_f, story_end) - sample_start, text=shot.text,
                             carried=shot.start_f < story_start, continues=shot.end_f > story_end,
                             shot_id=shot.id, media=shot.media, spoken=shot.spoken, locked_fields=shot.locked_fields,
                             shot_start_f=shot.start_f, shot_end_f=shot.end_f, effect=shot.effect))
    return tuple(out)


def _plan_issues(requested, planned, count, continuity):
    issues = []
    if planned != requested:
        issues.append(Issue("length_snapped", "The video will be %.3fs (%d frames), not %.3fs: chunks sit on H3's frame grid."
                            % (frames.frames_to_seconds(planned), planned, frames.frames_to_seconds(requested))))
    if count > 1 and continuity.mode == "none":
        issues.append(Issue("no_continuity", "%d chunks without continuity are independent clips; expect visible cuts between them." % count))
    if count - 1 > limits.AUDIO_DULLING_JOINS and continuity.mode in ("video", "video_audio"):
        issues.append(Issue("audio_dulling", "%d joins: the sound loses its highs along a long chain; measured at 5 joins." % (count - 1)))
    return issues


def _late_changes(shots, chunks):
    issues = []
    for chunk in chunks[1:]:
        if not chunk.head_frames or chunk.continuation_id:
            continue                    # nothing is pinned in front of it, so nothing holds the previous action
        for shot in shots:
            offset = shot.start_f - chunk.story_start_f
            if 0 <= offset < limits.LATE_CHANGE_FRAMES:
                issues.append(Issue("late_change", "begins %.1fs after a chunk boundary; the pinned picture holds the previous action for about 2.5s, so the change will come late."
                                    % frames.frames_to_seconds(offset), "shot %d" % shot.index))
    return issues


def plan_chunks(project_frames, chunk_target_frames, continuity, shots=(), cuts=(), joins=(), max_frames=limits.SAMPLED_MAX_FRAMES):
    """Split `project_frames` into chunks. Returns a SequencePlan; corrections are in plan.issues.

    `cuts` are story frames where a chunk starts without a pinned head, like the first one: a shot that opens on a First
    frame picture of its own. `joins` are story frames where a chunk must start but keeps its pin: the chunk before ends
    on a Keyframe picture. Each edge must leave whole grid lengths before it (see project._part_edges). `max_frames` is
    the longest sampled clip for the canvas (limits.max_frames)."""
    if project_frames < 1:
        raise ValueError("the project needs at least one frame")
    head = continuity.head
    openings = cuts if isinstance(cuts, dict) else {frame: ChunkOpening() for frame in cuts}
    external = any(opening.context_id for opening in openings.values())
    edges = sorted({0, *cuts, *joins, project_frames})
    lengths, heads, sources = [], [], []
    for start, end in zip(edges, edges[1:]):
        opening = openings.get(start, ChunkOpening(head if start in joins else 0))
        first_head = opening.head_frames
        minimum = limits.GRID_OFFSET if external else limits.SAMPLED_MIN_FRAMES
        part = plan_lengths(end - start, max(chunk_target_frames, 1), head, first_head, minimum, max_frames)
        if head and shots:
            part = align_to_shots(part, head, [replace(s, start_f=s.start_f - start) for s in shots if start < s.start_f < end], first_head,
                                  max_frames)
        lengths += part
        heads += [first_head] + [head] * (len(part) - 1)
        sources += [opening.context_id] + [""] * (len(part) - 1)
    chunks, cursor = [], 0
    for index, delivered in enumerate(lengths):
        this_head = heads[index]
        chunks.append(Chunk(index=index, story_start_f=cursor, delivered_frames=delivered, head_frames=this_head,
                            shots=_shots_for_chunk(shots, cursor, cursor + delivered, this_head, bool(sources[index])),
                            is_last=index == len(lengths) - 1, continuation_id=sources[index]))
        cursor += delivered
    issues = _plan_issues(project_frames, cursor, len(chunks), continuity)
    if continuity.mode != "none":
        issues += _late_changes(shots, chunks)
    return SequencePlan(requested_frames=project_frames, continuity=continuity, chunks=tuple(chunks), issues=tuple(issues))
