"""BUG-019: eine zweite Stimme derselben Figur verdraengt die erste still, wenn beide
ueber eine Shot-Bindung statt ueber den Sprecher-Slot laufen.

_voices_by_speaker nimmt takes[0] in den Slot und stuft jede weitere nur herab. Werden
beide per `spoken[].speaker_id` gebunden, entscheidet die Reihenfolge im Dokument, nicht
das Studio. Kein Fix, nur Beleg.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import module  # noqa: E402

context_mod = module("ng.core.context")
legacy_bridge = module("ng.core.legacy_bridge")
shot_bindings = module("ng.core.shot_bindings")
chunks = module("ng.core.chunks")
shots_mod = module("ng.core.shots")


def spoken(speaker):
    return {"schema_version": 1, "text": "Hallo.", "speaker_id": speaker,
            "voice": "a narrator", "language": "German", "delivery": "says"}


def document(speaker_id):
    return json.dumps({
        "format": "h3-director-shots", "schema_version": 1,
        "shots": [{"id": "s1", "start": 0, "end": 6, "text": "A",
                   "media": [{"schema_version": 1, "context_id": "img", "role": "reference"}],
                   "spoken": [spoken(speaker_id)], "locked_fields": []}],
        "audio": [], "audio_lanes": [],
    })


def picture():
    return context_mod.ContextItem(id="img", name="Mage", media="image", source="mage.png",
                                   usage=("reference",), description="A mage")


def voice(speaker=""):
    return context_mod.ContextItem(id="voice_a", name="Stimme A", media="audio", source="a.wav",
                                   usage=("voice",), speaker=speaker, length_s=10.0,
                                   description="Voice of Mage")


class VoiceSlot(unittest.TestCase):
    def test_control_a_voice_bound_by_its_speaker_widget_reaches_the_slot(self):
        context = context_mod.DirectorContext(idea="x", project_seconds=10.0,
                                              shots_text=document("img"),
                                              items=(picture(), voice("img")))
        voices, extra = legacy_bridge._voices_by_speaker(context)
        self.assertEqual([v.name for v in voices.values()], ["Stimme A"])
        self.assertEqual(extra, {})

    def test_bug_019_a_voice_named_only_in_the_shot_never_reaches_the_slot(self):
        # Der Shot benennt die Stimme als speaker_id, die Audiokarte hat aber kein
        # speaker-Widget gesetzt. Der Slot bleibt leer, und es kommt keine Meldung.
        context = context_mod.DirectorContext(idea="x", project_seconds=10.0,
                                              shots_text=document("voice_a"),
                                              items=(picture(), voice("")))
        voices, extra = legacy_bridge._voices_by_speaker(context)
        issues = legacy_bridge.extra_voice_issues(extra, context)
        print("Slot:", {k: v.name for k, v in voices.items()})
        print("Issues:", [str(i) for i in issues])
        self.assertEqual([v.name for v in voices.values()], ["Stimme A"],
                         "the voice named in the shot must still reach the subject's voice slot")
        self.assertTrue(issues, "a voice that reaches nobody must be reported, not dropped in silence")


if __name__ == "__main__":
    unittest.main()