"""BUG-046: In FL2VA mode, the prompt rule instructs the model to use <Picture 1>, but check() refuses it as an unknown label.

When a user in FL2VA mode has a First Frame image card connected and uses "Write with AI"
to elaborate a render part's prompt, part_prompt._extra_rules() instructs the model:

    "<Picture 1> is the first frame: begin with what it shows and develop forward from it."

When the model obeys this instruction and refers to <Picture 1> in its description,
check() validates:

    if not set(LABEL_RE.findall(written)) <= set(LABEL_RE.findall(compiled)):
        problems.append("it uses labels the plan does not have: %s" % ...)

In FL2VA mode, the compiled prompt header uses unbracketed notation ("Picture 1 ... aligns with ..."),
so LABEL_RE.findall(compiled) contains no "<Picture 1>".
As a result, check() rejects the AI prompt with:
    "it uses labels the plan does not have: <Picture 1>"
and discards the generated prompt completely.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

part_prompt = module("ng.core.part_prompt")


class FL2VAPictureLabelCheck(unittest.TestCase):
    def test_bug_046_fl2va_picture_label_must_not_be_refused_by_check(self):
        compiled = (
            "How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video.\n\n"
            "detailed_description:\n"
            "[Shot 1] At 00:00.000 A woman stands in the hall. "
            "[Shot 2] At 00:02.000 She turns away."
        )

        # The prompt generator produces this rule for the model:
        req = part_prompt.request(compiled, mode="fl2va", seconds=5.0)
        self.assertTrue(
            any("<Picture 1>" in line for line in req.splitlines()),
            "precondition: part_prompt.request must tell the model to use <Picture 1>",
        )

        # The model follows instructions and refers to <Picture 1>:
        answer = (
            "description: [Shot 1] At 00:00.000 A woman in an elegant dark dress stands in the center of the grand stone hall. "
            "<Picture 1> is the first frame: soft golden sunlight streams through the arched windows, illuminating the dust motes in the air. "
            "[Shot 2] At 00:02.000 She turns away gracefully, walking towards the heavy iron gates as the camera slowly pushes in."
        )

        text, problems = part_prompt.check(compiled, answer)
        self.assertNotIn(
            "it uses labels the plan does not have: <Picture 1>",
            problems,
            "check() must not reject <Picture 1> when the prompt rules instructed the model to use it",
        )
        self.assertIsNotNone(text, "the valid prompt elaboration must be accepted")

    def test_control_ref2va_bracketed_labels_are_accepted(self):
        compiled = (
            "subject_definitions:\n"
            "<Subject 1> is the woman in <Picture 1>.\n\n"
            "summary: [reference generation] A scene in the hall.\n\n"
            "detailed_description:\n"
            "[Shot 1] At 00:00.000 <Subject 1> stands in the hall. "
            "[Shot 2] At 00:02.000 <Subject 1> turns away."
        )
        answer = (
            "summary: A scene in the hall.\n"
            "description: [Shot 1] At 00:00.000 <Subject 1> stands in the center of the hall, looking through the various <Picture 1> references. "
            "Warm amber light fills the ancient stone corridor from the flickering candles hanging along the wall. "
            "[Shot 2] At 00:02.000 <Subject 1> turns away slowly and departs silently into the shadows as the camera tracks backward."
        )
        text, problems = part_prompt.check(compiled, answer)
        self.assertEqual(problems, [])
        self.assertIsNotNone(text)

    def test_control_unplanned_labels_are_still_refused(self):
        compiled = (
            "detailed_description:\n"
            "[Shot 1] At 00:00.000 A woman stands in the hall. "
            "[Shot 2] At 00:02.000 She turns away."
        )
        answer = (
            "description: [Shot 1] At 00:00.000 <Subject 99> stands in the hall with dramatic posture. "
            "The ancient stone walls are covered with ivy and mysterious glowing runes. "
            "[Shot 2] At 00:02.000 The mysterious figure turns away into the shadows."
        )
        text, problems = part_prompt.check(compiled, answer)
        self.assertIn("it uses labels the plan does not have: <Subject 99>", problems)
        self.assertIsNone(text)


if __name__ == "__main__":
    unittest.main()
