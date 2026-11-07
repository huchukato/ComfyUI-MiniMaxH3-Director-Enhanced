"""Bundle typed context groups and unevaluated native loader connections."""
from comfy_api.latest import io

from ..adapters.director_packets import DirectorInputs
from ..core.context import ContextItem, require_unique
from ..core.context_build import distinct
from .context_nodes import CATEGORY, NGContext
from .provider_node import NGAI

NGInputs = io.Custom("NG_DIRECTOR_INPUT")


def context_group(media, maximum):
    template = io.Autogrow.TemplatePrefix(input=NGContext.Input(media), prefix=media + "_", min=0, max=maximum)
    return io.Autogrow.Input("context_" + media, template=template, optional=True)


class NGContextConnector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGContextConnector", display_name="H3 Context Connector", category=CATEGORY,
                         description="Collect H3 models, encoders, VAEs and reusable Context nodes for the Director. AI is optional.",
                         inputs=[io.Model.Input("model_fl2va", display_name="model", raw_link=True, lazy=True, optional=True),
                                 io.Model.Input("model_ref2va", display_name="model ref", raw_link=True, lazy=True, optional=True),
                                 io.Clip.Input("clip", display_name="CLIP", raw_link=True, lazy=True),
                                 io.Vae.Input("vae", display_name="VAE", raw_link=True, lazy=True),
                                 io.Vae.Input("audio_vae", display_name="audio VAE", raw_link=True, lazy=True),
                                 NGAI.Input("ai_provider", display_name="AI provider", optional=True),
                                 context_group("text", 15), context_group("image", 15),
                                 context_group("video", 15), context_group("audio", 15),
                                 io.Vae.Input("preview_vae", display_name="preview VAE", raw_link=True, lazy=True, optional=True,
                                              tooltip="Optional H3 TAEHV VAE (taeh3): H3 Render Sequence shows a live preview of each part; also available at H3 Director Output."),
                                 io.ModelPatch.Input("model_patch", raw_link=True, lazy=True, optional=True,
                                                     tooltip="ModelPatchLoader with minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot. Used by control clips on the Studio timeline.")],
                         outputs=[NGInputs.Output(display_name="H3 context")])

    @classmethod
    def execute(cls, clip, vae, audio_vae, model_fl2va=None, model_ref2va=None, ai_provider=None, preview_vae=None, model_patch=None, **groups):
        if model_fl2va is None and model_ref2va is None:
            raise ValueError("Connect an H3 model to model or model ref.")
        items = []
        for media in ("text", "image", "video", "audio"):
            for item in (groups.get("context_" + media) or {}).values():
                if not isinstance(item, ContextItem) or item.media != media:
                    raise ValueError("Connect a %s Context node to context %s." % (media, media))
                items.append(item)
        items = list(distinct(items))
        require_unique(items)
        return io.NodeOutput(DirectorInputs(clip, vae, audio_vae, model_fl2va, model_ref2va, tuple(items), ai_provider,
                                           preview_vae=preview_vae, model_patch=model_patch))


NODES = [NGContextConnector]
