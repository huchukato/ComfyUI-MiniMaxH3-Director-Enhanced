"""BUG-046 verification using the real planner, writer brief, and answer checker.

No files are read as media and no provider/server is called. ``probe`` supplies
the deterministic image size-independent duration used by the planner.
The paired-frame failure is reachable through the writer's named attachments;
the old reported first-only header is not what the current compiler generates.
"""
import sys
import unittest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _pack import module

preview = module("ng.core.preview")
writer = module("ng.core.part_writer")
part = module("ng.core.part_prompt")

DIRECTOR = {"idea": "A woman walks through a grand stone hall.",
            "project_seconds": 5, "mode": "fl2va", "continuity": "none"}
PROSE = (" Soft golden sunlight crosses the ancient stone walls and catches the woman's dark dress and long flowing hair."
         " She takes measured steps along the marble floor while the camera tracks smoothly beside her,"
         " bringing the arched windows and delicate dust motes into view as her expression changes from curiosity to calm.")


def fixture(*roles):
    contexts = [{"media": "image", "widgets": {"context_id": role, "name": role,
                "image": role + ".png", "usage": role}} for role in roles]
    chunk = preview.plan_preview({"director": DIRECTOR, "contexts": contexts},
                                 probe=lambda _: 1)["chunks"][0]
    facts = writer.brief(DIRECTOR, contexts, 0, probe=lambda _: 1)
    # The HTTP vision adapter supplies this after loading these exact pictures.
    # No picture data is needed to verify the prompt/checker contract.
    facts["shown"] = facts["pictures"]
    head, sections = part.split_sections(facts["compiled"])
    body = sections[part._body_name(sections)]
    return chunk, facts, head, body


def answer(body, *labels):
    return "description: " + body + PROSE + " " + " ".join(
        "The woman is shown in %s." % label for label in labels)


class FL2VARealPlan(unittest.TestCase):
    def test_manual_header_prose_does_not_invent_a_native_picture(self):
        _, facts, _, body = fixture()
        compiled = "A painting called Picture 3 stands on the wall.\n\n" + facts["compiled"]
        _, problems = part.check(compiled, answer(body, "<Picture 3>"))
        self.assertTrue(any("labels the plan does not have: <Picture 3>" in issue for issue in problems))

    def test_paired_anchor_request_and_checker_offer_the_same_labels(self):
        _, facts, _, _ = fixture("first_frame", "last_frame")
        prompt = writer.write_prompt(facts)
        self.assertIn("Use only these labels: <Picture 1>, <Picture 2>", prompt)
        self.assertNotIn("Use no <...> labels", prompt)

    def test_paired_anchors_have_real_bracketed_labels_and_unbracketed_header(self):
        chunk, facts, head, body = fixture("first_frame", "last_frame")
        self.assertEqual(chunk["prompt_labels"],
                         {"<Picture 1>": "first_frame", "<Picture 2>": "last_frame"})
        self.assertIn("Picture 1 (from Shot 1)", head)
        self.assertNotIn("<Picture 1>", head)
        self.assertIn("The attached pictures are, in order: <Picture 1>, <Picture 2>",
                      writer.write_prompt(facts))
        result = writer.finish(answer(body, "<Picture 1>", "<Picture 2>"), facts)
        self.assertEqual(result["problems"], [], result)
        self.assertTrue(result["text"])

    def test_control_brief_pictures_follow_the_actual_native_prompt_labels(self):
        chunk, facts, _, _ = fixture("first_frame", "last_frame")
        self.assertEqual(dict(facts["pictures"]), chunk["prompt_labels"])

    def test_direct_check_accepts_real_paired_anchor_labels_without_a_new_argument(self):
        _, facts, _, body = fixture("first_frame", "last_frame")
        text, problems = part.check(facts["compiled"], answer(body, "<Picture 1>", "<Picture 2>"))
        self.assertEqual(problems, [])
        self.assertTrue(text)

    def test_control_first_only_header_is_bracketed_and_label_is_already_accepted(self):
        _, facts, head, body = fixture("first_frame")
        self.assertIn("<Picture 1>", head)
        self.assertIn("fully referenced", head)
        self.assertEqual(writer.finish(answer(body, "<Picture 1>"), facts)["problems"], [])

    def test_control_last_only_header_is_bracketed_and_label_is_already_accepted(self):
        _, facts, head, body = fixture("last_frame")
        self.assertIn("<Picture 1>", head)
        self.assertIn("aligns with", head)
        self.assertEqual(writer.finish(answer(body, "<Picture 1>"), facts)["problems"], [])

    def test_control_no_refs_does_not_allow_picture_1(self):
        chunk, facts, head, body = fixture()
        self.assertEqual(chunk["prompt_labels"], {})
        self.assertEqual(head, "")
        result = writer.finish(answer(body, "<Picture 1>"), facts)
        self.assertIn("it uses labels the plan does not have: <Picture 1>", result["problems"])
        self.assertEqual(result["text"], "")

    def test_control_two_native_pictures_do_not_allow_picture_3(self):
        _, facts, _, body = fixture("first_frame", "last_frame")
        result = writer.finish(answer(body, "<Picture 3>"), facts)
        self.assertIn("it uses labels the plan does not have: <Picture 3>", result["problems"])
        self.assertEqual(result["text"], "")

    def test_control_picture_named_in_body_prose_does_not_become_an_allowed_label(self):
        _, facts, _, body = fixture()
        compiled = facts["compiled"].replace("stone hall.", "stone hall with a painting called Picture 3.")
        text, problems = part.check(compiled, answer(body, "<Picture 3>"))
        self.assertIn("it uses labels the plan does not have: <Picture 3>", problems)
        self.assertIsNone(text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class EndPoseRule(unittest.TestCase):
    """Measured 2026-10-11: with the end pose in the text, 4-step H3 approached the last frame evenly instead of morphing
    into it in the last 4 frames. The AI writers must be told to name it (base-en 3.2: describe the path between frames)."""

    def test_part_writer_asks_for_the_final_pose_of_the_last_frame(self):
        part_prompt = module("ng.core.part_prompt")
        both = " ".join(part_prompt._extra_rules("<Picture 1> ... <Picture 2>", False, "", []))
        self.assertIn("final pose", both)
        last = " ".join(part_prompt._extra_rules("<Picture 1> aligns with the 10.08-second mark", False, "", []))
        self.assertIn("final pose", last)

    def test_make_h3_prompt_asks_for_the_final_pose(self):
        builder = module("ng.core.builder")
        found = [({"widgets": {"name": "Start"}}, ("first_frame",), ()), ({"widgets": {"name": "End"}}, ("last_frame",), ())]
        self.assertIn("final pose", builder._frame_rule(found))
        self.assertIn("final pose", builder._frame_rule(found[1:]))
