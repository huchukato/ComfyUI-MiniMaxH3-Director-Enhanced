"""A shot preview is the actual input, not an analysis frame or generated image."""
import base64
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from _pack import module, comfy_available, stub_prompt_server

context = module("ng.core.context")
build = module("ng.core.context_build")


class SingingContent(unittest.TestCase):
    def test_explicit_singing_content_survives_context_roundtrip_without_ai(self):
        self.assertIn("singing", context.CONTENT_BY_MEDIA["audio"])
        item = build.item_from_widgets("audio", {"audio": "song.wav", "name": "Song", "context_id": "song",
                                                "content_roles": '["singing","music"]', "usage": "copy"}, 3)
        self.assertEqual(item.content, ("singing", "music"))
        self.assertNotIn("content_unknown", {issue.code for issue in context.check_item(item)})
        self.assertEqual(context.ContextItem.from_dict(item.to_dict()), item)


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class FirstVideoFrame(unittest.TestCase):
    def setUp(self):
        import av
        from PIL import Image
        stub_prompt_server()
        self.preview = module("ng.adapters.preview_media")
        self.directory = tempfile.TemporaryDirectory()
        self.path_patch = patch("folder_paths.get_input_directory", return_value=self.directory.name)
        self.path_patch.start()
        with av.open(os.path.join(self.directory.name, "colors.mp4"), "w") as container:
            stream = container.add_stream("mpeg4", rate=24)
            stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
            for color in ("red", "green", "blue"):
                frame = av.VideoFrame.from_image(Image.new("RGB", (64, 64), color))
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def tearDown(self):
        self.path_patch.stop()
        self.directory.cleanup()

    def test_video_preview_reports_and_decodes_first_frame_without_analysis_sampling(self):
        from PIL import Image
        with patch.object(self.preview, "video_images", side_effect=AssertionError("analysis sampler must not run")):
            result = self.preview.preview("video", "colors.mp4")
        self.assertEqual(result["frame_index"], 0)
        with Image.open(io.BytesIO(base64.b64decode(result["thumbnail"].split(",", 1)[1]))) as image:
            red, green, blue = image.convert("RGB").getpixel((32, 32))
        self.assertGreater(red, 220)
        self.assertLess(max(green, blue), 30)

    def test_missing_and_corrupt_video_remain_actionable_errors(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            self.preview.preview("video", "missing.mp4")
        with open(os.path.join(self.directory.name, "broken.mp4"), "wb") as stream:
            stream.write(b"not a video")
        with self.assertRaises((OSError, ValueError)):
            self.preview.preview("video", "broken.mp4")
