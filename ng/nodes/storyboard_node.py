"""H3 Storyboard: a sheet of panels laid out in the node (js/ng/h3b_*.js). The browser draws the sheet and every panel's
picture and uploads them to input/h3-storyboard when the workflow is queued; this node hands them on as images, with the
panels as the Director's shot document."""
import hashlib
import json
import os

import numpy as np
import torch
from PIL import Image
from comfy_api.latest import io

from ..adapters.paths import input_path
from ..core.storyboard import read_board, shots_document
from .connector_node import NGInputs
from .context_nodes import CATEGORY


def _files(rendered):
    try:
        data = json.loads(rendered or "{}")
    except ValueError:
        data = {}
    names = [data.get("sheet")] + list(data.get("panels") or ()) if isinstance(data, dict) else [None]
    if not names[0] or len(names) < 2:
        raise ValueError("The storyboard has not been drawn yet: open the workflow in ComfyUI's browser tab and queue it from "
                         "there, the sheet is drawn in the browser.")
    paths = [input_path(name) for name in names]
    missing = [name for name, path in zip(names, paths) if not path]
    if missing:
        raise ValueError("The storyboard picture %s is missing from the input folder; queue the workflow again." % missing[0])
    return paths


def _image(path):
    with Image.open(path) as picture:
        return torch.from_numpy(np.asarray(picture.convert("RGB"), dtype=np.float32) / 255.0)


class NGStoryboard(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="NGStoryboard", display_name="H3 Storyboard", category=CATEGORY,
            description="Lay out a storyboard: numbered panels with pictures, cut-out figures and text layers, a time, a title "
                        "and a caption each. The AI writes the texts from what should happen. Outputs the sheet, the panels "
                        "and the panels as shots for the Director.",
            inputs=[io.String.Input("board", multiline=True, default="", tooltip="The storyboard, written by the node's editor."),
                    io.String.Input("rendered", default="", tooltip="The pictures the editor drew, set when the workflow is queued."),
                    NGInputs.Input("context", display_name="H3 context", optional=True, lazy=True,
                                   tooltip="The Context Connector's output, the same one the Director gets: its picture cards can "
                                           "be placed on panels, its names are used in the texts and its AI provider writes them. "
                                           "Only the editor reads it; it is not run with the workflow.")],
            outputs=[io.Image.Output(display_name="sheet"), io.Image.Output(display_name="panels"),
                     io.String.Output(display_name="shots", tooltip="The panels as the H3 Director's shots document.")])

    @classmethod
    def check_lazy_status(cls, **_):
        return []

    @classmethod
    def fingerprint_inputs(cls, board, rendered, **_):
        # The files keep their names when the sheet changes; their contents decide whether the outputs are new.
        try:
            stamps = [(os.path.getsize(path), os.path.getmtime(path)) for path in _files(rendered)]
        except ValueError:
            stamps = None
        return hashlib.sha1(json.dumps([board, rendered, stamps]).encode()).hexdigest()

    @classmethod
    def execute(cls, board, rendered, context=None):
        board = read_board(board)
        paths = _files(rendered)
        sheet = _image(paths[0])[None]
        panels = [_image(path) for path in paths[1:]]
        size = panels[0].shape
        panels = torch.stack([p if p.shape == size else torch.nn.functional.interpolate(
            p.permute(2, 0, 1)[None], size=size[:2], mode="bilinear")[0].permute(1, 2, 0) for p in panels])
        return io.NodeOutput(sheet, panels, shots_document(board))


NODES = [NGStoryboard]
