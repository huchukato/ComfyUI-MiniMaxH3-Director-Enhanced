import unittest

from _pack import module

shots = module("ng.core.shots")


class Parse(unittest.TestCase):
    def test_basic_formats(self):
        got, issues = shots.parse_shots("0-8: Alice enters.\n8-22.5 She finds the robot.\n0:22.5-0:38: She examines it.", 38 * 24)
        self.assertEqual([(s.start_f, s.end_f) for s in got], [(0, 192), (192, 540), (540, 912)])
        self.assertEqual(got[1].text, "She finds the robot.")
        self.assertEqual(issues, ())

    def test_continuation_lines_belong_to_the_shot(self):
        got, _ = shots.parse_shots("0-4: She talks.\n@ref1 says: Hello?\nmore text\n4-8: End.", 8 * 24)
        self.assertEqual(got[0].text, "She talks.\n@ref1 says: Hello?\nmore text")
        self.assertEqual(got[1].text, "End.")

    def test_seconds_suffix_and_dash_variants(self):
        got, _ = shots.parse_shots("0s – 3s: a\n3s to 6s: b", 6 * 24)
        self.assertEqual([(s.start_f, s.end_f) for s in got], [(0, 72), (72, 144)])

    def test_unsorted_input_is_sorted(self):
        got, _ = shots.parse_shots("5-8: b\n0-5: a", 8 * 24)
        self.assertEqual([s.text for s in got], ["a", "b"])
        self.assertEqual([s.index for s in got], [1, 2])

    def test_corrections_are_reported(self):
        got, issues = shots.parse_shots("intro line\n0-6: a\n4-8: b\n9-12: c\n20-30: far away", 12 * 24)
        codes = [i.code for i in issues]
        self.assertEqual(codes.count("shots_preamble"), 1)
        self.assertIn("shot_overlap", codes)
        self.assertIn("shot_gap", codes)
        self.assertIn("shot_after_end", codes)
        self.assertEqual([(s.start_f, s.end_f) for s in got], [(0, 144), (144, 192), (216, 288)])

    def test_clipped_at_project_end_and_empty_range(self):
        got, issues = shots.parse_shots("0-20: long\n5-5: nothing", 10 * 24)
        self.assertEqual(got[0].end_f, 240)
        self.assertEqual({i.code for i in issues}, {"shot_clipped", "shot_empty_range"})

    def test_empty_text_gives_no_shots(self):
        self.assertEqual(shots.parse_shots("", 240), ((), ()))

    def test_auto_shots(self):
        self.assertEqual(shots.auto_shots("a walk", 240), (shots.Shot(1, 0, 240, "a walk"),))
        self.assertEqual(shots.auto_shots("  ", 240), ())


if __name__ == "__main__":
    unittest.main()
