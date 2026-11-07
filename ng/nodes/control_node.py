"""H3 Control Video (experimental): Fun ControlNet-Union per render part, between H3 Director Output and the sampler."""
from comfy_api.latest import io

from ...minimax_core import core
from ..adapters import control, control_media
from ..core import control_timing
from ..adapters.director_packets import chunk_job
from .context_nodes import CATEGORY
from .director_node import NGChunk
from .product_director_node import NGResult


class NGControlVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGControlVideo", display_name="H3 Control Video (experimental)", category=CATEGORY + "/Custom loop",
                         description="Steer each render part with a pose, depth or edge video (MiniMax H3 Fun ControlNet-Union), or "
                                     "regenerate masked regions of a source video. The videos run on the story timeline at 24 fps; "
                                     "each part gets its own window, its pinned head included.",
                         inputs=[io.Model.Input("model", tooltip="H3 Director Output's model for this chunk."),
                                 io.ModelPatch.Input("model_patch", tooltip="ModelPatchLoader with minimax_h3_fun_controlnet_union."),
                                 io.Vae.Input("vae", tooltip="The H3 video VAE (not the preview VAE)."),
                                 NGResult.Input("sequence", tooltip="H3 Director Output's sequence."),
                                 io.Int.Input("chunk_index", default=0, min=0, max=9999, advanced=True),
                                 NGChunk.Input("loop_chunk", optional=True, tooltip="Start Loop list_item, as on H3 Director Output."),
                                 io.Float.Input("strength", default=1.0, min=0.0, max=10.0, step=0.01),
                                 io.Float.Input("start_percent", default=0.0, min=0.0, max=1.0, step=0.001, advanced=True),
                                 io.Float.Input("end_percent", default=1.0, min=0.0, max=1.0, step=0.001, advanced=True),
                                 io.Image.Input("control_video", optional=True, tooltip="Pose, depth, canny, HED or MLSD frames."),
                                 io.Mask.Input("mask", optional=True, tooltip="1 marks the regions to regenerate (e.g. SAM3 Track to Mask)."),
                                 io.Image.Input("source_video", optional=True, tooltip="The video behind the mask; only read with a mask."),
                                 io.Combo.Input("mask_shape", options=list(control.MASK_SHAPES), default="box", optional=True,
                                                tooltip="box: regenerate the mask's bounding box per frame (a new figure of another shape "
                                                        "fits in, no grey rim). outline: only the masked shape itself."),
                                 io.Int.Input("mask_grow", default=16, min=0, max=256, optional=True,
                                              tooltip="Pixels added around the box or outline.")],
                         outputs=[io.Model.Output(display_name="model")])

    @classmethod
    def execute(cls, model, model_patch, vae, sequence, chunk_index=0, loop_chunk=None, strength=1.0, start_percent=0.0,
                end_percent=1.0, control_video=None, mask=None, source_video=None, mask_shape="box", mask_grow=16):
        job = chunk_job(sequence, chunk_index, loop_chunk)
        return io.NodeOutput(control.apply(core(), model, model_patch, vae, job, strength, start_percent, end_percent,
                                           control_video, mask, source_video, mask_shape, mask_grow))


class NGControlChunk(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGControlChunk", display_name="NG Control Chunk", category=CATEGORY + "/Technical", is_dev_only=True,
                         inputs=[io.Model.Input("model"), NGChunk.Input("chunk"),
                                 io.ModelPatch.Input("model_patch", optional=True, lazy=True),
                                 io.Vae.Input("vae", optional=True, lazy=True),
                                 io.Float.Input("strength", default=1.0, min=0.0, max=10.0),
                                 io.Float.Input("start_percent", default=0.0, min=0.0, max=1.0),
                                 io.Float.Input("end_percent", default=1.0, min=0.0, max=1.0)],
                         outputs=[io.Model.Output()])

    @classmethod
    def check_lazy_status(cls, chunk, strength=1.0, model_patch=None, vae=None, **_):
        job = chunk[0] if isinstance(chunk, list) else chunk
        if strength == 0 or not control_timing.spans(job):
            return []
        return [name for name, value in (("model_patch", model_patch), ("vae", vae)) if value is None]

    @classmethod
    def execute(cls, model, chunk, model_patch=None, vae=None, strength=1.0, start_percent=0.0, end_percent=1.0):
        job = chunk[0] if isinstance(chunk, list) else chunk
        if strength == 0 or not control_timing.spans(job):
            return io.NodeOutput(model)
        if model_patch is None or vae is None:
            raise ValueError("Connect ModelPatchLoader to the Context Connector's model_patch for control clips.")
        if end_percent < start_percent:
            raise ValueError("ControlNet denoising end must be at or after start.")
        images = control_media.prepare(job)
        out = core().MiniMaxH3FunControlNetApply.execute(model=model, model_patch=model_patch, vae=vae, strength=strength,
                                                      start_percent=start_percent, end_percent=end_percent,
                                                      control_video=images.control_video, mask=images.mask, source_video=images.source_video)
        return io.NodeOutput(out.args[0])


NODES = [NGControlVideo, NGControlChunk]
