"""Pictures of one figure that are left as separate Subjects are flagged (Ref2VA minute 2026-10-20: three views of one elf
were three Subjects, and H3 switched between them)."""
import unittest

from _pack import module

ctx, checks = module("ng.core.context"), module("ng.core.context_checks")


def card(cid, name, description, **kw):
    return ctx.ContextItem(cid, name, "image", cid + ".png", usage=("reference",), content=("character",), description=description, **kw)


ELF = "A female elf with long white hair, golden eyes and pointed ears, a black off-shoulder dress and an ornate staff with glowing gems."
SIDE = "An elf-like character with long white hair, pointed ears, golden eyes and a black off-shoulder dress holding an ornate staff."
MAN = "An old fisherman with a grey beard, a yellow raincoat and rubber boots, holding a net."


def codes(*items):
    return [(i.code, i.ref) for i in checks.check_context(ctx.DirectorContext(items=items, project_seconds=10)) if i.code == "subject_look_alike"]


class LookAlike(unittest.TestCase):
    def test_two_views_of_one_figure_are_flagged_once_each(self):
        self.assertEqual(codes(card("a", "Mage", ELF), card("b", "Profile", SIDE), card("c", "Back", SIDE)),
                         [("subject_look_alike", "Profile"), ("subject_look_alike", "Back")])

    def test_different_figures_and_linked_views_are_not(self):
        self.assertEqual(codes(card("a", "Mage", ELF), card("m", "Fisher", MAN)), [])
        self.assertEqual(codes(card("a", "Mage", ELF), card("b", "Profile", SIDE, subject_ids=("a",))), [])


if __name__ == "__main__":
    unittest.main()
