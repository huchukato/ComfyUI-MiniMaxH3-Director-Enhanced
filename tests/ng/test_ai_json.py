"""Real AI parser boundaries: complete JSON, explanatory prose, malformed and ambiguous answers."""
import json
import unittest

from _pack import module

direction = module("ng.core.auto_direct")
builder = module("ng.core.builder")


def plan():
    return {"look": "Sunlit station", "shots": [{"start_s": 0, "end_s": 8,
            "action": 'Alice examines a sign saying {departures} and "Welcome".', "lines": []}],
            "soundscape": "Soft room tone.", "music": "N/A"}


PARSERS = {"split": lambda text: direction.parse_direction(text, 8), "build": builder.read_answer}


class ResponseEdges(unittest.TestCase):
    def assert_parses(self, text):
        for name, parse in PARSERS.items():
            with self.subTest(parser=name):
                self.assertIn("shots", parse(text))

    def assert_bad(self, text, truncated=False):
        for name, parse in PARSERS.items():
            with self.subTest(parser=name, text=text[-80:]):
                try:
                    parse(text)
                except ValueError as error:
                    if truncated:
                        self.assertIn("Raise Max tokens", str(error))
                    else:
                        self.assertNotIn("Raise Max tokens", str(error), "Malformed/ambiguous JSON is not a token cutoff")
                else:
                    self.fail("An invalid or ambiguous root object must be refused")

    def test_clean_object_with_braces_and_escaped_quotes_inside_strings(self):
        self.assert_parses(json.dumps(plan()))

    def test_trailing_prose_after_complete_object(self):
        self.assert_parses(json.dumps(plan()) + "\nI hope this plan helps!")

    def test_leading_prose_before_complete_object(self):
        self.assert_parses("Here is your plan:\n" + json.dumps(plan()))

    def test_json_fence_with_trailing_prose(self):
        self.assert_parses("```json\n" + json.dumps(plan()) + "\n```\nEnjoy your project!")

    def test_prose_before_and_after_json_fence(self):
        self.assert_parses("Here is the requested plan:\n```json\n" + json.dumps(plan()) + "\n```\nEnjoy!")

    def test_plain_fence_without_language_tag(self):
        self.assert_parses("```\n" + json.dumps(plan()) + "\n```\nEnjoy!")

    def test_closing_fence_missing_but_complete_object_is_usable(self):
        self.assert_parses("```json\n" + json.dumps(plan()))

    def test_trailing_prose_with_non_json_braces_does_not_change_root(self):
        self.assert_parses(json.dumps(plan()) + "\nRemember {the notes} while filming.")

    def test_two_complete_objects_remain_ambiguous(self):
        self.assert_bad(json.dumps(plan()) + "\n" + json.dumps(plan()))

    def test_two_fenced_objects_remain_ambiguous(self):
        self.assert_bad("```json\n" + json.dumps(plan()) + "\n```\n```json\n" + json.dumps(plan()) + "\n```")

    def test_top_level_array_does_not_become_the_nested_first_object(self):
        self.assert_bad(json.dumps([plan()]))
        self.assert_bad("```json\n" + json.dumps([plan()]) + "\n```")

    def test_truly_cutoff_root_and_string_still_get_token_hint(self):
        raw = json.dumps(plan())
        self.assert_bad(raw[:-1], truncated=True)
        self.assert_bad(raw[:raw.index("Alice") + 3], truncated=True)
        self.assert_bad("```json\n" + raw[:-1], truncated=True)

    def test_closed_malformed_object_has_no_token_hint(self):
        self.assert_bad('{"shots": INVALID}')
        self.assert_bad('{"shots": [} ')

    def test_invalid_unclosed_object_has_no_token_hint(self):
        self.assert_bad('{"shots": INVALID')
        self.assert_bad('{not JSON')

    def test_non_json_prose_has_no_token_hint(self):
        self.assert_bad("I cannot provide a plan.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
