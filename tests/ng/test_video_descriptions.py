"""Narrative video descriptions reach H3 within shot scope; control source notes stay on the card."""
import json
import unittest

from _pack import module

ctx = module("ng.core.context")
project = module("ng.core.project")
chunks = module("ng.core.chunks")


class VideoDescriptions(unittest.TestCase):
    def item(self, role):
        return ctx.ContextItem("video", "Walk", "video", "source.mp4", usage=(role,),
                               description="A red-coated woman walks clockwise beside a blue wall.")

    def jobs(self, item, shots=""):
        context = ctx.DirectorContext(idea="A woman walks.", items=(item,), project_seconds=10.33, shots_text=shots)
        return project.jobs(project.plan_project(context, 5.167, chunks.ContinuityPlan("video_audio", 22, 24)))

    def test_description_is_sent_once_for_narrative_roles_and_never_for_control(self):
        for role in ctx.USAGE_BY_MEDIA["video"]:
            item = self.item(role)
            with self.subTest(role=role):
                self.assertEqual(self.jobs(item)[0].compiled.prompt.count(item.description), 0 if role == "control" else 1)

    def test_bound_description_leaves_parts_where_the_card_is_out_of_scope(self):
        shots = json.dumps(dict(format="h3-director-shots", schema_version=1, shots=[
            dict(id="first", start=0, end=2, text="Walk.", media=[dict(schema_version=1, context_id="video", role="context")]),
            dict(id="later", start=2, end=10.33, text="A quiet garden.", media=[])]))
        item = self.item("motion")
        jobs = self.jobs(item, shots)
        self.assertIn(item.description, jobs[0].compiled.prompt)
        self.assertNotIn(item.description, jobs[1].compiled.prompt)


if __name__ == "__main__":
    unittest.main()
