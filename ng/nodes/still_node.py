"""The nodes of the Director's Pictures output (core/stills.py, adapters/stills.py): one latent frame per shot inside the
render loop, and the pictures after it."""
import logging

import torch
from comfy_api.latest import io

from ..adapters import stills
from ..adapters.media import MediaError
from .context_nodes import CATEGORY
from .director_node import NGChunk


def _job(chunk):
    return chunk[0] if isinstance(chunk, list) else chunk


def _still(job):
    return job.project.stills[job.index]


class NGStillLatent(io.ComfyNode):
    """Inside the loop, after NG Chunk Conditioning: the part's clip latent replaced by one frame (with the source and its
    edit mask, when the shot changes a picture)."""
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGStillLatent", display_name="NG Still Latent", category=CATEGORY + "/Technical", is_dev_only=True,
                         inputs=[NGChunk.Input("chunk"), io.Latent.Input("latent"), io.Vae.Input("vae")],
                         outputs=[io.Latent.Output()])

    @classmethod
    def execute(cls, chunk, latent, vae):
        job = _job(chunk)
        still, context = _still(job), job.project.context
        try:
            source = stills.load_source(still) if still.source and still.mask else None
            mask = stills.load_mask(still.mask, context.width, context.height) if source is not None else None
        except MediaError as error:
            raise ValueError("picture %d: %s" % (job.index + 1, error)) from error
        return io.NodeOutput(stills.still_latent(context.width, context.height, vae, source, mask))


class NGStillCollect(io.ComfyNode):
    """After the loop: every picture decoded, the source kept outside an edit mask, and saved to input/h3-director-stills,
    where every Image card can choose it."""
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGStillCollect", display_name="NG Still Collect", category=CATEGORY + "/Technical", is_dev_only=True,
                         is_input_list=True,
                         inputs=[io.Latent.Input("latents"), NGChunk.Input("chunks"), io.Vae.Input("vae")],
                         outputs=[io.Image.Output(display_name="images"), io.Audio.Output(display_name="audio"),
                                  io.String.Output(display_name="warnings")])

    @classmethod
    def execute(cls, latents, chunks, vae):
        vae = vae[0]
        pictures, saved = [], []
        for latent, job in zip(latents, chunks):
            still, context = _still(job), job.project.context
            image = stills.decode(vae, latent)
            if still.source and still.mask:
                image = stills.paste_back(image, stills.load_source(still),
                                          stills.load_mask(still.mask, image.shape[2], image.shape[1]))
            name = stills.save(image, "shot%02d" % (job.index + 1))
            saved.append(name)
            logging.info("[H3 Director] picture %d saved as input/%s", job.index + 1, name)
            pictures.append(image)
        silent = {"waveform": torch.zeros(1, 2, 32000 * max(1, len(pictures))), "sample_rate": 32000}
        note = "Saved for the Image cards: " + ", ".join(saved)
        return io.NodeOutput(torch.cat(pictures), silent, note)


NODES = [NGStillLatent, NGStillCollect]
