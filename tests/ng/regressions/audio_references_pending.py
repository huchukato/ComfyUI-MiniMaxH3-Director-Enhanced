"""Independent audio reference selections and the Studio preview must describe what the compiler sends."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _pack import module, REPO

context = module("ng.core.context")
project = module("ng.core.project")
chunks = module("ng.core.chunks")
NODE = shutil.which("node")


def clip(identity, source, start, end, offset, mode="ref"):
    return dict(schema_version=1, id=identity, context_id=source, start=start, end=end, offset=offset, mode=mode, lane="lane_a")


def plan(clips, seconds=8, chunk_seconds=0):
    ids = dict.fromkeys(entry["context_id"] for entry in clips)
    items = tuple(context.ContextItem(identity, identity, "audio", "fixture.wav", usage=("music_style",), length_s=60) for identity in ids)
    document = json.dumps(dict(format="h3-director-shots", schema_version=1, shots=[], audio=clips))
    director = context.DirectorContext(idea="A walk.", shots_text=document, items=items, project_seconds=seconds, mode="ref2va")
    return project.plan_project(director, chunk_seconds, chunks.ContinuityPlan("none"))


def budget(compiled):
    script = ('import {chunkBudget} from "./js/ng/h3s_model.js"; '
              'console.log(JSON.stringify(chunkBudget(JSON.parse(process.argv[1]))));')
    return json.loads(subprocess.check_output([NODE, "--input-type=module", "--eval", script,
                                              json.dumps(compiled.to_dict())], cwd=REPO, text=True))


class AudioReferenceSelections(unittest.TestCase):
    def test_bug_021_each_distinct_file_selection_of_one_card_reaches_the_reference_slots(self):
        result = plan([clip("first", "song", 0, 2, 0), clip("second", "song", 3, 5, 20)])
        selections = [(ref.trim_start_f, ref.length_f) for ref in result.compiled[0].of_kind("audio")]
        self.assertCountEqual(selections, [(0, 48), (480, 48)], "the second clip's distinct file selection disappeared below the audio cap")

    def test_control_two_cards_keep_both_selected_reference_intervals(self):
        result = plan([clip("first", "song_a", 0, 2, 0), clip("second", "song_b", 3, 5, 20)])
        self.assertCountEqual([(ref.trim_start_f, ref.length_f) for ref in result.compiled[0].of_kind("audio")], [(0, 48), (480, 48)])

    def test_control_copy_clips_of_one_card_keep_both_file_selections(self):
        result = plan([clip("first", "song", 0, 2, 0, "copy"), clip("second", "song", 3, 5, 20, "copy")])
        self.assertCountEqual([(ref.trim_start_f, ref.length_f) for ref in result.compiled[0].of_kind("audio")], [(0, 48), (480, 48)])

    @unittest.skipUnless(NODE, "Node is required to compare the real Studio preview")
    def test_bug_022_reference_preview_matches_the_source_interval_sent_in_each_part(self):
        reference = clip("reference", "song", 0, 20, 10)
        result = plan([reference], seconds=20, chunk_seconds=10)
        ranges = [dict(index=chunk.index, start_s=chunk.story_start_f / 24, end_s=chunk.story_end_f / 24) for chunk in result.plan.chunks]
        script = ('import {clipParts} from "./js/ng/h3s_model.js"; '
                  'const input=JSON.parse(process.argv[1]); console.log(JSON.stringify(clipParts(input.clip,input.chunks)));')
        payload = json.dumps(dict(clip=reference, chunks=ranges))
        previews = json.loads(subprocess.check_output([NODE, "--input-type=module", "--eval", script, payload], cwd=REPO, text=True))
        self.assertGreater(len(previews), 1)
        for preview in previews:
            with self.subTest(part=preview["index"]):
                refs = result.compiled[preview["index"]].of_kind("audio")
                self.assertEqual(len(refs), 1)
                actual = [refs[0].trim_start_f / 24, (refs[0].trim_start_f + refs[0].length_f) / 24]
                self.assertEqual(preview["file"], actual, "the ref preview displays a placed slice but the model receives the whole selected reference")


@unittest.skipUnless(NODE, "Node is required to compare the real reference budget")
class AudioReferenceBudget(unittest.TestCase):
    def test_bug_020_budget_counts_each_compiled_audio_input_of_the_same_card(self):
        for count in (2, 3):
            with self.subTest(native_inputs=count):
                result = plan([clip(f"copy_{i}", "song", i * 2, i * 2 + 1, i * 10, "copy") for i in range(count)])
                compiled = result.compiled[0]
                self.assertEqual(len(compiled.of_kind("audio")), count, "control: compiler keeps each selected input below the cap")
                displayed = budget(compiled)
                self.assertEqual(displayed["audio"], count, "the Studio counts cards rather than native audio inputs")
                self.assertEqual(displayed["total"], count)

    def test_control_lock_placements_do_not_consume_reference_slots(self):
        result = plan([clip("lock_a", "song", 0, 2, 0, "lock"), clip("lock_b", "song", 3, 5, 20, "lock")])
        self.assertEqual(len(result.compiled[0].of_kind("lock")), 2)
        self.assertEqual(budget(result.compiled[0]), dict(image=0, video=0, audio=0, total=0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
