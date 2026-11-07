"""BUG-069: batch_plan duplicates card label / media name in skip messages.

Where:
- ng/core/assist.py:110-120 (batch_plan)
- ng/adapters/analyze_all.py:17, 31 (analyze_all -> data.skipped)
- ng/nodes/analysis_routes.py:43-51 (/ng/analyze_all)
- js/ng/ng_assist.js:40-48 (summarizeBatch -> data.skipped)

Real workflow steps:
1. Connect context cards (e.g. image, audio, text) to the H3 Context Connector and H3 AI Loader.
2. In the AI Loader set Mode to 'Assist' or 'Auto'.
3. Some cards are not analyzable:
   - an audio card named 'Voice' has already been analyzed (analyzed: true),
   - a text card named 'Rules' has empty text (""),
   - an image card named 'Station' has no file chosen (""),
   - an unnamed image card has no file chosen.
4. Click 'Analyze All' in the AI Loader (POST /ng/analyze_all).

What happens (Ist):
In ng/core/assist.py, lines 111, 114, 117 already prepend the card name/media to the reason string:
  line 111: skipped.append((index, "%s: the text is empty" % (widgets.get("name") or "Text")))
  line 114: skipped.append((index, "%s: no file chosen" % (widgets.get("name") or media)))
  line 117: skipped.append((index, "%s: already analyzed" % (widgets.get("name") or media)))
Then, line 120 formats each tuple with _label(entries, index):
  return targets, ["%s: %s" % (_label(entries, index), reason) for index, reason in skipped]
Since _label also produces widgets.get("name") or media or "Context %d", the card name/media
is prepended TWICE:
  - 'Voice: Voice: already analyzed'
  - 'Rules: Rules: the text is empty'
  - 'Station: Station: no file chosen'
  - 'image: image: no file chosen'
  (unlike line 108 for unsupported media, which correctly appends "no supported medium"
   and formats once to 'hologram: no supported medium').
The user sees stuttered card names in the UI notification / skipped summaries.

What should happen (Soll):
Each skipped message should cleanly prefix the card label once:
  - 'Voice: already analyzed'
  - 'Rules: the text is empty'
  - 'Station: no file chosen'
  - 'image: no file chosen'
  - 'hologram: no supported medium'
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module  # noqa: E402

assist = module("ng.core.assist")


class BatchPlanDuplicateLabel(unittest.TestCase):
    def test_bug_069_batch_plan_does_not_duplicate_named_card_labels_in_skip_messages(self):
        """RED: Named cards must not repeat their name twice in skip messages."""
        contexts = [
            {"media": "image", "widgets": {"name": "Alice", "image": "alice.png"}},
            {"media": "audio", "widgets": {"name": "Voice", "audio": "voice.wav", "analyzed": True}},
            {"media": "text", "widgets": {"name": "Rules", "text": "  "}},
            {"media": "image", "widgets": {"name": "Station", "image": ""}},
        ]
        targets, skipped = assist.batch_plan(contexts, "assist", True)
        self.assertEqual(targets, [0])

        self.assertNotIn("Voice: Voice: already analyzed", skipped,
                         "Card name 'Voice' must not be stuttered twice")
        self.assertNotIn("Rules: Rules: the text is empty", skipped,
                         "Card name 'Rules' must not be stuttered twice")
        self.assertNotIn("Station: Station: no file chosen", skipped,
                         "Card name 'Station' must not be stuttered twice")

        self.assertIn("Voice: already analyzed", skipped)
        self.assertIn("Rules: the text is empty", skipped)
        self.assertIn("Station: no file chosen", skipped)

    def test_bug_069_batch_plan_does_not_duplicate_unnamed_media_labels_in_skip_messages(self):
        """RED: Unnamed cards must not repeat the media fallback twice in skip messages."""
        contexts = [
            {"media": "image", "widgets": {"image": ""}},
            {"media": "audio", "widgets": {"audio": "snd.wav", "analyzed": True}},
            {"media": "text", "widgets": {"text": ""}},
        ]
        targets, skipped = assist.batch_plan(contexts, "assist", True)
        self.assertEqual(targets, [])

        self.assertNotIn("image: image: no file chosen", skipped,
                         "Media fallback 'image' must not be stuttered twice")
        self.assertNotIn("audio: audio: already analyzed", skipped,
                         "Media fallback 'audio' must not be stuttered twice")
        self.assertNotIn("text: Text: the text is empty", skipped,
                         "Text fallback must not be stuttered twice")

        self.assertIn("image: no file chosen", skipped)
        self.assertIn("audio: already analyzed", skipped)
        # For unnamed text, either 'text: the text is empty' or 'Text: the text is empty'
        self.assertTrue(
            "text: the text is empty" in skipped or "Text: the text is empty" in skipped,
            f"Expected single-label text skip message, got: {skipped}"
        )

    def test_bug_069_all_reasons_have_single_colon_label_prefix(self):
        """RED: Every skip reason for unanalyzable media must have exactly one colon separator."""
        contexts = [
            {"media": "audio", "widgets": {"name": "Voice", "audio": "voice.wav", "analyzed": True}},
            {"media": "text", "widgets": {"name": "Rules", "text": ""}},
            {"media": "image", "widgets": {"name": "Station", "image": ""}},
            {"media": "hologram", "widgets": {}},
        ]
        targets, skipped = assist.batch_plan(contexts, "assist", True)
        for msg in skipped:
            # Each message should be '<label>: <reason>' without a double prefix '<label>: <label>: <reason>'
            colon_count = msg.count(":")
            self.assertEqual(
                colon_count, 1,
                f"Skip message has redundant colon separators (likely doubled label): {msg!r}"
            )

    def test_control_batch_plan_unsupported_medium_single_label(self):
        """GREEN Control: Unsupported media format already works with single label."""
        entries = [
            {"media": "text", "widgets": {"text": "Valid note"}},
            {"media": "hologram", "widgets": {}}
        ]
        targets, skipped = assist.batch_plan(entries, "auto", True)
        self.assertEqual(targets, [0])
        self.assertIn("hologram: no supported medium", skipped)

    def test_control_batch_plan_manual_mode_and_missing_provider(self):
        """GREEN Control: Mode guard messages are preserved without card iteration."""
        entries = [{"media": "image", "widgets": {"image": "test.png"}}]
        targets, skipped = assist.batch_plan(entries, "manual", True)
        self.assertEqual(targets, [])
        self.assertIn("Manual mode: no analysis is sent. Switch to Assist or Auto.", skipped)

        targets, skipped = assist.batch_plan(entries, "assist", False)
        self.assertEqual(targets, [])
        self.assertIn("Connect H3 AI Loader to the Connector first.", skipped)

    def test_control_batch_plan_valid_targets_returned(self):
        """GREEN Control: Analyzable card is correctly returned in targets list."""
        entries = [{"media": "image", "widgets": {"name": "Alice", "image": "alice.png"}}]
        targets, skipped = assist.batch_plan(entries, "assist", True)
        self.assertEqual(targets, [0])
        self.assertEqual(skipped, [])


if __name__ == "__main__":
    unittest.main()
