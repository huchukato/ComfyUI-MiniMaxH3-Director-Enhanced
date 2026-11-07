"""The arithmetic of pinning the tail of one clip in front of the next (experiments E2, E4, E6).

Video latent steps cover 1, 4, 4, 4, 4, 1, ... pixel frames; audio latent steps run at 40 Hz, so a pixel frame is 5/3 audio steps.
The pinned picture sits at the start of the new clip's timeline; the pinned sound must END where the pinned picture ends and reach
backwards, which needs a fractional, negative anchor index. Snapping its end onto the target's own audio grid removes the
constant 8 ms lateness measured without it.
"""
from dataclasses import dataclass

from .limits import AUDIO_HZ, FPS

FRAMES_PER_STEP = (1, 4, 4, 4, 4)
FRAME_RESCALE = AUDIO_HZ / float(FPS)       # 5/3 audio steps per pixel frame


def pixel_frames(steps):
    return sum(FRAMES_PER_STEP[k % 5] for k in range(steps))


def step_offsets(steps):
    """Pixel-frame index at which each video latent step begins."""
    offsets, acc = [], 0
    for k in range(steps):
        offsets.append(acc)
        acc += FRAMES_PER_STEP[k % 5]
    return offsets


def steps_for_frames(frames):
    """Latent steps that cover exactly `frames` pixel frames counted from a cycle start, or None when no whole number does."""
    steps = covered = 0
    while covered < frames:
        covered += FRAMES_PER_STEP[steps % 5]
        steps += 1
    return steps if covered == frames else None


@dataclass(frozen=True)
class VideoPin:
    start_step: int          # first latent step of the previous clip that is pinned
    steps: int
    offsets: tuple           # pixel-frame position of each pinned step in the new clip
    span: int                # pixel frames covered = the head to cut off again


def video_pin(window_frames, previous_steps):
    steps = steps_for_frames(window_frames)
    if steps is None:
        raise ValueError("a %d frame window is not a whole number of latent steps; use 5, 22, 39 or 56" % window_frames)
    if steps > previous_steps:
        raise ValueError("the previous clip has %d video steps, the window needs %d" % (previous_steps, steps))
    start = previous_steps - steps
    if start % 5:
        raise ValueError("the tail would start inside a 1-4-4-4-4 cycle (step %d); previous clip lengths must be 17k+5 frames" % start)
    return VideoPin(start, steps, tuple(step_offsets(steps)), pixel_frames(steps))


def audio_overhang(audio_steps, video_steps):
    """How far the audio grid reaches past the last pixel frame, in audio steps: exactly 0, +1/3 or -1/3 for legal clips."""
    return audio_steps - FRAME_RESCALE * pixel_frames(video_steps)


@dataclass(frozen=True)
class AudioPin:
    steps: int               # audio latent steps pinned
    index: float             # anchor index for the keyframe: fractional and usually negative
    end_coord: int           # audio step coordinate (relative to the clip start) where the pinned window ends


def audio_pin(audio_frames, previous_audio_steps, previous_video_steps, head_frames):
    rt = min(max(int(round(audio_frames / float(FPS) * AUDIO_HZ)), 1), previous_audio_steps)
    overhang = audio_overhang(previous_audio_steps, previous_video_steps)
    if not -0.5 < overhang < 0.5:
        overhang = 0.0
    end_coord = int(round(FRAME_RESCALE * (head_frames + overhang / FRAME_RESCALE)))
    return AudioPin(rt, (end_coord - rt) / FRAME_RESCALE, end_coord)
