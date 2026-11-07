"""The connectable Director: model inputs and contexts directly to a finished video."""
from comfy_api.latest import io

from ..adapters.render_graph import director_sequence
from .context_nodes import CATEGORY, NGContext
from .director_node import NGDirector
from .render_node import model_inputs, sampling_inputs, render_outputs, split_render_inputs


class NGDirectorStudio(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        planning = NGDirector.define_schema().inputs[:-1]
        contexts = io.Autogrow.TemplatePrefix(input=NGContext.Input("context", raw_link=True), prefix="context_", min=0, max=15)
        return io.Schema(node_id="NGDirectorStudio", display_name="NG Studio Laboratory", category=CATEGORY + "/Custom loop",
                         description="Write your idea, connect contexts and H3 models, then Run. Plans and renders the entire project with native progress and interrupt.",
                         inputs=[*model_inputs(), *planning, io.Autogrow.Input("contexts", template=contexts, optional=True), *sampling_inputs()],
                         outputs=[*render_outputs(), io.String.Output(display_name="plan"), io.String.Output(display_name="plan_warnings")],
                         enable_expand=True)

    @classmethod
    def execute(cls, **values):
        inputs, settings = split_render_inputs(values)
        planning_names = [item.id for item in NGDirector.define_schema().inputs[:-1]]
        planning = {name: values[name] for name in planning_names if name in values}
        planning.update({"contexts." + name: link for name, link in (values.get("contexts") or {}).items()})     # None when unwired (BUG-063)
        expanded, outputs = director_sequence(planning, inputs, settings)
        return io.NodeOutput(*outputs, expand=expanded)


NODES = [NGDirectorStudio]
