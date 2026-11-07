"""BUG-045: an answer in the shape the analysis prompt itself asks for is thrown away.

analysis_prompt() lists the roles it accepts as pairs, "role = what it means":

    usage (exactly one of: reference = keep this figure or thing recognizable;
           first_frame = the opening picture; …)

Measured against local Ollama with exactly that prompt and the offer the card sends,
the model answers by copying one pair verbatim:

    {"description": "A steampunk-style female warrior …",
     "content": "character",
     "usage": "reference = keep this figure or thing recognizable", "why": "…"}

That is the role the user asked for, spelled the way the product spelled it to them.
parse_suggestion() has two repairs for small-model shapes - an answer split into a
list of stills, and a role written as a key instead of a value - and neither covers
this one, so the half-parsed string travels on. h3c_model.usableFields() then finds
no role in it and drops it, and the suggestion box shows only Description and
Content: the "Use as" line the panel promises never appears and Accept cannot write
the role.

Measured end to end: `card keeps ['content', 'description']` for the pair-shaped
answer against `['description', 'usage']` for the same answer with "reference" alone.

The test calls the real parse_suggestion() and asserts that a value naming one of the
card's own roles comes back as that bare role.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

analysis = module("ng.core.analysis")

OFFER = {"content": ["character", "face", "outfit", "pose", "environment", "style"],
         "usage": ["reference", "first_frame", "last_frame", "keyframe", "storyboard"]}


def parse(payload, media="image"):
    return analysis.parse_suggestion(json.dumps(payload), media).to_dict()


class UsageRoleFromThePrompt(unittest.TestCase):
    def test_bug_045_the_prompt_prints_the_roles_as_pairs(self):
        # Precondition: the separator the answer copies is the product's own.
        prompt = analysis.analysis_prompt("image", "character", OFFER)
        self.assertIn("reference = keep this figure or thing recognizable", prompt,
                      "the prompt must print roles in the shape this bug is about")

    def test_bug_045_a_role_spelled_as_a_pair_must_come_back_as_the_bare_role(self):
        # The measured answer from local Ollama, unchanged.
        answer = {"description": "A steampunk-style female warrior with gauntlets.",
                  "content": "character",
                  "usage": "reference = keep this figure or thing recognizable",
                  "why": "A clear visual anchor."}
        self.assertEqual(parse(answer)["usage"], "reference",
                         "the role the model chose never becomes a usable role")

    def test_bug_045_every_offered_role_survives_in_pair_form(self):
        for role in OFFER["usage"]:
            meaning = analysis.USAGE_MEANING["image"][role]
            answer = {"description": "A figure.", "usage": "%s = %s" % (role, meaning)}
            self.assertEqual(parse(answer)["usage"], role, role)

    def test_control_a_bare_role_is_untouched(self):
        self.assertEqual(parse({"description": "A figure.", "usage": "reference"})["usage"],
                         "reference")

    def test_control_the_keyed_shape_is_still_repaired(self):
        # The sibling repair that already exists must keep working.
        self.assertEqual(parse({"constraint": "No on-screen text"}, media="text")["usage"],
                         "constraint")

    def test_control_a_value_naming_no_role_is_left_for_the_card_to_drop(self):
        # A genuine free-text answer keeps its existing behaviour: passed on, dropped by the card.
        self.assertEqual(parse({"description": "A figure.", "usage": "whatever"})["usage"],
                         "whatever")


if __name__ == "__main__":
    unittest.main()