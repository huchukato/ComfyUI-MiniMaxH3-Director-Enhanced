"""BUG-017: dieselbe Audiokarte an Shot und Tonspur gebunden erzeugt zwei Segmente,
die beide am Dateianfang starten — der Ton liegt doppelt und gleichzeitig auf derselben Stelle.

Gegenprobe: nur Shot-Bindung bzw. nur Tonspur ergibt genau ein Segment.
Kein Fix, nur Beleg.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import module  # noqa: E402

context_mod = module("ng.core.context")
shot_bindings = module("ng.core.shot_bindings")
chunks = module("ng.core.chunks")
legacy_bridge = module("ng.core.legacy_bridge")
shots_mod = module("ng.core.shots")


def document(with_clip, shot_media=True):
    return json.dumps({
        "format": "h3-director-shots", "schema_version": 1,
        "shots": [{"id": "s1", "start": 0, "end": 6, "text": "A",
                   "media": ([{"schema_version": 1, "context_id": "a1", "role": "copy"}] if shot_media else []),
                   "spoken": [], "locked_fields": []}],
        "audio": ([{"schema_version": 1, "id": "c1", "context_id": "a1",
                    "start": 0, "end": 4, "offset": 0, "mode": "lock", "lane": "l1"}] if with_clip else []),
        "audio_lanes": ["l1"] if with_clip else [],
    })


def segments(with_clip, shot_media=True):
    item = context_mod.ContextItem.from_dict(
        {**context_mod.ContextItem(id="a1", name="Music", media="audio", source="song.mp3",
                                  usage=("copy",), description="A song", length_s=30.0).to_dict(),
         "usage": ["copy"]})
    context = context_mod.DirectorContext(idea="x", project_seconds=10.0,
                                          shots_text=document(with_clip, shot_media), items=(item,))
    shots, _ = shots_mod.parse_shots(context.shots_text, 240)
    chunk = chunks.Chunk(index=0, story_start_f=0, delivered_frames=144, head_frames=0,
                         shots=tuple(chunks.ChunkShot(
                             shot_index=s.index, local_start_f=s.start_f, local_end_f=s.end_f,
                             text=s.text, carried=False, continues=False, shot_id=s.id,
                             media=s.media, spoken=s.spoken, locked_fields=s.locked_fields)
                             for s in shots))
    scoped, _issues = shot_bindings.scoped_context(context, chunk)
    tdata, _mapping, _notes = legacy_bridge.build_timeline(scoped, chunk, "ref2va", ())
    return tdata.get("audioSegments", [])


class DuplicateAudio(unittest.TestCase):
    def test_control_only_shot_binding_yields_one_segment(self):
        self.assertEqual(len(segments(False)), 1)

    def test_control_only_lane_clip_yields_one_segment(self):
        self.assertEqual(len(segments(True, shot_media=False)), 1)

    def test_bug_017_binding_and_lane_clip_do_not_play_the_same_audio_twice(self):
        both = segments(True)
        spans = sorted((s.get("start"), s.get("trimStart"), s.get("length")) for s in both)
        print("Segmente bei Shot-Bindung + Tonspur:", spans)
        # Jedes Paar genau einmal, ohne das Element mit sich selbst zu vergleichen.
        overlaps = [(a, b) for index, a in enumerate(spans) for b in spans[index + 1:]
                    if a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] == b[1]]
        self.assertEqual(overlaps, [],
                         "the same source must not be placed twice over the same story time")


if __name__ == "__main__":
    unittest.main()