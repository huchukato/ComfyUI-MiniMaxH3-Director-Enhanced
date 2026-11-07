"""Frame arithmetic for H3: the 17k+5 grid, seconds <-> frames, chunk length rules."""
from .limits import FPS, GRID_OFFSET, GRID_STEP, SAMPLED_MAX_FRAMES, SAMPLED_MIN_FRAMES


def seconds_to_frames(seconds):
    return int(round(float(seconds) * FPS))


def frames_to_seconds(frames):
    return frames / float(FPS)


def on_grid(frames):
    return frames >= GRID_OFFSET and (frames - GRID_OFFSET) % GRID_STEP == 0


def snap_up(frames):
    """Smallest 17k+5 frame count that is at least `frames`."""
    frames = max(int(frames), GRID_OFFSET)
    return frames + (-(frames - GRID_OFFSET)) % GRID_STEP


def snap_down(frames):
    """Largest 17k+5 frame count that is at most `frames` (never below 5)."""
    frames = int(frames)
    if frames < GRID_OFFSET:
        return GRID_OFFSET
    return frames - (frames - GRID_OFFSET) % GRID_STEP


def snap_nearest(frames):
    low, high = snap_down(frames), snap_up(frames)
    return low if frames - low <= high - frames else high


def delivered_residue(head):
    """Delivered frames of a continued chunk must be congruent to this modulo 17.

    A continued chunk is sampled with its pinned head in front: sampled = delivered + head, and sampled is on the grid.
    """
    return (GRID_OFFSET - head) % GRID_STEP


def delivered_candidates(target, head, lo, hi):
    """All allowed delivered lengths in [lo, hi], nearest to `target` first."""
    residue = delivered_residue(head)
    values = [v for v in range(max(lo, 1), hi + 1) if v % GRID_STEP == residue]
    return sorted(values, key=lambda v: (abs(v - target), v))


def delivered_bounds(head, maximum=SAMPLED_MAX_FRAMES):
    """Shortest and longest delivered length whose sampled clip (head included) is inside H3's trained range (or the
    canvas' own longest clip, limits.max_frames)."""
    return max(SAMPLED_MIN_FRAMES - head, 1), maximum - head
