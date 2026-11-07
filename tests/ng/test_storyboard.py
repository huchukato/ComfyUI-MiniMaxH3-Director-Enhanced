"""H3 Storyboard: the board the editor writes, the panels as the Director's shots, the AI's panel texts and the node."""
import json
import os
import tempfile
import unittest
from unittest import mock

from _pack import comfy_available, module, stub_prompt_server

storyboard, texts = module("ng.core.storyboard"), module("ng.core.storyboard_texts")
LUNA = {"media": "image", "widgets": {"name": "Luna", "description": "An adult woman with long violet hair.", "image": "luna.png"}}


def board(*seconds, **extra):
    data = storyboard.new_board()
    data["panels"] = [{"id": "p%d" % n, "seconds": s, "title": "", "caption": "", "shot": "", "layers": []} for n, s in enumerate(seconds, 1)]
    data.update(extra)
    return data


class Board(unittest.TestCase):
    def test_panels_follow_each_other_and_become_shots(self):
        data = board(2.5, 5, 2.5)
        data["panels"][1].update(caption="They meet.", shot="0–2.5s: A full-body shot. 2.5–5s: A close-up.")
        self.assertEqual(storyboard.panel_times(data), [(0.0, 2.5), (2.5, 7.5), (7.5, 10.0)])
        shots = json.loads(storyboard.shots_document(data))["shots"]
        self.assertEqual([(s["start"], s["end"]) for s in shots], [(0.0, 2.5), (2.5, 7.5), (7.5, 10.0)])
        self.assertEqual(shots[1]["text"], "0–2.5s: A full-body shot. 2.5–5s: A close-up.", "the shot text, not the caption")
        self.assertEqual(module("ng.core.shots").parse_shots(storyboard.shots_document(data), 240)[1], (), "the Director reads it")

    def test_an_empty_widget_is_a_new_board_and_bad_data_is_named(self):
        fresh = storyboard.read_board("")
        self.assertEqual(fresh["format"], "h3-storyboard")
        self.assertEqual((fresh["panels"][0]["first_frame"], fresh["panels"][0]["last_frame"]), (False, False))
        raw = board(2.5)
        raw["panels"][0]["last_frame"] = True
        parsed = storyboard.read_board(json.dumps(raw))
        self.assertEqual((parsed["panels"][0]["first_frame"], parsed["panels"][0]["last_frame"]), (False, True))
        for bad, words in (("{", "readable JSON"), ('{"format":"x"}', "not H3 storyboard"),
                           (json.dumps(board(*[1] * 10)), "1 to 9 panels"), (json.dumps(board(2, aspect="5:2")), "panel format"),
                           (json.dumps(board(0)), "seconds")):
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, words):
                storyboard.read_board(bad)


class Texts(unittest.TestCase):
    def test_the_request_gives_each_long_panel_its_beats_and_keeps_the_users_words(self):
        data = board(2.5, 10, idea="@Luna lights the altar.")
        data["panels"][0]["title"] = "INTRO"
        prompt = texts.texts_prompt(data, [LUNA])
        self.assertIn('"write_shot_as_beats": "0–5s, 5–10s"', prompt)
        self.assertIn('{"title":"...","caption":"...","shot":"..."},{"title":"...","caption":"...","shot":"0–5s: ... 5–10s: ..."}', prompt)
        self.assertEqual(prompt.count("write_shot_as_beats\""), 1, "2.5 s needs no beats")
        self.assertIn('"user_title": "INTRO"', prompt)
        self.assertIn("@Luna: An adult woman with long violet hair.", prompt)
        self.assertIn("holds a static shot", prompt)
        with self.assertRaisesRegex(ValueError, "what should happen"):
            texts.texts_prompt(board(2.5), [LUNA])

    def test_the_answer_fills_every_panel_and_a_missing_one_keeps_its_texts(self):
        data = board(2.5, 2.5, 2.5, idea="x")
        data["panels"][2]["caption"] = "Own caption."
        answer = {"title": "THE PACT", "subtitle": "LUNA - 7.5 SECONDS", "panels": [
            {"title": "INTRO", "caption": "Luna enters.", "shot": "A full-body shot of @Luna. The camera holds a static shot."},
            {"title": "ALTAR", "caption": "She  touches\nit.", "shot": "@Nobody waves."}]}
        result = texts.parse_texts("```json\n%s\n```" % json.dumps(answer), data, [LUNA])
        self.assertEqual((result["title"], result["subtitle"]), ("THE PACT", "LUNA - 7.5 SECONDS"))
        self.assertEqual(result["panels"][1]["caption"], "She touches it.")
        self.assertEqual(result["panels"][1]["shot"], "Nobody waves.")
        self.assertEqual(result["unknown_mentions"], ["Nobody"])
        self.assertEqual(result["panels"][2]["caption"], "Own caption.")
        self.assertEqual(result["missing"], [3])
        with self.assertRaisesRegex(ValueError, "no panel texts"):
            texts.parse_texts('{"panels": []}', data, [LUNA])


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class Node(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stub_prompt_server()

    def test_the_node_hands_on_the_drawn_pictures_and_the_shots(self):
        from PIL import Image
        node = module("ng.nodes.storyboard_node").NGStoryboard
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "h3-storyboard"))
            for name, size in (("s.png", (64, 40)), ("p1.png", (32, 18)), ("p2.png", (16, 9))):
                Image.new("RGB", size, (200, 10, 10)).save(os.path.join(root, "h3-storyboard", name))
            rendered = json.dumps({"sheet": "h3-storyboard/s.png", "panels": ["h3-storyboard/p1.png", "h3-storyboard/p2.png"]})
            with mock.patch("folder_paths.get_input_directory", return_value=root):
                out = node.execute(board=json.dumps(board(2.5, 2.5)), rendered=rendered)
                self.assertEqual(tuple(out.args[0].shape), (1, 40, 64, 3))
                self.assertEqual(tuple(out.args[1].shape), (2, 18, 32, 3), "panels of another size are fitted to the first")
                self.assertEqual(len(json.loads(out.args[2])["shots"]), 2)
                before = node.fingerprint_inputs(board="", rendered=rendered)
                Image.new("RGB", (64, 40)).save(os.path.join(root, "h3-storyboard", "s.png"))
                os.utime(os.path.join(root, "h3-storyboard", "s.png"), (1, 1))
                self.assertNotEqual(before, node.fingerprint_inputs(board="", rendered=rendered), "a redrawn sheet runs again")
                with self.assertRaisesRegex(ValueError, "not been drawn"):
                    node.execute(board="", rendered="")

    def test_the_editor_links_are_never_run(self):
        node = module("ng.nodes.storyboard_node").NGStoryboard
        self.assertEqual(node.check_lazy_status(context=None), [])
        inputs = {item.id: item for item in node.GET_SCHEMA().inputs}
        self.assertTrue(inputs["context"].lazy)
        self.assertNotIn("ai_provider", inputs, "the AI provider comes through the Context Connector")


if __name__ == "__main__":
    unittest.main()
