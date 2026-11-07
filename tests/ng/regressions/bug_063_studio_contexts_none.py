"""Regression test for BUG-063: NGDirectorStudio crashes when optional contexts is None.

In ComfyUI, the NGDirectorStudio ('NG Studio Laboratory') node declares:
    io.Autogrow.Input("contexts", template=contexts, optional=True)
When a user places the studio node in their graph without connecting any Context
cards (which is valid since contexts is optional), ComfyUI executes the node
passing kwargs containing:
    contexts=None

In ng/nodes/studio_node.py:26:
    planning.update({"contexts." + name: link for name, link in values.get("contexts", {}).items()})
Because 'contexts' is a present key in values with value None, values.get("contexts", {})
evaluates to None instead of the fallback {}. Calling None.items() raises:
    AttributeError: 'NoneType' object has no attribute 'items'
preventing the user from rendering or planning a project in the Studio without
connecting at least one context card.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NG_TESTS = os.path.dirname(HERE)
if NG_TESTS not in sys.path:
    sys.path.insert(0, NG_TESTS)

from _pack import comfy_available, load_full_pack


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class TestBug063StudioContextsNone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_full_pack()
        cls.studio = cls.pack.NODE_CLASS_MAPPINGS["NGDirectorStudio"]

    def _base_values(self):
        return dict(
            clip=["clip", 0],
            vae=["video_vae", 0],
            audio_vae=["audio_vae", 0],
            model_fl2va=["fl2va", 0],
            model_ref2va=["ref2va", 0],
            seed=123,
            steps=8,
            sampler_name="res_multistep",
            scheduler="simple",
            shift_video=12.0,
            shift_audio=3.0,
            idea="@Alice walks.",
            project_seconds=20.0,
            shots="",
            chunk_seconds=10.0,
            width=384,
            height=576,
            mode="auto",
            continuity="video_audio",
            pin_frames="22",
            soundscape="wind",
            music="N/A",
        )

    # ------------------ GREEN CONTROLS ------------------

    def test_control_studio_executes_with_contexts_dict(self):
        values = self._base_values()
        values["contexts"] = {"context_1": ["alice", 0]}
        output = self.studio.execute(**values)
        self.assertIsNotNone(output)
        self.assertEqual(len(output.args), 6)

    def test_control_studio_executes_with_empty_contexts_dict(self):
        values = self._base_values()
        values["contexts"] = {}
        output = self.studio.execute(**values)
        self.assertIsNotNone(output)
        self.assertEqual(len(output.args), 6)

    def test_control_studio_executes_with_omitted_contexts(self):
        values = self._base_values()
        output = self.studio.execute(**values)
        self.assertIsNotNone(output)
        self.assertEqual(len(output.args), 6)

    # ------------------ RED REGRESSION TEST ------------------

    def test_bug_063_studio_executes_with_contexts_none_must_not_crash(self):
        """When ComfyUI supplies contexts=None for an unwired optional autogrow input,

        NGDirectorStudio.execute must safely treat it as empty dict rather than
        calling None.items() and raising AttributeError.
        """
        values = self._base_values()
        values["contexts"] = None
        # On current codebase, this raises AttributeError: 'NoneType' object has no attribute 'items'
        output = self.studio.execute(**values)
        self.assertIsNotNone(output)
        self.assertEqual(len(output.args), 6)


if __name__ == "__main__":
    unittest.main()
