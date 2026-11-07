r"""BUG-052: Make H3 prompt builder.kinds classifies all independent character cards as views of the last card when context_id is empty.

When a user adds character cards in ComfyUI, widget context_id defaults to empty ("").
In ng/core/builder.py:
- kinds builds:
    names = {entry["widgets"].get("context_id"): entry["widgets"].get("name") for entry in contexts}
  When cards have context_id == "", names contains {"": <last_card_name>}.
- kinds then parses subject_ids:
    owners = [names.get(i) for i in re.split(r"[\s,\[\]\"]+", widgets.get("subject_ids") or "") if names.get(i)]
  When subject_ids is empty ("" or None), re.split(...) returns [''].
  Because names.get("") evaluates to the last card's name, owners becomes [<last_card_name>] for EVERY card!
- As a consequence:
    kind = ("frame" if set(usage) & set(FRAMES) else "view" if owners else ...)
  evaluates to "view" for every single character card without subject_ids!
- The prompt sent to the AI then describes independent characters as:
    1. "Warrior" - another view of @Mage
    2. "Mage" - another view of @Mage
  instead of "@Warrior - a character" and "@Mage - a character", completely breaking character recognition,
  dialogue attribution, and prompt generation.
- In addition, an asset card with subject_ids pointing to a character by fallback ID (e.g. ["image_warrior"])
  fails to find the character because names was not keyed by fallback ID.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

builder = module("ng.core.builder")


class BuilderKindsEmptyContextId(unittest.TestCase):
    def test_bug_052_independent_characters_must_be_figures_when_context_id_is_empty(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Warrior",
                    "image": "warrior.png",
                    "description": "A battle-hardened warrior",
                    "context_id": "",  # standard default for newly added cards
                    "content_roles": "character",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            },
            {
                "media": "image",
                "widgets": {
                    "name": "Mage",
                    "image": "mage.png",
                    "description": "A robed spellcaster",
                    "context_id": "",  # standard default
                    "content_roles": "character",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            },
        ]

        sorts = builder.kinds(contexts)

        self.assertEqual(
            sorts.get("Warrior", ("", ""))[0],
            "figure",
            "Warrior must be classified as a figure, not a view of another card",
        )
        self.assertEqual(
            sorts.get("Mage", ("", ""))[0],
            "figure",
            "Mage must be classified as a figure, not a view of another card",
        )

    def test_bug_052_plan_prompt_must_declare_characters_as_figures_when_context_id_is_empty(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Warrior",
                    "image": "warrior.png",
                    "description": "A battle-hardened warrior",
                    "context_id": "",
                    "content_roles": "character",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            },
            {
                "media": "image",
                "widgets": {
                    "name": "Mage",
                    "image": "mage.png",
                    "description": "A robed spellcaster",
                    "context_id": "",
                    "content_roles": "character",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            },
        ]

        prompt = builder.plan_prompt(builder.DEFAULT_QUICK, "A fantasy battle", 10.0, contexts, 2)

        self.assertIn(
            "@Warrior - a character",
            prompt,
            "plan_prompt must list Warrior as an independent character (@Warrior - a character)",
        )
        self.assertIn(
            "@Mage - a character",
            prompt,
            "plan_prompt must list Mage as an independent character (@Mage - a character)",
        )
        self.assertNotIn(
            'another view of @Mage',
            prompt,
            "Warrior must not be collapsed into 'another view of @Mage'",
        )

    def test_bug_052_asset_with_fallback_subject_id_resolves_owner(self):
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Warrior",
                    "image": "warrior.png",
                    "description": "A battle-hardened warrior",
                    "context_id": "",  # fallback id: image_warrior
                    "content_roles": "character",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            },
            {
                "media": "image",
                "widgets": {
                    "name": "Warrior Sword",
                    "image": "sword.png",
                    "description": "The warrior's runic sword",
                    "context_id": "",
                    "content_roles": "object",
                    "usage_roles": "reference",
                    "subject_ids": '["image_warrior"]',  # assigned via Belongs to in UI
                },
            },
        ]

        sorts = builder.kinds(contexts)

        self.assertEqual(
            sorts.get("Warrior", ("", ""))[0],
            "figure",
            "Warrior must be a figure",
        )
        self.assertEqual(
            sorts.get("Warrior Sword"),
            ("view", "Warrior"),
            "Warrior Sword must be resolved as a view of Warrior",
        )

    def test_control_explicit_context_ids_classify_figures_correctly(self):
        """Green control test: When context_id is explicitly set, characters are classified as figures."""
        contexts = [
            {
                "media": "image",
                "widgets": {
                    "name": "Warrior",
                    "image": "warrior.png",
                    "description": "A battle-hardened warrior",
                    "context_id": "image_warrior",
                    "content_roles": "character",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            },
            {
                "media": "image",
                "widgets": {
                    "name": "Mage",
                    "image": "mage.png",
                    "description": "A robed spellcaster",
                    "context_id": "image_mage",
                    "content_roles": "character",
                    "usage_roles": "reference",
                    "subject_ids": "",
                },
            },
        ]

        sorts = builder.kinds(contexts)

        self.assertEqual(sorts.get("Warrior"), ("figure", ""))
        self.assertEqual(sorts.get("Mage"), ("figure", ""))


if __name__ == "__main__":
    unittest.main()
