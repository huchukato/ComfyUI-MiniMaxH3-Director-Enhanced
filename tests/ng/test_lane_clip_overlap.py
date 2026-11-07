"""BUG-027: zwei Tonspur-Clips derselben Karte auf derselben Spur - der zweite verschwindet
ohne Meldung. _lane_references gibt out[:1] zurueck, timed_segments nimmt alle; pruefen,
was bei zwei ref-Clips im selben Chunk passiert.
Kein Fix, nur Beleg.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import module  # noqa: E402

context_mod = module("ng.core.context")
legacy_bridge = module("ng.core.legacy_bridge")
chunks = module("ng.core.chunks")
shots_mod = module("ng.core.shots")


def document(clips):
    return json.dumps({
        "format": "h3-director-shots", "schema_version": 1,
        "shots": [{"id": "s1", "start": 0, "end": 10, "text": "A",
                   "media": [{"schema_version": 1, "context_id": "img", "role": "reference"}],
                   "spoken": [], "locked_fields": []}],
        "audio": clips, "audio_lanes": ["l1"],
    })


def clip(identity, start, end, mode="lock", lane="l1"):
    return {"schema_version": 1, "id": "c%s%d" % (identity, start), "context_id": identity,
            "start": start, "end": end, "offset": 0, "mode": mode, "lane": lane}


def audio_segments(clips, extra_items=()):
    picture = context_mod.ContextItem(id="img", name="Mage", media="image", source="mage.png",
                                      usage=("reference",), description="A mage", length_s=30.0)
    items = [picture]
    for identity in {c["context_id"] for c in clips}:
        items.append(context_mod.ContextItem(id=identity, name=identity.upper(), media="audio",
                                             source="%s.wav" % identity, usage=("sound_reference",),
                                             length_s=30.0, description="Sound"))
    items.extend(extra_items)
    context = context_mod.DirectorContext(idea="x", project_seconds=10.0,
                                          shots_text=document(clips), items=tuple(items))
    shots, _ = shots_mod.parse_shots(context.shots_text, 240)
    chunk = chunks.Chunk(index=0, story_start_f=0, delivered_frames=240, head_frames=0,
                         shots=tuple(chunks.ChunkShot(
                             shot_index=s.index, local_start_f=s.start_f, local_end_f=s.end_f,
                             text=s.text, carried=False, continues=False, shot_id=s.id,
                             media=s.media, spoken=s.spoken, locked_fields=s.locked_fields)
                             for s in shots))
    scoped, issues = module("ng.core.shot_bindings").scoped_context(context, chunk)
    tdata, _mapping, _notes = legacy_bridge.build_timeline(scoped, chunk, "ref2va", ())
    return tdata.get("audioSegments", []), [str(i) for i in issues]


class LaneClips(unittest.TestCase):
    def test_control_one_clip_plays_once(self):
        segments, issues = audio_segments([clip("a1", 0, 4)])
        self.assertEqual(len(segments), 1, "issues were %r" % issues)

    def test_bug_027_two_lock_clips_of_one_card_in_the_same_chunk(self):
        segments, issues = audio_segments([clip("a1", 0, 4), clip("a1", 5, 9)])
        print("Segmente:", [(s.get("start"), s.get("trimStart"), s.get("length")) for s in segments])
        print("Issues:", issues)
        placed = sorted((s.get("start"), s.get("length")) for s in segments)
        self.assertEqual(placed, [(0, 96), (120, 96)],
                         "both lane clips must be placed, got %r" % (placed,))

    def test_bug_027b_two_clips_overlapping_in_story_time(self):
        segments, issues = audio_segments([clip("a1", 0, 6), clip("a1", 2, 8)])
        print("Segmente:", [(s.get("start"), s.get("trimStart"), s.get("length")) for s in segments])
        spans = sorted((s.get("start"), s.get("start", 0) + s.get("length", 0)) for s in segments)
        overlaps = [(a, b) for index, a in enumerate(spans) for b in spans[index + 1:]
                    if a[0] < b[1] and b[0] < a[1]]
        self.assertEqual(overlaps, [],
                         "two clips of one card must not overlap in story time: %r" % (spans,))


if __name__ == "__main__":
    unittest.main()