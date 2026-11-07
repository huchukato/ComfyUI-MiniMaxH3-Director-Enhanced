"""Compare the Studio's displayed file interval with the actual compiled lock interval; no audio/GPU needed."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _pack import module, REPO

context = module("ng.core.context")
options = module("ng.core.context_options")
project = module("ng.core.project")
chunks = module("ng.core.chunks")
NODE = shutil.which("node")


def compile_and_display(source_start, mode="fl2va", clip_mode="lock", offset=10, source_end=40):
    clip = dict(schema_version=1, id="clip_a", context_id="song", start=2, end=6, offset=offset, mode=clip_mode, lane="lane_a")
    document = json.dumps(dict(format="h3-director-shots", schema_version=1, shots=[], audio=[clip]))
    song = context.ContextItem("song", "Song", "audio", "fixture.wav", usage=("music_style",), length_s=60,
                               options=options.ContextOptions(start_s=source_start, end_s=source_end))
    director = context.DirectorContext(idea="A walk.", shots_text=document, items=(song,), project_seconds=8, mode=mode)
    result = project.plan_project(director, 0, chunks.ContinuityPlan("none"))
    chunk = result.plan.chunks[0]
    refs = result.compiled[0].of_kind("lock" if clip_mode == "lock" else "audio")
    script = ('import {clipParts} from "./js/ng/h3s_model.js"; '
              'const input=JSON.parse(process.argv[1]); console.log(JSON.stringify(clipParts(input.clip,input.chunks)));')
    payload = json.dumps(dict(clip=clip, chunks=[dict(index=0, start_s=chunk.story_start_f / 24, end_s=chunk.story_end_f / 24)]))
    display = json.loads(subprocess.check_output([NODE, "--input-type=module", "--eval", script, payload], cwd=REPO, text=True))
    return refs, display


@unittest.skipUnless(NODE, "Node is required to compare the real Studio model with the compiler")
class AudioSourceWindow(unittest.TestCase):
    def test_control_no_context_trim_agrees_with_studio(self):
        refs, display = compile_and_display(0)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].trim_start_f / 24, display[0]["file"][0])
        self.assertEqual((refs[0].trim_start_f + refs[0].length_f) / 24, display[0]["file"][1])

    def test_bug_016_context_trim_and_clip_offset_agree_with_studio(self):
        refs, display = compile_and_display(5)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].trim_start_f / 24, display[0]["file"][0],
                         "Studio promises file 10-14 s, compiler locks file 15-19 s")

    def test_bug_016_copy_and_reference_offsets_before_context_trim_agree_with_studio(self):
        for mode in ("copy", "ref"):
            with self.subTest(mode=mode):
                refs, display = compile_and_display(5, mode="ref2va", clip_mode=mode, offset=2)
                self.assertEqual(len(refs), 1)
                self.assertEqual(refs[0].trim_start_f / 24, display[0]["file"][0],
                                 "Context trim silently changes a lane clip's absolute file offset")

    def test_bug_016_copy_and_reference_lengths_agree_with_studio_despite_context_end(self):
        for mode in ("copy", "ref"):
            with self.subTest(mode=mode):
                refs, display = compile_and_display(0, mode="ref2va", clip_mode=mode, source_end=12)
                self.assertEqual(len(refs), 1)
                self.assertEqual((refs[0].trim_start_f + refs[0].length_f) / 24, display[0]["file"][1],
                                 "Context trim silently shortens the lane clip compared with its preview")

    def test_bug_013_ref_clip_is_not_a_supported_fl2va_soundtrack(self):
        refs, _ = compile_and_display(0, clip_mode="ref")
        self.assertEqual(refs, (), "control: the FL2VA compiler does not consume a ref clip")


class VoiceAndLane(unittest.TestCase):
    def compiled(self, bind_voice):
        clip = dict(schema_version=1, id="clip_a", context_id="voice_a", start=2, end=6, offset=10, mode="lock", lane="lane_a")
        binding = [dict(schema_version=1, context_id="voice_a", role="voice")] if bind_voice else []
        shot = dict(id="shot_a", start=0, end=8, text="The character speaks.", media=binding, spoken=[], locked_fields=[])
        document = json.dumps(dict(format="h3-director-shots", schema_version=1, shots=[shot], audio=[clip]))
        figure = context.ContextItem("figure", "Mage", "image", "fixture.png", content=("character",), usage=("reference",))
        voice = context.ContextItem("voice_a", "Voice", "audio", "fixture.wav", usage=("voice",), speaker="figure", length_s=60)
        director = context.DirectorContext(idea="", shots_text=document, items=(figure, voice), project_seconds=8, mode="ref2va")
        return project.plan_project(director, 0, chunks.ContinuityPlan("none")).compiled[0]

    def test_control_voice_card_can_be_used_as_a_lane_lock(self):
        locks = self.compiled(False).of_kind("lock")
        self.assertEqual([(ref.start_f, ref.length_f, ref.trim_start_f) for ref in locks], [(48, 96, 240)])

    def test_bug_017_voice_binding_does_not_suppress_its_independent_lane_lock(self):
        compiled = self.compiled(True)
        self.assertTrue(compiled.of_kind("audio"), "the Subject's voice reference is still compiled")
        self.assertEqual([(ref.start_f, ref.length_f, ref.trim_start_f) for ref in compiled.of_kind("lock")],
                         [(48, 96, 240)], "using this card as a Subject voice silently loses its lane lock")


if __name__ == "__main__":
    unittest.main(verbosity=2)
