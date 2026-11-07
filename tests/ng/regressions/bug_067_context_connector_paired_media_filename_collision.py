"""BUG-067: paired media cards sharing a filename stem without explicit names collide in require_unique.

User flow:
In ComfyUI, a user organizes project assets per scene, e.g. `scene1.png` (a storyboard / reference picture)
and `scene1.wav` (dialogue or audio for scene 1). The user creates an H3 Context Image card with `scene1.png`
and an H3 Context Audio card with `scene1.wav`. On both cards, the `Name` widget is left empty (default).
Both cards are connected to the H3 Context Connector (`NGContextConnector`), or previewed in the Director Studio.

Observed:
`context_build.item_from_widgets` falls back to `label = name or os.path.splitext(os.path.basename(source))[0] or media`,
so both cards receive the derived name "scene1".
`require_unique(items)` validates `name.casefold()` globally across all items regardless of media type or whether
the name was user-specified, and raises:
`SchemaError: context.name: name used twice: scene1; use distinct names for @mentions and speakers`.
1. The ComfyUI graph execution immediately crashes with SchemaError in `NGContextConnector.execute`.
2. In the Director Studio, `/ng/plan` preview fails with `ok: False`, causing `S.planError` and disabling
   the "Generate" button completely.

Expected:
Paired media assets of different media types (`image` vs `audio` vs `video`) sharing a filename stem without
an explicit name should not collide and crash workflow execution or disable the Studio Generate button.

Run: python -B tests/ng/regressions/bug_067_context_connector_paired_media_filename_collision.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _pack import module, load_full_pack  # noqa: E402

load_full_pack()
context_build = module("ng.core.context_build")
connector_node = module("ng.nodes.connector_node")
preview = module("ng.core.preview")


class PairedMediaFilenameCollision(unittest.TestCase):
    def test_bug_067_connector_execute_with_paired_image_and_audio_same_stem(self):
        """Connecting scene1.png and scene1.wav without custom names must not crash with SchemaError."""
        img = context_build.item_from_widgets("image", {"image": "scene1.png", "name": "", "context_id": "ctx_img_1"})
        aud = context_build.item_from_widgets("audio", {"audio": "scene1.wav", "name": "", "context_id": "ctx_aud_2"})
        
        output = connector_node.NGContextConnector.execute(
            clip="dummy_clip", vae="dummy_vae", audio_vae="dummy_audio_vae",
            model_fl2va="dummy_model",
            context_image={"1": img}, context_audio={"2": aud}
        )
        self.assertIsNotNone(output)

    def test_bug_067_plan_preview_with_paired_image_and_audio_same_stem(self):
        """Previewing scene1.png and scene1.wav in Director Studio must return ok: True, not disable Generate."""
        payload = {
            "director": {"idea": "A cinematic scene", "project_seconds": 5.0},
            "contexts": [
                {"media": "image", "widgets": {"image": "scene1.png", "name": "", "context_id": "ctx_img_1"}},
                {"media": "audio", "widgets": {"audio": "scene1.wav", "name": "", "context_id": "ctx_aud_2"}}
            ]
        }
        res = preview.plan_preview(payload)
        self.assertTrue(res.get("ok"), "plan_preview failed with error: %s" % res.get("error"))

    # Controls: distinct stems or explicit distinct names work as expected
    def test_control_distinct_filenames_execute_and_preview_successfully(self):
        img = context_build.item_from_widgets("image", {"image": "scene1.png", "name": "", "context_id": "ctx_img_1"})
        aud = context_build.item_from_widgets("audio", {"audio": "narration1.wav", "name": "", "context_id": "ctx_aud_2"})
        output = connector_node.NGContextConnector.execute(
            clip="dummy_clip", vae="dummy_vae", audio_vae="dummy_audio_vae",
            model_fl2va="dummy_model",
            context_image={"1": img}, context_audio={"2": aud}
        )
        self.assertIsNotNone(output)

        res = preview.plan_preview({
            "director": {"idea": "A cinematic scene", "project_seconds": 5.0},
            "contexts": [
                {"media": "image", "widgets": {"image": "scene1.png", "name": "", "context_id": "ctx_img_1"}},
                {"media": "audio", "widgets": {"audio": "narration1.wav", "name": "", "context_id": "ctx_aud_2"}}
            ]
        })
        self.assertTrue(res.get("ok"))

    def test_control_explicit_distinct_names_execute_and_preview_successfully(self):
        img = context_build.item_from_widgets("image", {"image": "scene1.png", "name": "Keyframe One", "context_id": "ctx_img_1"})
        aud = context_build.item_from_widgets("audio", {"audio": "scene1.wav", "name": "Audio Track One", "context_id": "ctx_aud_2"})
        output = connector_node.NGContextConnector.execute(
            clip="dummy_clip", vae="dummy_vae", audio_vae="dummy_audio_vae",
            model_fl2va="dummy_model",
            context_image={"1": img}, context_audio={"2": aud}
        )
        self.assertIsNotNone(output)

        res = preview.plan_preview({
            "director": {"idea": "A cinematic scene", "project_seconds": 5.0},
            "contexts": [
                {"media": "image", "widgets": {"image": "scene1.png", "name": "Keyframe One", "context_id": "ctx_img_1"}},
                {"media": "audio", "widgets": {"audio": "scene1.wav", "name": "Audio Track One", "context_id": "ctx_aud_2"}}
            ]
        })
        self.assertTrue(res.get("ok"))


if __name__ == "__main__":
    unittest.main()
