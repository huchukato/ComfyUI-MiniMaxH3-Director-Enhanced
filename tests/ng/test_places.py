"""A shot set in the place of an earlier one ("Place like Shot 1", core/places.py; user 2026-10-18 after the tavern test)."""
import json
import os
from dataclasses import replace
import tempfile
import unittest
from unittest import mock

from _pack import comfy_available, module

ctx, chunks, project, places = (module("ng.core.context"), module("ng.core.chunks"), module("ng.core.project"),
                                module("ng.core.places"))
HAVE_COMFY = comfy_available()


def plan(mode="ref2va", place_from="s1", seconds=(5, 5, 5), items=None, **picture):
    starts = [sum(seconds[:n]) for n in range(len(seconds))]
    texts = ("@Luna sits in a cozy tavern.", "@Luna walks across a market square.", "@Luna comes back into the tavern.")
    records = [{"id": "s%d" % (n + 1), "start": start, "end": start + length, "text": texts[n % 3], "media": []}
               for n, (start, length) in enumerate(zip(starts, seconds))]
    if place_from is not None:
        records[-1]["place_from"] = place_from
        records[-1].update(picture)
    luna = ctx.ContextItem("luna", "Luna", "image", "luna.png", usage=("reference",), content=("character",), description="A woman.")
    context = ctx.DirectorContext(shots_text=json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": records}),
                                  items=(luna,) if items is None else items, project_seconds=sum(seconds), mode=mode, music="N/A",
                                  soundscape="Quiet.", width=1024, height=576)
    return project.plan_project(context, 0, chunks.ContinuityPlan("video_audio"))


def codes(result):
    return [issue.code for issue in result.issues]


class Planning(unittest.TestCase):
    def test_the_later_shot_opens_its_own_part_and_gets_the_place_card(self):
        result = plan()
        third = next(r for r in json.loads(result.context.shots_text)["shots"] if r["id"] == "s3")
        target = next(c for c in result.plan.chunks if c.story_start_f == module("ng.core.frames").seconds_to_frames(third["start"]))
        self.assertGreater(target.index, 0)
        self.assertEqual(target.head_frames, 0, "a cut back to the place: not pinned to the market square before it")
        (place,) = result.places
        self.assertEqual((place.target_id, place.source_id), ("s3", "s1"))
        self.assertEqual(place.frame, 24, "1 s into the earlier shot")
        self.assertTrue(place.source.startswith(places.FOLDER + "/"))
        compiled = result.compiled[target.index]
        self.assertIn(place.context_id, [ref.ctx_id for ref in compiled.refs])
        self.assertIn(places.DESCRIPTION, compiled.prompt)
        for earlier in result.compiled[:target.index]:
            self.assertNotIn(place.context_id, [ref.ctx_id for ref in earlier.refs], "only the later shot uses it")

    def test_the_picture_is_in_an_earlier_part_than_the_one_that_uses_it(self):
        result = plan()
        (place,) = result.places
        source = [c for c in result.plan.chunks if places.in_chunk(result.places, c)]
        user = [c for c, compiled in zip(result.plan.chunks, result.compiled) if place.context_id in [r.ctx_id for r in compiled.refs]]
        self.assertEqual(len(source), 1)
        self.assertLess(source[0].index, user[0].index)

    def test_an_automatic_first_last_frame_project_stays_one(self):
        result = plan(mode="auto", items=())
        self.assertEqual(result.context.mode, "fl2va")
        self.assertTrue(result.places)

    def test_without_a_link_nothing_changes(self):
        self.assertEqual(plan(place_from=None).places, ())
        self.assertNotIn("place_moved", codes(plan(place_from=None)))

    def test_a_missing_or_later_source_is_reported_and_left_out(self):
        gone = plan(place_from="nope")
        self.assertEqual(gone.places, ())
        self.assertIn("place_unknown", codes(gone))
        later = plan(place_from="s3")
        self.assertEqual(later.places, ())
        self.assertIn("place_later", codes(later))

    def test_a_shot_too_short_for_a_part_of_its_own_is_left_out(self):
        result = plan(seconds=(5, 5, 0.5))
        self.assertEqual(result.places, ())
        self.assertIn("place_too_close", codes(result))

    def test_the_picture_kind_and_its_candidates(self):
        (clean,) = plan().places
        self.assertEqual((clean.kind, clean.view), ("clean", ""))
        self.assertEqual(clean.candidates[0], clean.frame, "the frame 1 s in is tried first")
        self.assertEqual(len(clean.candidates), places.CANDIDATES)
        self.assertTrue(all(12 <= f < 5 * 24 - 12 for f in clean.candidates), "half a second in from the earlier shot's edges")
        (raw,) = plan(place_picture="raw").places
        self.assertEqual(raw.candidates, (raw.frame,))
        (view,) = plan(place_picture="view", place_view="from the bar toward the door").places
        self.assertEqual((view.kind, view.view), ("view", "from the bar toward the door"))
        (odd,) = plan(place_picture="sideways", place_view="ignored").places
        self.assertEqual((odd.kind, odd.view), ("clean", ""))

    def test_two_shots_in_the_same_place_get_a_card_each(self):
        result = plan(seconds=(5, 5, 5, 5), place_picture="view", place_view="from the door")
        doc = json.loads(result.context.shots_text)
        doc["shots"][2]["place_from"] = "s1"
        context = replace(result.context, shots_text=json.dumps(doc))
        both = project.plan_project(context, 0, chunks.ContinuityPlan("video_audio")).places
        self.assertEqual(len({p.context_id for p in both}), 2)

    def test_the_picture_lies_inside_the_earlier_shot(self):
        result = plan(seconds=(1, 5, 5))
        (place,) = result.places
        self.assertLess(place.frame, 24, "a 1 s shot: its middle, not past its end")


class Window(unittest.TestCase):
    @unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
    def test_the_window_starts_one_vae_clip_early_and_finds_the_frame(self):
        adapter = module("ng.adapters.places")
        self.assertEqual(adapter.window(5, 60), (0, 7, 5))
        start, stop, index = adapter.window(40, 60)
        self.assertEqual((start, stop), (5, 17))
        self.assertEqual(index, 40 - 17)


NO_QWEN = {"image": None, "encoder": None, "vae": None}
QWEN = {"image": "qwen_image.safetensors", "encoder": "qwen3vl_8b.safetensors", "vae": "qwen_vae.safetensors"}


@unittest.skipUnless(HAVE_COMFY, "ComfyUI is not importable")
class Writing(unittest.TestCase):
    """The models are mocked: SAM3's person share per candidate, Qwen's edit."""
    def setUp(self):
        self.adapter, self.pin = module("ng.adapters.places"), module("ng.core.pin")

    def written(self, result, shares=None, qwen=NO_QWEN, edit=None):
        import torch
        from comfy.nested_tensor import NestedTensor
        from PIL import Image
        job = next(j for j in project.jobs(result) if places.in_chunk(result.places, j.chunk))
        steps = self.pin.steps_for_frames(job.chunk.sampled_frames)
        latent = {"samples": NestedTensor((torch.zeros(1, 24, steps, 2, 2), torch.zeros(1, 32, 2, 4)))}

        def decode(video):
            count = self.pin.pixel_frames(video.shape[2])
            return torch.arange(count).float().div(1000).view(count, 1, 1, 1).expand(count, 4, 4, 3)

        with tempfile.TemporaryDirectory() as root, mock.patch("folder_paths.get_input_directory", return_value=root), \
                mock.patch.object(self.adapter, "person_shares", return_value=shares), \
                mock.patch.object(self.adapter, "qwen_files", return_value=qwen), \
                mock.patch.object(self.adapter, "qwen_edit", side_effect=edit) as edits:
            (path, how), = self.adapter.write(job, latent, decode)
            self.assertTrue(path.startswith(os.path.join(root, places.FOLDER)))
            with Image.open(path) as picture:
                return picture.getpixel((0, 0))[0], how, edits.call_args_list

    def test_as_rendered_is_the_frame_one_second_in(self):
        value, how, edits = self.written(plan(place_picture="raw"))
        self.assertEqual(value, round(24 / 1000 * 255))
        self.assertEqual((how, edits), ("as rendered", []))

    def test_without_people_takes_the_candidate_nobody_is_in(self):
        result = plan()
        (place,) = result.places
        shares = [0.2, 0.1, 0.0, 0.3, 0.0, 0.4]
        value, how, edits = self.written(result, shares=shares)
        self.assertEqual(value, round(place.candidates[2] / 1000 * 255), "the first candidate without a person")
        self.assertEqual(edits, [])
        self.assertIn("nobody in it", how)

    def test_a_person_in_every_candidate_is_painted_out(self):
        import torch
        painted = lambda files, picture, prompt, seed: torch.full_like(picture, 0.5)
        value, how, edits = self.written(plan(), shares=[0.2, 0.1, 0.3, 0.3, 0.3, 0.4], qwen=QWEN, edit=painted)
        self.assertEqual(value, round(0.5 * 255))
        self.assertEqual(len(edits), 1)
        self.assertIn("Remove every person", edits[0].args[2])
        self.assertIn("painted out", how)

    def test_without_qwen_the_least_person_frame_is_used(self):
        result = plan()
        (place,) = result.places
        value, how, _ = self.written(result, shares=[0.2, 0.1, 0.3, 0.3, 0.3, 0.4])
        self.assertEqual(value, round(place.candidates[1] / 1000 * 255))
        self.assertIn("no Qwen", how)

    def test_another_view_is_painted_from_the_clean_picture(self):
        import torch
        painted = lambda files, picture, prompt, seed: torch.full_like(picture, 0.25)
        _, how, edits = self.written(plan(place_picture="view", place_view="from the bar toward the door"), shares=[0.0] * 6,
                                     qwen=QWEN, edit=painted)
        self.assertEqual(len(edits), 1, "nobody to paint out, one edit for the view")
        self.assertIn("from the bar toward the door", edits[0].args[2])
        self.assertIn("new view", how)

    def test_a_rewritten_picture_does_not_change_the_resume_key(self):
        resume = module("ng.adapters.resume")
        result = plan()
        job = next(j for j in project.jobs(result) if any(places.is_place(r.ctx_id) for r in j.compiled.refs))
        with mock.patch.object(resume, "_file", return_value=[1, 2]):
            first = resume.part_key(job, {"seed": 1})
        with mock.patch.object(resume, "_file", side_effect=lambda source: [1, 2] if source == "luna.png" else [9, 9]):
            rewritten = resume.part_key(job, {"seed": 1})
        self.assertEqual(first, rewritten)
        other = next(j for j in project.jobs(plan(place_picture="view", place_view="from the door"))
                     if any(places.is_place(r.ctx_id) for r in j.compiled.refs))
        with mock.patch.object(resume, "_file", return_value=[1, 2]):
            self.assertNotEqual(first, resume.part_key(other, {"seed": 1}), "another kind of picture renders the part again")


if __name__ == "__main__":
    unittest.main()
