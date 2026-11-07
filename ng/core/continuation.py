"""External video prefixes: selected source tail and the story openings that consume it."""
import math

from .audio_timing import locked_spans
from .chunks import Chunk, ChunkOpening, _shots_for_chunk
from .legacy_bridge import decide_mode
from .limits import CONTINUE_REF_AUDIO_FRAMES, CONTINUE_VIDEO_FRAMES, FPS, GRID_OFFSET, GRID_STEP
from .shot_bindings import scoped_context
from .shot_document import bound_media_ids, read_document


def source_end(item):
    ends = [end for end in (item.options.end_s, item.length_s) if end > 0]
    return min(ends) if ends else 0.0


def has_locked_sound(context):
    if locked_spans(context):
        return True
    # A later Shot can give an ordinary sound card the Lock role only locally.
    for record in read_document(context.shots_text) or ():
        for binding in record.get("media", ()):
            item = context.item(binding.get("context_id"))
            if binding.get("role") == "lock" and item and item.media == "audio" and item.source:
                return True
    return False


def preferred_frames(context, item, shot=None):
    if context is None or item.options.video_audio != "reference":
        return CONTINUE_VIDEO_FRAMES
    has_locks = has_locked_sound(context)
    if shot is not None:
        sample = Chunk(0, shot.start_f, shot.frames, 0,
                       shots=_shots_for_chunk((shot,), shot.start_f, shot.end_f, 0))
        context, _ = scoped_context(context, sample)
    if decide_mode(context) == "ref2va" and not has_locks:
        return CONTINUE_REF_AUDIO_FRAMES
    return CONTINUE_VIDEO_FRAMES


def prefix_frames(item, wanted=CONTINUE_VIDEO_FRAMES):
    end = source_end(item)
    available = math.floor((end - item.options.start_s) * FPS + 1e-6) if end else wanted
    count = min(wanted, max(available, 1))
    return count - (count - GRID_OFFSET) % GRID_STEP if count >= GRID_OFFSET else 1


def global_source(context):
    bound = bound_media_ids(context.shots_text)
    return next((item for item in context.by_media("video") if item.id not in bound and item.source
                 and "continue" in item.effective_usage), None)


def shot_source(context, shot):
    for binding in shot.media:
        item = context.item(binding.context_id)
        if item and item.media == "video" and item.source:
            roles = item.effective_usage if binding.role == "context" else (binding.role,)
            if "continue" in roles:
                return item
    return None


def opening(item, context=None, shot=None):
    if not item or (source_end(item) and source_end(item) <= item.options.start_s):
        return None
    return ChunkOpening(prefix_frames(item, preferred_frames(context, item, shot)), item.id)


def initial_opening(context, shots):
    item = next((shot_source(context, shot) for shot in shots if shot.start_f == 0 and shot_source(context, shot)), None)
    first = next((shot for shot in shots if shot.start_f == 0), None)
    return opening(item or global_source(context), context, first)
