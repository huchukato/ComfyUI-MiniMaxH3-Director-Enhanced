"""TAEHV live preview shared by the Legacy and NG model nodes."""

import comfy.patcher_extension
from comfy_api.latest import io

from .minimax_preview_runtime import PreviewOptions, OuterSamplePreview, require_taehv

WRAPPER_KEY = "minimax_h3_preview"


def preview_schema(node_id, display_name, category, optional_vae=False):
    return io.Schema(
        node_id=node_id, display_name=display_name, category=category,
        description="TAEHV preview of the complete H3 shot while sampling. "
                    "Connect after the Director model output and attach an H3 TAEHV VAE.",
        inputs=[
            io.Model.Input("model"),
            io.Vae.Input("vae", optional=optional_vae,
                         tooltip="Connect an H3 TAEHV VAE loaded from taeh3.safetensors. "
                                 "A full video VAE is not supported for live previews."),
            io.Int.Input("max_resolution", default=768, min=128, max=2048, step=32,
                         tooltip="Maximum preview long edge. TAEHV decodes real image detail; "
                                 "larger values cost more time and memory."),
            io.Float.Input("preview_fps", default=24.0, min=1.0, max=24.0, step=1.0,
                           tooltip="Display cadence, up to H3's native 24 FPS. "
                                   "The complete shot keeps its original duration."),
            io.Int.Input("jpeg_quality", default=90, min=50, max=100, step=1),
            io.Int.Input("every_n_steps", default=1, min=1, max=50, step=1,
                         tooltip="Minimum sampler step interval between preview requests."),
            io.Int.Input("max_preview_overhead", default=25, min=0, max=100, step=5,
                         tooltip="Preview work limit in percent; 0 allows continuous "
                                 "updates. Playback continues independently of updates."),
            io.Boolean.Input("suppress_default_preview", default=True,
                             tooltip="Hide the sampler's single-frame preview while this node runs."),
        ],
        outputs=[io.Model.Output()],
        hidden=[io.Hidden.unique_id, io.Hidden.dynprompt],
    )


def execute_preview(cls, model, vae, **values):
    require_taehv(vae)
    hidden = cls.hidden
    node_id = str(hidden.unique_id)
    if hidden.dynprompt is not None:
        node_id = str(hidden.dynprompt.get_display_node_id(node_id))
    options = PreviewOptions.from_values(values)
    cloned = model.clone()
    wrappers = cloned.model_options.setdefault("transformer_options", {}).setdefault("wrappers", {})
    # A second Preview node replaces this package's wrapper rather than decoding twice.
    wrappers.setdefault(comfy.patcher_extension.WrappersMP.OUTER_SAMPLE, {}).pop(WRAPPER_KEY, None)
    comfy.patcher_extension.add_wrapper_with_key(
        comfy.patcher_extension.WrappersMP.OUTER_SAMPLE, WRAPPER_KEY,
        OuterSamplePreview(node_id, options, vae), cloned.model_options, is_model_options=True)
    return io.NodeOutput(cloned)


class MiniMaxH3PreviewOverride(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return preview_schema("MiniMaxH3PreviewOverrideCS", "🎯 Preview Override (live)", "MiniMax H3/NG/Custom loop")

    @classmethod
    def execute(cls, model, vae, **values) -> io.NodeOutput:
        return execute_preview(cls, model, vae, **values)
