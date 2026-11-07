"""R3: what the three assistance modes allow, which fields an Apply writes, and what Analyze All covers."""
import unittest

from _pack import module

analysis = module("ng.core.analysis")
assist = module("ng.core.assist")


class Modes(unittest.TestCase):
    def test_every_mode_is_persisted_with_its_version(self):
        for mode in assist.MODES:
            state = assist.AssistState(mode=mode, provider=True)
            self.assertEqual(assist.AssistState.from_dict(state.to_dict()), state)
        self.assertNotIn("auto_apply", assist.AssistState().to_dict(), "only the mode is saved")
        for change in ({"mode": "silent"}, {"schema_version": 2}, {"provider": "yes"}, {"auto_apply": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                assist.AssistState.from_dict({"schema_version": 1, **change})

    def test_auto_direct_needs_auto_and_a_provider(self):
        off = assist.AssistState(mode="manual", provider=True)
        auto = assist.AssistState(mode="auto", provider=True)
        self.assertFalse(off.can_auto_direct, "Manual must never start a scene proposal")
        self.assertFalse(assist.AssistState(mode="auto", provider=False).can_auto_direct)
        self.assertTrue(auto.can_auto_direct)
        self.assertFalse(assist.AssistState(mode="auto", provider=True, busy=True).can_auto_direct)
        self.assertTrue(off.can_analyze and auto.can_analyze, "analysis stays an explicit action in every mode")
        self.assertFalse(assist.AssistState(provider=False).can_analyze)

    def test_status_names_what_the_mode_does(self):
        self.assertIn("connect h3 ai loader", assist.AssistState().status().lower())
        self.assertIn("Working", assist.AssistState(provider=True, busy=True).status())
        for mode in assist.MODES:
            self.assertTrue(assist.AssistState(mode=mode, provider=True).status())


class FieldSelection(unittest.TestCase):
    def suggestion(self, **changes):
        return analysis.AnalysisSuggestion(**{"description": "A woman in a red coat.", "content": "character", **changes})

    def test_only_selected_fields_are_written(self):
        changes, notes = assist.field_changes(self.suggestion(), ["description"], "image")
        self.assertEqual(changes, {"description": "A woman in a red coat."})
        self.assertEqual(notes, [], "fields that were simply not selected are not warnings")

    def test_roles_are_written_with_their_role_list(self):
        changes, _ = assist.field_changes(self.suggestion(), ["content", "usage"], "image")
        self.assertEqual(changes["content"], "character")
        self.assertEqual(changes["content_roles"], '["character"]')

    def test_a_role_the_medium_does_not_offer_is_kept_and_reported(self):
        # voice is a content kind but not an image role for usage, so it must not be mapped to something else.
        suggestion = self.suggestion(usage="voice")
        changes, notes = assist.field_changes(suggestion, ["usage"], "image")
        self.assertEqual(changes, {}, "an unsupported role must not overwrite the card")
        self.assertIn("is not a usage role for image", notes[0])

    def test_the_reason_is_shown_but_never_written_as_a_field(self):
        # `why` explains the suggestion to the user; it is not a widget, so Apply must refuse it.
        with self.assertRaisesRegex(ValueError, "why"):
            assist.field_changes(self.suggestion(why="she wears a red coat"), ["why"], "image")
        for selected in ("description", ["color"], [1]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                assist.field_changes(self.suggestion(), selected, "image")


class AnalyzeAll(unittest.TestCase):
    def contexts(self):
        return [{"media": "image", "widgets": {"name": "Alice", "image": "alice.png"}},
                {"media": "audio", "widgets": {"name": "Voice", "audio": "voice.wav", "analyzed": True}},
                {"media": "text", "widgets": {"name": "Rules", "text": "  "}},
                {"media": "image", "widgets": {"name": "Station", "image": ""}}]

    def test_only_usable_cards_are_analyzed_and_the_rest_are_named(self):
        targets, skipped = assist.batch_plan(self.contexts(), "assist", True)
        self.assertEqual(targets, [0])
        self.assertEqual(len(skipped), 3)
        self.assertTrue(any("already analyzed" in reason for reason in skipped))
        self.assertTrue(any("text is empty" in reason for reason in skipped))
        self.assertTrue(any("no file chosen" in reason for reason in skipped))

    def test_manual_mode_sends_nothing_and_a_missing_provider_says_so(self):
        targets, skipped = assist.batch_plan(self.contexts(), "manual", True)
        self.assertEqual(targets, [])
        self.assertIn("Manual", skipped[0])
        self.assertIn("Connect H3 AI Loader", assist.batch_plan(self.contexts(), "assist", False)[1][0])
        with self.assertRaisesRegex(ValueError, "Manual, Assist or Auto"):
            assist.batch_plan(self.contexts(), "silent", True)

    def test_an_unsupported_medium_is_skipped_instead_of_sent(self):
        entries = [{"media": "text", "widgets": {"text": "Rules"}}, {"media": "hologram", "widgets": {}}]
        targets, skipped = assist.batch_plan(entries, "auto", True)
        self.assertEqual(targets, [0])
        self.assertIn("no supported medium", skipped[0])


if __name__ == "__main__":
    unittest.main()