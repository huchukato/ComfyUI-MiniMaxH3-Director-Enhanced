"""BUG-028: Text-Context mit subject_ids darf compile_chunk nicht mit ValueError oder AttributeError crashen.

In ng/core/asset_prompt.py:
1. Zeile 39: mapping.slot_items.index(identity) wirft ValueError, wenn die Figur nicht in
   mapping.slot_items liegt (z. B. im FL2VA-Modus oder bei Frame-Rollen wie first_frame).
2. Zeile 63: context.item(identity).name wirft AttributeError, wenn identity nicht in
   context.items existiert (z. B. geloeschte/getrennte Context-Karte).

Kein Fix, nur roter Regressionstest.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import module  # noqa: E402

context_mod = module("ng.core.context")
compile_mod = module("ng.core.compile")
chunks_mod = module("ng.core.chunks")
asset_prompt = module("ng.core.asset_prompt")
legacy_bridge = module("ng.core.legacy_bridge")


class ScopedTextCrash(unittest.TestCase):
    def test_bug_028_scoped_text_in_fl2va_must_not_crash_compiler(self):
        """In FL2VA hat die Bildkarte keine Reference-Rolle; mapping.slot_items ist leer.
        _scope_text darf nicht mapping.slot_items.index(identity) aufrufen und crashen.
        """
        img = context_mod.ContextItem("img1", "Alice", "image", "alice.png",
                                     usage=("first_frame",), description="Alice")
        txt = context_mod.ContextItem("t1", "Notes", "text", "Stay calm.",
                                     usage=("rule",), subject_ids=("img1",))
        ctx = context_mod.DirectorContext(idea="x", project_seconds=5.0,
                                          items=(img, txt), mode="fl2va")
        chunk = chunks_mod.Chunk(0, 0, 80, 0, (), is_last=True)
        continuity = chunks_mod.ContinuityPlan("none", 22, 16)
        try:
            compiled = compile_mod.compile_chunk(ctx, chunk, continuity)
            self.assertIsNotNone(compiled)
        except ValueError as err:
            self.fail("compile_chunk crashed with ValueError: %s" % err)

    def test_bug_028_missing_subject_id_must_not_raise_attribute_error(self):
        """Ein verwaistes subject_id darf bei apply_asset_relations nicht mit
        AttributeError ('NoneType' has no attribute 'name') abstuerzen.
        """
        item = context_mod.ContextItem("t1", "Notes", "text", "abc", subject_ids=("ghost",))
        ctx = context_mod.DirectorContext(items=(item,))
        mapping = legacy_bridge.Mapping([], {})
        result = {"prompt": "Context guidance:", "ref_image_slots": [], "subject_of_slot": {}}
        try:
            prompt, issues = asset_prompt.apply_asset_relations(result, mapping, ctx, [])
            self.assertIsNotNone(prompt)
        except AttributeError as err:
            self.fail("apply_asset_relations crashed with AttributeError: %s" % err)


if __name__ == "__main__":
    unittest.main()
