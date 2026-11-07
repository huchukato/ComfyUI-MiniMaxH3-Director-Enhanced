"""BUG-054: split._keep merges a Content card named "Narrator" with the anonymous narrator.

A card may legitimately be named "Narrator": the Context node's name widget is free text ("What the Director and
your shot text call this") and the repo's own fixtures do it (tests/ng/test_compile.py: an audio voice card and a
text note both named "Narrator"). The split prompt tells the model "speaker is the exact Content name of who says
it", so the answer names that card, and ng/core/split.py:_owner binds the line to the card's context_id
(`_owner("Narrator", contexts)` -> ("ctx_narr", "a narrator")).

_keep then reads the same name the other way round (ng/core/split.py:103):

    own.setdefault(("" if name.casefold() == "narrator" else name).casefold(), []).append(...)

so the Studio's own dialogue text for that card (`ownLines()` in js/ng/h3s_ai.js writes "@Narrator says: ...")
is filed under the empty key, while `key(line)` (split.py:107, fed by `names`, split.py:106) maps the card's
context_id to the key "narrator". The two sides never meet:

  * the user's line for the card does not replace the card's AI line - the AI line stays, so the dialogue is
    doubled, and the user's line is appended to the LAST shot (the `shots[-1]` fallback) with speaker_id "";
  * the card's line and the real narrator's line (speaker "") are merged into one shot, both with speaker_id "",
    so the card's line is compiled as an off-screen "@voice(A narrator)" instead of "@Narrator"
    (ng/core/shot_bindings.py:spoken_text).

The control (the same card named "Sage") places and binds the line correctly.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module

direction = module("ng.core.auto_direct")


def card(name, context_id):
    return {"media": "image", "widgets": {"name": name, "context_id": context_id, "description": "a figure"}}


def spoken_of(shots):
    return [[(line["text"], line["speaker_id"]) for line in shot["spoken"]] for shot in shots]


class SplitNarratorNamedCard(unittest.TestCase):
    def answer(self, name):
        return {"look": "Dark hall.", "soundscape": "Room tone", "music": "N/A", "shots": [
            {"start_s": 0, "end_s": 4, "action": "@%s stands." % name, "camera": "Wide.",
             "lines": [{"speaker": name, "delivery": "says", "language": "English", "text": "AI CARD line."}]},
            {"start_s": 4, "end_s": 8, "action": "The hall is dark.", "camera": "Wide.",
             "lines": [{"speaker": "", "delivery": "says", "language": "English", "text": "AI NARRATOR line."}]}]}

    def split(self, name, context_id, keep):
        result = direction.parse_direction(json.dumps(self.answer(name)), 8, [card(name, context_id)], keep=keep)
        return json.loads(result["shots"])["shots"]

    def test_the_users_line_for_a_card_named_narrator_replaces_its_line_in_its_own_shot(self):
        shots = self.split("Narrator", "ctx_narr", "@Narrator says: MY CARD LINE.")

        self.assertEqual(
            spoken_of(shots),
            [[("MY CARD LINE.", "ctx_narr")], [("AI NARRATOR line.", "")]],
            "the user's line for the card named Narrator must replace that card's line, in the card's shot, "
            "bound to the card's context_id - not land in the last shot as an anonymous narrator")

    def test_a_card_named_narrator_and_the_real_narrator_stay_separate_speakers(self):
        shots = self.split("Narrator", "ctx_narr", "@Narrator says: MY CARD LINE.\nNarrator says: MY NARRATOR LINE.")

        self.assertEqual(
            spoken_of(shots),
            [[("MY CARD LINE.", "ctx_narr")], [("MY NARRATOR LINE.", "")]],
            "the card named Narrator and the anonymous narrator are two speakers: each user line replaces its own "
            "AI line in its own shot, and only the narrator's line stays unbound")

    def test_control_the_same_card_named_sage_is_placed_and_bound(self):
        shots = self.split("Sage", "ctx_sage", "@Sage says: MY CARD LINE.")

        self.assertEqual(spoken_of(shots), [[("MY CARD LINE.", "ctx_sage")], [("AI NARRATOR line.", "")]])

    def test_control_the_card_and_the_narrator_keep_their_own_shots_when_the_card_is_named_sage(self):
        shots = self.split("Sage", "ctx_sage", "@Sage says: MY CARD LINE.\nNarrator says: MY NARRATOR LINE.")

        self.assertEqual(spoken_of(shots), [[("MY CARD LINE.", "ctx_sage")], [("MY NARRATOR LINE.", "")]])


if __name__ == "__main__":
    unittest.main()
