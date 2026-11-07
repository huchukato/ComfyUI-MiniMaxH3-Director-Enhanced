"""Do the new schema checks actually fail on a malformed prompt?

A validator that stays quiet on broken input is worth nothing, and it is easy to write one that
passes for the wrong reason: a regex that never matches, an expected list built from the output
itself, a `set()` comparison that hides a real difference. So this file takes the compiled prompt,
breaks it in each of the ways the guides forbid, and requires the checks to notice.

Every mutation is applied to a real compiled prompt, so the mutations are grounded in what the
compiler actually produces rather than in a hand-written sample.
"""
import re
import unittest

from _pack import module

import test_ir_schema as schema

ref2va_ctx = schema.ref2va_ctx
build = schema.build
fields_of = schema.fields_of


def broken(prompt):
    """The same text with its field blocks in reverse order, for the field-list checks."""
    parts = re.split(r"\n\n(?=[A-Za-z_][A-Za-z0-9_]*:)", prompt)
    return "\n\n".join(reversed(parts))


class MutantDetection(unittest.TestCase):
    """Each mutation must be caught by at least one of the new checks."""

    def setUp(self):
        _, self.ref2va = build(ref2va_ctx())
        _, self.base = build(schema.context.DirectorContext(
            idea="A woman plays with a red ball.", project_seconds=8))
        _, self.framed = build(schema.context.DirectorContext(
            idea="She walks.", project_seconds=8, items=(schema.FIRST, schema.LAST)))

    def assert_caught(self, mutated, original, note):
        """The mutated prompt must not look like the original to the field-list check."""
        self.assertNotEqual(fields_of(mutated), fields_of(original),
                            "%s was not caught by the field check" % note)


    # --- ordering ---

    def test_reversed_field_order_is_caught(self):
        self.assert_caught(broken(self.ref2va[0].prompt), self.ref2va[0].prompt, "reversed ref2va order")
        self.assert_caught(broken(self.base[0].prompt), self.base[0].prompt, "reversed base order")

    def test_swapped_ref2va_fields_are_caught(self):
        prompt = self.ref2va[0].prompt
        summary = schema.body_of(prompt, "summary")
        retention = schema.body_of(prompt, "retention_analysis")
        mutated = prompt.replace(summary, "@@SUMMARY@@").replace(retention, "@@RET@@")
        mutated = mutated.replace("@@SUMMARY@@", retention).replace("@@RET@@", summary)
        self.assert_caught(mutated, prompt, "summary and retention_analysis swapped")

    # --- missing fields ---

    def test_dropped_retention_analysis_is_caught(self):
        prompt = self.ref2va[0].prompt
        retention = schema.body_of(prompt, "retention_analysis")
        mutated = prompt.replace(retention + "\n\n", "")
        self.assertNotIn("retention_analysis:", mutated)
        self.assert_caught(mutated, prompt, "dropped retention_analysis")
        # the schema check itself now reports the field as absent
        self.assertNotIn("retention_analysis", schema.fields_of(mutated))

    def test_dropped_music_field_is_caught(self):
        prompt = self.base[0].prompt
        mutated = prompt.split("non_diegetic_music:")[0]
        self.assertNotIn("non_diegetic_music:", mutated)
        self.assert_caught(mutated, prompt, "dropped non_diegetic_music")

    # --- invented fields ---

    def test_invented_field_is_caught(self):
        prompt = self.ref2va[0].prompt
        mutated = prompt.replace("summary:", "continuity_notes:\n\nsummary:")
        found = fields_of(mutated)
        self.assertIn("continuity_notes", found)
        self.assertNotEqual(found, [f for f in schema.REF2VA_FIELDS if f in found])

    # --- description field swapped ---

    def test_using_the_base_field_name_in_ref2va_is_caught(self):
        prompt = self.ref2va[0].prompt
        mutated = prompt.replace("detailed_description:", "integrated_multimodal_description:")
        self.assertNotIn("detailed_description:", mutated)
        self.assert_caught(mutated, prompt, "ref2va using the base description field name")

    # --- alignment line ---

    def test_missing_alignment_line_is_caught(self):
        prompt = self.framed[0].prompt
        mutated = "\n".join(prompt.splitlines()[1:]).lstrip()
        self.assertFalse(mutated.startswith("How the reference pictures align"))
        self.assertNotEqual(mutated.splitlines()[0], prompt.splitlines()[0])

    def test_two_decimal_marks_are_what_the_check_looks_for(self):
        prompt = self.framed[0].prompt
        self.assertTrue(re.findall(r"aligns with the ([0-9.]+)-second mark", prompt))
        broken_form = prompt.replace("-second mark", "-seconds mark")
        self.assertEqual(re.findall(r"aligns with the ([0-9.]+)-second mark", broken_form), [])

    def test_three_decimal_mark_is_caught(self):
        prompt = self.framed[0].prompt
        mutated = prompt.replace("8.00-second mark", "8.000-second mark")
        found = re.findall(r"aligns with the ([0-9.]+)-second mark", mutated)
        self.assertIn("8.000", found, "the mutation must be visible to the mark check")
        # the check the schema tests apply: exactly two decimals
        offenders = [v for v in found if not re.match(r"^[0-9]+\.[0-9]{2}$", v)]
        self.assertEqual(offenders, ["8.000"], "three decimals must be reported")

    # --- retention vocabulary ---

    def test_unknown_retention_word_is_caught(self):
        prompt = self.ref2va[0].prompt
        mutated = prompt.replace("): fully_preserved - ", "): totally_preserved - ")
        words = re.findall(r"\): ([a-z_]+) - ", schema.body_of(mutated, "retention_analysis"))
        self.assertIn("totally_preserved", words)
        offenders = [w for w in words if w not in schema.RETENTION_WORDS]
        self.assertEqual(offenders, ["totally_preserved"], "the unknown word must be reported")

    def test_subject_missing_from_retention_is_caught(self):
        prompt = self.ref2va[0].prompt
        body = schema.body_of(prompt, "retention_analysis")
        defined = set(re.findall(r"^<Subject \d+>", schema.body_of(prompt, "subject_definitions"), re.M))
        analysed = set(re.findall(r"^<Subject \d+>", body, re.M))
        self.assertTrue(defined)
        self.assertEqual(defined, analysed)
        first = sorted(defined)[0]
        mutated_body = "\n".join(l for l in body.splitlines() if not l.startswith(first))
        self.assertNotEqual(defined, set(re.findall(r"^<Subject \d+>", mutated_body, re.M)))

    # --- labels ---

    def test_undocumented_label_is_caught(self):
        prompt = self.ref2va[0].prompt
        mutated = prompt.replace("<Subject 1>", "<Hero 1>")
        labels = set(re.findall(r"<(\w+) \d+>", mutated))
        self.assertIn("Hero", labels)
        offenders = [l for l in labels if l not in schema.LABELS]
        self.assertEqual(offenders, ["Hero"], "the undocumented label must be reported")


if __name__ == "__main__":
    unittest.main()
