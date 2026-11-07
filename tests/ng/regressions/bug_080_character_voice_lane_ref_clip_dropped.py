r"""Regression test for BUG-080: Character voice timeline reference clips on audio lanes are dropped.

Where:
- ng/core/legacy_bridge.py:181-185 (_audio_segments)

User workflow:
1. In ComfyUI Director Studio, the user creates an Image card (e.g. Alice, img_1) and an
   Audio card (e.g. AliceVoice, voice_1).
2. The user sets the 'speaker' on the audio card to Alice ('img_1'), configuring it as
   Alice's primary voice card.
3. On the Studio timeline, the user creates an audio lane ('l1') and places an audio clip
   of Alice's voice (e.g. 0s to 4s, trimmed with offset 1.0s), setting its mode to "ref"
   (Reference) to serve as a reference audio clip during rendering.
4. The user clicks Generate / Render or triggers NGH3Director.

What happens (Ist):
In `ng/core/legacy_bridge.py:181-185`:
```python
if item.id in used:
    for mode in ("lock", "copy"):
        if item.id in lanes[mode]:
            segments.extend(timed_segments(item, chunk, lanes[mode], _AUDIO_RETENTION[mode], in_file=True))
    continue
```
`used` contains the primary voice audio items bound to character subjects (`voices.values()`).
Because `item.id in used`, `_audio_segments` only checks `("lock", "copy")` and immediately executes `continue`.
It skips `_lane_references(item, chunk, lanes["ref"].get(item.id, ()))` and `_shot_bound`!
As a result:
- `timeline_data["audioSegments"]` does not contain the reference clip from the audio lane.
- The model never receives `<Audio 2>` with the user's intended timeline in/out trim and time window.
- If the user has two voice takes for Alice, the first take's timeline reference clip is dropped,
  while the second take's timeline reference clip is preserved (because only the first take is in `used`).

What should happen (Soll):
When a character's voice card is placed on an audio lane in `mode: "ref"`, `_audio_segments`
must include its reference segment via `_lane_references(item, chunk, lanes["ref"].get(item.id, ()))`,
so that timeline reference clips are not discarded.

Run:
    D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe -B tests/ng/regressions/bug_080_character_voice_lane_ref_clip_dropped.py
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NG_TESTS = os.path.dirname(HERE)
if NG_TESTS not in sys.path:
    sys.path.insert(0, NG_TESTS)

from _pack import module, stub_prompt_server  # noqa: E402

stub_prompt_server()

context_mod = module("ng.core.context")
legacy_bridge = module("ng.core.legacy_bridge")
chunks_mod = module("ng.core.chunks")
shots_mod = module("ng.core.shots")
plan_mod = module("minimax_plan")


def make_chunk(shots_text, project_seconds=10.0, chunk_delivered=144):
    total_frames = int(round(project_seconds * 24))
    shots, _ = shots_mod.parse_shots(shots_text, total_frames)
    chunk_shots = tuple(
        chunks_mod.ChunkShot(
            shot_index=s.index,
            local_start_f=s.start_f,
            local_end_f=s.end_f,
            text=s.text,
            carried=False,
            continues=False,
            shot_id=s.id,
            media=s.media,
            spoken=s.spoken,
            locked_fields=s.locked_fields,
        )
        for s in shots
    )
    return chunks_mod.Chunk(
        index=0,
        story_start_f=0,
        delivered_frames=chunk_delivered,
        head_frames=0,
        shots=chunk_shots,
    )


class TestBug080CharacterVoiceLaneRefClipDropped(unittest.TestCase):
    def test_control_unbound_voice_lane_ref_clip_is_preserved(self):
        """Green Control: An audio card NOT bound to a subject (speaker='') preserves its ref lane clip."""
        doc = json.dumps({
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 6, "text": "A scene", "media": [], "spoken": [], "locked_fields": []}],
            "audio": [{"schema_version": 1, "id": "c1", "context_id": "voice_1", "start": 0, "end": 4, "offset": 1.0, "mode": "ref", "lane": "l1"}],
            "audio_lanes": ["l1"],
        })
        img = context_mod.ContextItem(id="img_1", name="Alice", media="image", source="alice.png", usage=("reference",))
        voice = context_mod.ContextItem(id="voice_1", name="AliceVoice", media="audio", source="voice.wav", usage=("voice",), speaker="", length_s=10.0)

        ctx = context_mod.DirectorContext(idea="test", project_seconds=10.0, shots_text=doc, items=(img, voice))
        chunk = make_chunk(ctx.shots_text)
        tdata, _mapping, _notes = legacy_bridge.build_timeline(ctx, chunk, "ref2va", ())

        segs = tdata.get("audioSegments", [])
        self.assertEqual(len(segs), 1, "Unbound audio card must produce exactly 1 reference audio segment")
        self.assertEqual(segs[0]["fileName"], "AliceVoice")
        self.assertEqual(segs[0]["trimStart"], 24, "Offset 1.0s @ 24fps = frame 24")
        self.assertEqual(segs[0]["length"], 96, "Duration 4.0s @ 24fps = 96 frames")
        self.assertEqual(segs[0]["retention"], "reference")

    def test_control_voice_without_lane_clip_is_not_duplicated(self):
        """Green Control: A bound voice card without lane clips is assigned to subjects[0]['voice'] and not duplicated in audioSegments."""
        doc = json.dumps({
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 6, "text": "A scene", "media": [], "spoken": [], "locked_fields": []}],
            "audio": [],
            "audio_lanes": [],
        })
        img = context_mod.ContextItem(id="img_1", name="Alice", media="image", source="alice.png", usage=("reference",))
        voice = context_mod.ContextItem(id="voice_1", name="AliceVoice", media="audio", source="voice.wav", usage=("voice",), speaker="img_1", length_s=10.0)

        ctx = context_mod.DirectorContext(idea="test", project_seconds=10.0, shots_text=doc, items=(img, voice))
        chunk = make_chunk(ctx.shots_text)
        tdata, _mapping, _notes = legacy_bridge.build_timeline(ctx, chunk, "ref2va", ())

        subjects = tdata.get("subjects", [])
        self.assertEqual(len(subjects), 1)
        # Alice says nothing in this part, so her voice sample stays out: sent along, H3 spoke a sentence of the sample
        # (GUI test 2026-10-25). It is not duplicated into audioSegments either.
        self.assertIsNone(subjects[0].get("voice"))
        self.assertEqual(tdata.get("audioSegments", []), [], "Unplaced bound voice must not be duplicated into audioSegments")
        speaking = json.loads(doc)
        speaking["shots"][0]["spoken"] = [{"schema_version": 1, "text": "Hello.", "speaker_id": "img_1"}]
        ctx = context_mod.DirectorContext(idea="test", project_seconds=10.0, shots_text=json.dumps(speaking), items=(img, voice))
        tdata, _mapping, _notes = legacy_bridge.build_timeline(ctx, make_chunk(ctx.shots_text), "ref2va", ())
        self.assertEqual(tdata["subjects"][0]["voice"]["fileName"], "AliceVoice", "a figure that speaks keeps its voice")
        self.assertEqual(tdata.get("audioSegments", []), [])

    def test_control_bound_voice_lane_lock_clip_is_preserved(self):
        """Green Control: A bound voice card placed on an audio lane with mode 'lock' IS kept in audioSegments."""
        doc = json.dumps({
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 6, "text": "A scene", "media": [], "spoken": [], "locked_fields": []}],
            "audio": [{"schema_version": 1, "id": "c1", "context_id": "voice_1", "start": 0, "end": 4, "offset": 1.0, "mode": "lock", "lane": "l1"}],
            "audio_lanes": ["l1"],
        })
        img = context_mod.ContextItem(id="img_1", name="Alice", media="image", source="alice.png", usage=("reference",))
        voice = context_mod.ContextItem(id="voice_1", name="AliceVoice", media="audio", source="voice.wav", usage=("voice",), speaker="img_1", length_s=10.0)

        ctx = context_mod.DirectorContext(idea="test", project_seconds=10.0, shots_text=doc, items=(img, voice))
        chunk = make_chunk(ctx.shots_text)
        tdata, _mapping, _notes = legacy_bridge.build_timeline(ctx, chunk, "ref2va", ())

        segs = tdata.get("audioSegments", [])
        self.assertEqual(len(segs), 1, "Lock clip must be preserved in audioSegments")
        self.assertEqual(segs[0]["retention"], "lock")

    def test_bug_080_bound_voice_lane_ref_clip_is_dropped(self):
        """BUG-080: When Alice's voice is placed on an audio lane with mode 'ref', it is dropped from audioSegments."""
        doc = json.dumps({
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 6, "text": "A scene", "media": [], "spoken": [], "locked_fields": []}],
            "audio": [{"schema_version": 1, "id": "c1", "context_id": "voice_1", "start": 0, "end": 4, "offset": 1.0, "mode": "ref", "lane": "l1"}],
            "audio_lanes": ["l1"],
        })
        img = context_mod.ContextItem(id="img_1", name="Alice", media="image", source="alice.png", usage=("reference",))
        voice = context_mod.ContextItem(id="voice_1", name="AliceVoice", media="audio", source="voice.wav", usage=("voice",), speaker="img_1", length_s=10.0)

        ctx = context_mod.DirectorContext(idea="test", project_seconds=10.0, shots_text=doc, items=(img, voice))
        chunk = make_chunk(ctx.shots_text)
        tdata, _mapping, _notes = legacy_bridge.build_timeline(ctx, chunk, "ref2va", ())

        segs = tdata.get("audioSegments", [])
        # Soll: The timeline reference clip on lane 'l1' must be emitted into audioSegments.
        # Ist: segs is [] because ng/core/legacy_bridge.py:181-185 checks only ("lock", "copy") and executes continue.
        self.assertEqual(len(segs), 1, "Timeline 'ref' clip for bound voice card must not be dropped")
        self.assertEqual(segs[0]["fileName"], "AliceVoice")
        self.assertEqual(segs[0]["trimStart"], 24, "Trim offset 1.0s must be preserved as 24 frames")
        self.assertEqual(segs[0]["length"], 96, "Clip length 4.0s must be preserved as 96 frames")
        self.assertEqual(segs[0]["retention"], "reference")

    def test_bug_080_first_take_ref_clip_dropped_while_second_take_kept(self):
        """BUG-080: Two voice takes on audio lanes: Take 1 is dropped because it is in used, while Take 2 is kept."""
        doc = json.dumps({
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 6, "text": "A scene", "media": [], "spoken": [], "locked_fields": []}],
            "audio": [
                {"schema_version": 1, "id": "c1", "context_id": "voice_1", "start": 0, "end": 3, "offset": 0.0, "mode": "ref", "lane": "l1"},
                {"schema_version": 1, "id": "c2", "context_id": "voice_2", "start": 3, "end": 6, "offset": 0.0, "mode": "ref", "lane": "l1"},
            ],
            "audio_lanes": ["l1"],
        })
        img = context_mod.ContextItem(id="img_1", name="Alice", media="image", source="alice.png", usage=("reference",))
        voice1 = context_mod.ContextItem(id="voice_1", name="Take1", media="audio", source="take1.wav", usage=("voice",), speaker="img_1", length_s=10.0)
        voice2 = context_mod.ContextItem(id="voice_2", name="Take2", media="audio", source="take2.wav", usage=("voice",), speaker="img_1", length_s=10.0)

        ctx = context_mod.DirectorContext(idea="test", project_seconds=10.0, shots_text=doc, items=(img, voice1, voice2))
        chunk = make_chunk(ctx.shots_text)
        tdata, _mapping, _notes = legacy_bridge.build_timeline(ctx, chunk, "ref2va", ())

        segs = tdata.get("audioSegments", [])
        names = [s.get("fileName") for s in segs]
        # Soll: Both Take1 and Take2 reference clips on lane 'l1' must be preserved in audioSegments.
        # Ist: names is ['Take2'] — Take1 is discarded while Take2 is kept!
        self.assertIn("Take1", names, "Take 1 timeline reference clip must not be dropped")
        self.assertIn("Take2", names, "Take 2 timeline reference clip must be present")
        self.assertEqual(len(segs), 2)

    def test_bug_080_compiled_plan_drops_audio_reference_for_bound_voice(self):
        """BUG-080: Compiler end-to-end: minimax_plan receives only 1 audio ref (<Audio 1>) instead of 2 (<Audio 1> and <Audio 2>)."""
        doc = json.dumps({
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [{"id": "s1", "start": 0, "end": 6, "text": "@ref1 says: Hello", "media": [], "spoken": [], "locked_fields": []}],
            "audio": [{"schema_version": 1, "id": "c1", "context_id": "voice_1", "start": 0, "end": 4, "offset": 1.0, "mode": "ref", "lane": "l1"}],
            "audio_lanes": ["l1"],
        })
        img = context_mod.ContextItem(id="img_1", name="Alice", media="image", source="alice.png", usage=("reference",))
        voice = context_mod.ContextItem(id="voice_1", name="AliceVoice", media="audio", source="voice.wav", usage=("voice",), speaker="img_1", length_s=10.0)

        ctx = context_mod.DirectorContext(idea="test", project_seconds=10.0, shots_text=doc, items=(img, voice))
        chunk = make_chunk(ctx.shots_text)
        tdata, _mapping, _notes = legacy_bridge.build_timeline(ctx, chunk, "ref2va", ())

        planned = plan_mod.plan_timeline(tdata, 0, 144, 24, use_custom_motion=False, use_custom_audio=True)
        ref_audios = planned.get("ref_audio_segs", [])
        # Soll: ref_audios must include both the subject voice slot (<Audio 1>) AND the timeline reference clip (<Audio 2>).
        # Ist: ref_audios only contains [<Audio 1>] (the subject voice slot) because audioSegments was empty!
        self.assertEqual(len(ref_audios), 2, "Planned ref_audios must contain both voice slot and timeline reference clip")


if __name__ == "__main__":
    unittest.main()
