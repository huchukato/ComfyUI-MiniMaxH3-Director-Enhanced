"""Save the last frame of a decoded batch, and pass the batch on untouched.

Sits directly after `VAEDecode`. Every H3 render ends on a frame worth keeping — it is the
one you feed back in as the next shot's opening keyframe — and fishing it out otherwise
means a second graph with `ImageFromBatch` wired to a `SaveImage`, rebuilt every time the
length changes.

Two things it deliberately does *not* do:

* **it never touches the pixels.** The IMAGE output is the same tensor object that came in,
  so putting this in the middle of a chain cannot change what anything downstream decodes,
  encodes or muxes. The passthrough is the point; saving is the side effect.
* **it does not need to be bypassed.** `save` is a widget rather than a reason to reach for
  Ctrl+B, because a node that has to be disabled between runs is a node that will be left
  enabled by accident.

The file, the counter, the `%date:…%` prefix tokens and the embedded workflow metadata are
core's, through `ImageSaveHelper` — so a frame saved here is a frame `SaveImage` would have
written, and the node body stays about *which* frame.
"""

import logging

from comfy_api.latest import io, ui

log = logging.getLogger(__name__)


class MiniMaxH3SaveLastFrame(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3SaveLastFrameCS",
            display_name="MiniMax H3 Save Last Frame",
            category="MiniMax H3/Legacy",
            description=(
                "Saves the LAST frame of an image batch as a PNG, whatever the length, and "
                "passes the whole batch through unchanged. Put it straight after VAEDecode. "
                "Turn 'save' off to skip writing a file without unwiring or bypassing the node."
            ),
            inputs=[
                io.Image.Input("images",
                               tooltip="The decoded frames (VAEDecode output). Passed on "
                                       "unchanged, whether or not a file is written."),
                io.Boolean.Input("save", default=True,
                                 tooltip="Off = pass the frames through and write nothing. "
                                         "Here so you never have to bypass the node."),
                io.String.Input("filename_prefix", default="MiniMaxH3/lastframe",
                                tooltip="Prefix for the saved file, under ComfyUI's output "
                                        "folder. Supports the same tokens as Save Image, "
                                        "e.g. %date:yyyy-MM-dd%."),
            ],
            outputs=[
                io.Image.Output(display_name="images",
                                tooltip="The input batch, untouched."),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            # Output node so the graph runs it even when nothing downstream is wired, and so
            # the saved frame gets a preview in the node body the way Save Image does.
            is_output_node=True,
        )

    @classmethod
    def execute(cls, images, save=True, filename_prefix="MiniMaxH3/lastframe") -> io.NodeOutput:
        if not save:
            return io.NodeOutput(images)

        # An empty batch is not an error worth failing a finished render over: this node
        # sits at the end of the graph, so raising here throws away the whole run for a
        # frame that was never there.
        count = int(images.shape[0]) if getattr(images, "shape", None) is not None else 0
        if count < 1:
            log.warning("[MiniMaxSaveLastFrame] the batch is empty — nothing to save.")
            return io.NodeOutput(images)

        # Slice, do not index: images[-1] would drop the batch dimension and the saver
        # expects [N, H, W, C].
        last = images[-1:]
        saved = ui.ImageSaveHelper.get_save_images_ui(last, filename_prefix=filename_prefix,
                                                      cls=cls)
        names = ", ".join(r["filename"] for r in saved.results)
        log.info("[MiniMaxSaveLastFrame] frame %d of %d (%dx%d) -> %s",
                 count, count, int(images.shape[2]), int(images.shape[1]), names)

        # `images`, not `last` — the batch goes on whole.
        return io.NodeOutput(images, ui=saved)


NODE_CLASS_MAPPINGS = {"MiniMaxH3SaveLastFrameCS": MiniMaxH3SaveLastFrame}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3SaveLastFrameCS": "MiniMax H3 Save Last Frame"}
