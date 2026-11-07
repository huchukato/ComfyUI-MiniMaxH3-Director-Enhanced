"""Width/height 0 take the first picture's size the way H3 does; frame fitting and reference size reach the conditioning."""
import unittest

from _pack import comfy_available, load_full_pack, module
import test_product_nodes

ctx, chunks, project, preview = (module("ng.core.context"), module("ng.core.chunks"),
                                 module("ng.core.project"), module("ng.core.preview"))


def picture(identity, usage=("reference",)):
    return ctx.ContextItem(identity, identity.title(), "image", identity + ".png", usage=usage)


def planned(items, width=0, height=0, image_size=None):
    director = ctx.DirectorContext(idea="A walk.", width=width, height=height, items=items, project_seconds=4)
    return project.plan_project(director, 0, chunks.ContinuityPlan("none"), image_size)


class Canvas(unittest.TestCase):
    def test_h3_rule_matches_the_core_node(self):
        sizes = [(1920, 1080), (1080, 1920), (1024, 1024), (3000, 1000), (640, 480), (768, 1344)]
        expected = {(1920, 1080): (1344, 768), (1080, 1920): (768, 1344), (1024, 1024): (768, 768), (640, 480): (1024, 768)}
        for size, canvas in expected.items():
            self.assertEqual(project.h3_canvas(*size), canvas, size)
        if comfy_available():
            from comfy_extras.nodes_minimax_h3 import adapt_canvas
            for size in sizes:
                self.assertEqual(project.h3_canvas(*size), adapt_canvas(*size), size)

    def test_first_frame_wins_over_an_earlier_reference(self):
        sizes = {"ref.png": (1000, 1000), "start.png": (1080, 1920)}
        result = planned((picture("ref"), picture("start", ("first_frame",))), image_size=sizes.get)
        self.assertEqual((result.context.width, result.context.height), (768, 1344))
        self.assertIn(("canvas_from_image", ""), {(i.code, i.ref) for i in result.issues})

    def test_no_picture_or_unreadable_picture_falls_back_and_says_so(self):
        for items, sizes in (((), {}), ((picture("broken"),), {})):
            result = planned(items, image_size=sizes.get)
            self.assertEqual((result.context.width, result.context.height), (1344, 768))
            self.assertIn("canvas_default", {i.code for i in result.issues})

    def test_explicit_size_is_kept(self):
        result = planned((picture("ref"),), 864, 480, image_size=lambda _: (1080, 1920))
        self.assertEqual((result.context.width, result.context.height), (864, 480))
        self.assertFalse({"canvas_from_image", "canvas_default"} & {i.code for i in result.issues})

    def test_preview_reports_the_size_it_planned(self):
        payload = {"director": {"idea": "A walk.", "width": 0, "height": 0, "project_seconds": 4},
                   "contexts": [{"media": "image", "widgets": {"context_id": "a", "name": "A", "image": "a.png", "usage": "first_frame"}}]}
        data = preview.plan_preview(payload, image_size=lambda name: (1920, 1080) if name == "a.png" else None)
        self.assertTrue(data["ok"], data)
        self.assertEqual((data["width"], data["height"]), (1344, 768))


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class Settings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_full_pack().NODE_CLASS_MAPPINGS
        cls.helper = test_product_nodes.ProductNodes()
        cls.helper.nodes = cls.nodes

    def result(self, **extra):
        values = dict(context=self.helper.packet(), idea="A baker opens a shop.", shots="", project_seconds=8.0,
                      chunk_seconds=5.0, width=384, height=576, mode="auto", continuity="video_audio", pin_frames="22",
                      soundscape="Wind", music="N/A", seed=1, steps=4, sampler_name="res_multistep", scheduler="simple",
                      shift_video=12.0, shift_audio=3.0)
        values.update(extra)
        return self.nodes["NGH3Director"].execute(**values).args[0]

    def conditioning(self, expand):
        return next(v for v in expand.values() if v["class_type"] == "NGChunkConditioning")["inputs"]

    def test_fitting_and_reference_size_reach_both_render_paths(self):
        result = self.result(resize_method="pad", ref_image_size="max")
        for expand in (self.nodes["NGProjectRender"].execute(sequence=result).expand,
                       self.nodes["NGDirectorOutput"].execute(result=result, chunk_index=0).expand):
            inputs = self.conditioning(expand)
            self.assertEqual((inputs["resize_method"], inputs["ref_image_size"]), ("pad", "max"))

    def test_defaults_keep_the_earlier_behaviour(self):
        inputs = self.conditioning(self.nodes["NGProjectRender"].execute(sequence=self.result()).expand)
        self.assertEqual((inputs["resize_method"], inputs["ref_image_size"]), ("crop", "match"))
        names = [item.id for item in self.nodes["NGH3Director"].GET_SCHEMA().inputs]
        # new inputs go last, so older workflows keep their saved widget order
        self.assertEqual(names[-10:], ["resize_method", "ref_image_size", "resume", "resume_delete_done", "control_strength", "control_start", "control_end",
                                       "models", "output", "spectrum"])

    def test_resume_is_on_by_default_and_can_be_switched_off(self):
        types = lambda result: {v["class_type"] for v in self.nodes["NGProjectRender"].execute(sequence=result).expand.values()}
        self.assertIn("NGResumeChunk", types(self.result()))
        self.assertNotIn("NGResumeChunk", types(self.result(resume=False)))

    def test_zero_size_director_plans_from_the_default_without_pictures(self):
        result = self.result(width=0, height=0)
        self.assertEqual((result.project.context.width, result.project.context.height), (1344, 768))


if __name__ == "__main__":
    unittest.main()
