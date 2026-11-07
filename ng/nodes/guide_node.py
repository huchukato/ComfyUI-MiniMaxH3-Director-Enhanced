"""H3 Guide: the user guide inside the graph. The chapters are Markdown files with pictures in js/guide (also the guide on
GitHub); the browser shows the chosen one in the node (js/ng/h3g_guide.js). The node is never sent to the server."""
import json
import os

from comfy_api.latest import io

from .context_nodes import CATEGORY

GUIDE = os.path.join(os.path.dirname(__file__), "..", "..", "js", "guide", "guide.json")


def chapters():
    with open(GUIDE, encoding="utf-8") as file:
        return [chapter["id"] for chapter in json.load(file)["chapters"]]


class NGGuide(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        ids = chapters()
        return io.Schema(node_id="NGGuide", display_name="H3 Guide", category=CATEGORY,
                         description="The H3 Director's guide with pictures, chapter by chapter. Put it next to a workflow; it does "
                                     "nothing when the workflow runs.",
                         inputs=[io.Combo.Input("chapter", options=ids, default=ids[0], tooltip="The chapter the node shows.")],
                         outputs=[])

    @classmethod
    def execute(cls, chapter):
        return io.NodeOutput()


NODES = [NGGuide]
