"""Move chunk boundaries so a new shot does not begin right after a join (experiment E7) or right before one.

The pinned picture holds the previous action for about 2.5 s, so a shot that starts less than that after a boundary comes late. A shot
that starts in a part's last two seconds has no room there: H3 cut 1.6 s early, and the next part cut again after its head (Ref2VA
minute, 2026-10-20: two cuts, 18.38 s and 20.04 s, for one shot change at 20.0 s). Either the boundary moves earlier, so the held
stretch ends where the shot should begin, or later, so the join falls inside the new shot. Boundaries only move in whole 17-frame
steps, which keeps every chunk on the frame grid, and the total length never changes.
"""
from . import frames, limits
from .shot_share import SPEAK_MIN_FRAMES as END_LEAD    # a shot needs two seconds of its part before the part ends

STEP = limits.GRID_STEP


def _candidates(boundary, shot_start):
    """Boundary shifts that fix a shot starting `shot_start - boundary` frames after it: earlier, or later, in whole steps.
    Either way the shot gets the held stretch's 2.5 s: after the new edge, or before it in the part that shows the cut."""
    earlier = -(-(boundary - (shot_start - limits.LATE_CHANGE_FRAMES)) // STEP) * STEP
    later = -(-((shot_start + limits.LATE_CHANGE_FRAMES) - boundary) // STEP) * STEP
    return sorted((-earlier, later), key=abs)


def _fits(lengths, k, delta, head, first_head=0, maximum=limits.SAMPLED_MAX_FRAMES):
    low_a, high_a = frames.delivered_bounds(first_head if k == 0 else head, maximum)
    low_b, high_b = frames.delivered_bounds(head, maximum)
    return low_a <= lengths[k] + delta <= high_a and low_b <= lengths[k + 1] - delta <= high_b


def align_to_shots(lengths, head, shots, first_head=0, maximum=limits.SAMPLED_MAX_FRAMES):
    """Returns new delivered lengths with the same total. Boundaries that are fine are left alone."""
    lengths = list(lengths)
    starts = [s.start_f for s in shots if s.start_f > 0]
    for k in range(len(lengths) - 1):
        boundary = sum(lengths[:k + 1])
        late = [t for t in starts if -END_LEAD < t - boundary < limits.LATE_CHANGE_FRAMES]
        if not late:
            continue
        for delta in _candidates(boundary, late[0]):
            if _fits(lengths, k, delta, head, first_head, maximum):
                lengths[k] += delta
                lengths[k + 1] -= delta
                break
    return lengths
