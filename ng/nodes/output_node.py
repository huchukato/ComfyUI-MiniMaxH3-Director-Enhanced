"""Unpack prepared native sampler values or render the whole planned sequence."""
from comfy.samplers import KSampler
from comfy_api.latest import io

from ..adapters.director_packets import prepare_output, render_project
from ..core.project import jobs
from .context_nodes import CATEGORY
from .director_node import NGChunk
from .product_director_node import NGResult
from .render_node import render_outputs


class _Choice(io.Combo.Output):
    """A combo output typed with its option list itself. KSampler declares sampler_name and scheduler the old way, as that
    list, and ComfyUI links such an input only to an output of exactly that list; a plain COMBO output is refused."""
    def __init__(self, display_name, options, tooltip):
        super().__init__(display_name=display_name, options=list(options), tooltip=tooltip)
        self._options_type = options

    @property
    def io_type(self):
        return self._options_type


def _choice(name, options, tooltip):
    return _Choice(name, options, tooltip)


class NGDirectorOutput(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGDirectorOutput", display_name="H3 Director Output", category=CATEGORY,
                         description="Native sampler values, seed and the Director's sampling settings for the current chunk. Connect Director.chunks to Start Loop, then its list_item and current_iteration_value here. Sequence also supports H3 Render Sequence.",
                         inputs=[NGResult.Input("result", display_name="input"),
                                 io.Int.Input("chunk_index", default=0, min=0, max=9999, advanced=True),
                                 io.Latent.Input("previous", optional=True, raw_link=True,
                                                 tooltip="Full, untrimmed AV latent of the previous completed chunk, including video and audio."),
                                 NGChunk.Input("loop_chunk", optional=True,
                                               tooltip="Start Loop list_item from the same Director's chunks. Overrides chunk_index."),
                                 io.Boolean.Input("apply_sigma_shift", default=True, optional=True, advanced=True,
                                                  tooltip="Disable when your connected MODEL already has the desired native H3 Sigma Shift."),
                                 io.Int.Input("seed", optional=True, force_input=True, min=0, max=0xffffffffffffffff,
                                              tooltip="Optional base seed override; the output adds the current chunk index. Otherwise use the Director's seed.")],
                         outputs=[io.Model.Output(display_name="model"), io.Conditioning.Output(display_name="positive"),
                                  io.Conditioning.Output(display_name="negative"), io.Latent.Output(display_name="latent"),
                                  io.Float.Output(display_name="fps"), io.Int.Output(display_name="width"),
                                  io.Int.Output(display_name="height"), io.String.Output(display_name="prompt"),
                                  NGResult.Output(display_name="sequence"), io.Int.Output(display_name="seed"),
                                  # The Director's sampling settings for an external sampler; appended, so older links keep their slots.
                                  io.Int.Output(display_name="steps", tooltip="The Director's steps (4 with Turbo)."),
                                  io.Float.Output(display_name="cfg", tooltip="1.0: H3 is sampled without classifier-free guidance, like H3 Render Sequence."),
                                  _choice("sampler_name", KSampler.SAMPLERS, "The Director's sampler, for KSampler or KSamplerSelect."),
                                  _choice("scheduler", KSampler.SCHEDULERS, "The Director's scheduler, for KSampler or BasicScheduler."),
                                  io.Sampler.Output(display_name="sampler", tooltip="Ready for SamplerCustomAdvanced."),
                                  io.Sigmas.Output(display_name="sigmas", tooltip="Steps and scheduler on this chunk's model, ready for SamplerCustomAdvanced."),
                                  io.Vae.Output(display_name="preview VAE", tooltip="The Context Connector's optional VAE for Preview Override (live).")],
                         enable_expand=True)

    @classmethod
    def execute(cls, result, chunk_index=0, previous=None, loop_chunk=None, apply_sigma_shift=True, seed=None):
        graph, outputs = prepare_output(result, chunk_index, previous, loop_chunk, apply_sigma_shift, seed)
        return io.NodeOutput(*outputs, expand=graph)


class NGProjectRender(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGProjectRender", display_name="H3 Render Sequence", category=CATEGORY,
                         description="Render the complete planned project through ComfyUI's native loop and sampler, with progress and interrupt.",
                         inputs=[NGResult.Input("sequence")], outputs=render_outputs(), enable_expand=True)

    @classmethod
    def execute(cls, sequence):
        graph, outputs = render_project(sequence)
        return io.NodeOutput(*outputs, expand=graph)


class NGProjectChunks(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGProjectChunks", display_name="NG Project Chunks", category=CATEGORY + "/Technical", is_dev_only=True,
                         inputs=[NGResult.Input("sequence")], outputs=[NGChunk.Output(is_output_list=True)])

    @classmethod
    def execute(cls, sequence):
        return io.NodeOutput(jobs(sequence.project))


NODES = [NGDirectorOutput, NGProjectRender, NGProjectChunks]
