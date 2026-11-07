"""NG Chunk Conditioning and NG Collect: the nodes inside and after the loop."""
import json
import logging
import os
import uuid

import folder_paths
from comfy_api.latest import InputImpl, io

from ...minimax_core import audio_nodes, core
from ..adapters import audio_locks, chunk_builder, collect, continuation_join, latents, resume
from ..adapters.media import MediaError
from ..core.limits import FPS, RESIZE_METHODS
from .context_nodes import CATEGORY
from .director_node import NGChunk


log = logging.getLogger(__name__)


def _job(chunk):
    """The loop hands the list item over as is, or wrapped in a one-element list; take either."""
    return chunk[0] if isinstance(chunk, list) else chunk


class _Unconnected:
    """Tells an empty optional socket from a lazy one that has not been evaluated yet (None)."""


UNCONNECTED = _Unconnected()


class NGChunkConditioning(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="NGChunkConditioning", display_name="NG Chunk Conditioning", category=CATEGORY + "/Technical", is_dev_only=True,
            description="Inside the loop: prompt, references and the pinned tail of the previous chunk for one chunk. Wire the sampler after it.",
            inputs=[
                NGChunk.Input("chunk", tooltip="The loop's list_item."),
                io.Clip.Input("clip"), io.Vae.Input("vae"),
                io.Vae.Input("audio_vae", optional=True, tooltip="Needed for voices, copied or locked audio."),
                io.Model.Input("model_fl2va", optional=True, lazy=True, tooltip="minimax_h3_fl2va_*; loaded only when the project is text/frames."),
                io.Model.Input("model_ref2va", optional=True, lazy=True, tooltip="minimax_h3_ref2va_*; loaded only when references are used."),
                io.Latent.Input("previous", optional=True, tooltip="The loop's current_iteration_value: the previous chunk's latent."),
                io.Float.Input("shift_video", default=12.0, min=0.01, max=100.0, step=0.01, advanced=True),
                io.Float.Input("shift_audio", default=3.0, min=0.01, max=100.0, step=0.01, advanced=True),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match", advanced=True),
                io.Boolean.Input("apply_sigma_shift", default=True, optional=True, advanced=True,
                                 tooltip="Disable to keep the connected model's existing H3 sampling shifts."),
                io.Combo.Input("resize_method", options=list(RESIZE_METHODS), default="crop", optional=True, advanced=True,
                               tooltip="How a first or last frame picture is fitted to the video size."),
            ],
            outputs=[io.Model.Output(display_name="model"), io.Conditioning.Output(display_name="positive"), io.Latent.Output(display_name="latent"),
                     io.String.Output(display_name="prompt")],
        )

    @classmethod
    def check_lazy_status(cls, chunk=None, model_fl2va=UNCONNECTED, model_ref2va=UNCONNECTED, **_):
        job = _job(chunk)
        if job is None:
            return []
        wanted = ("model_ref2va", "model_fl2va") if job.compiled.mode == "ref2va" else ("model_fl2va", "model_ref2va")
        have = {"model_fl2va": model_fl2va, "model_ref2va": model_ref2va}
        for name in wanted:
            if have[name] is not UNCONNECTED:
                return [name] if have[name] is None else []
        return []

    @classmethod
    def execute(cls, chunk, clip, vae, audio_vae=None, model_fl2va=None, model_ref2va=None, previous=None,
                shift_video=12.0, shift_audio=3.0, ref_image_size="match", apply_sigma_shift=True, resize_method="crop"):
        job = _job(chunk)
        if job.chunk.head_frames and not job.chunk.continuation_id:
            if previous is None:
                raise ValueError("Chunk %d needs the previous full AV latent; connect Start Loop's current_iteration_value to previous." % (job.index + 1))
            latents.validate_chunk(previous, job.project.plan.chunks[job.index - 1].sampled_frames, "Previous chunk")
        mm = core()
        wanted, other = (model_ref2va, model_fl2va) if job.compiled.mode == "ref2va" else (model_fl2va, model_ref2va)
        model = wanted if wanted is not None else other
        if model is None:
            raise ValueError("no model connected: wire a UNETLoader into model_fl2va (text/frames) and/or model_ref2va (references)")
        if wanted is None:
            log.warning("[NG] this project needs the %s model but only the other one is connected; using it.", job.compiled.mode)
        try:
            built = chunk_builder.build_chunk(job, clip, vae, audio_vae=audio_vae, previous=previous, ref_image_size=ref_image_size, mm=mm,
                                              resize_method=resize_method)
        except MediaError as error:
            raise ValueError("NG chunk %d: %s" % (job.index + 1, error)) from error
        if apply_sigma_shift:
            shifted = mm.MiniMaxH3SigmaShift.execute(model=model, shift_video=float(shift_video), shift_audio=float(shift_audio))
            model = getattr(shifted, "args", shifted)[0]
        model = audio_locks.bind_source(model, job, audio_vae)
        return io.NodeOutput(model, built.positive, built.latent, job.compiled.prompt)


class NGCollect(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="NGCollect", display_name="NG Collect", category=CATEGORY + "/Custom loop", is_input_list=True,
            description="After the loop: decode every chunk, cut off the pinned heads and join picture and sound into one video.",
            inputs=[io.Latent.Input("latents", tooltip="End Loop output (accumulate on)."), NGChunk.Input("chunks", tooltip="The Director's chunks."),
                    io.Vae.Input("vae"), io.Vae.Input("audio_vae"),
                    io.String.Input("resume_settings", optional=True, advanced=True,
                                    tooltip="Set by Render Sequence when the kept render parts are deleted once the video is put together."),
                    io.Boolean.Input("smooth_source_join", default=True, optional=True, advanced=True,
                                     tooltip="Ease the source/VAE picture difference over the first six new frames of Continue. Sound is unchanged.")],
            outputs=[io.Image.Output(display_name="images"), io.Audio.Output(display_name="audio"), io.String.Output(display_name="warnings"),
                     io.Float.Output(display_name="fps", tooltip="24, for CreateVideo. Outside the loop, unlike Director Output's fps.")],
        )

    @classmethod
    def execute(cls, latents, chunks, vae, audio_vae, resume_settings=None, smooth_source_join=None):
        project = _jobs_of(chunks)
        decode_audio = audio_nodes().vae_decode_audio
        frames, sound, issues = collect.collect_chunks(
            latents, project.plan, lambda video: _decode_video(vae[0], video), lambda audio: decode_audio(audio_vae[0], {"samples": audio}),
            restore_audio=lambda index, wave, rate: audio_locks.restore_waveform(chunks[index], wave, rate),
            restore_picture=_picture_restorer(chunks, smooth_source_join))
        # A list input: an empty field in a hand-built loop arrives as [""] (2026-10-18: Collect failed with JSONDecodeError).
        if resume_settings and resume_settings[0]:
            resume.forget(chunks, json.loads(resume_settings[0]))
        return io.NodeOutput(frames, sound, "\n".join(str(i) for i in issues), float(FPS))


def _jobs_of(chunks):
    project = chunks[0].project
    if [job.index for job in chunks] != list(range(len(project.plan.chunks))) or any(job.project is not project for job in chunks):
        raise ValueError("Connect the complete, ordered Project Chunks list from the same Director to Collect.")
    return project


def _picture_restorer(chunks, enabled):
    if enabled is not None and not enabled[0]:
        return None
    return lambda index, known, frames: continuation_join.smooth(chunks[index], known, frames)


class NGCollectVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="NGCollectVideo", display_name="NG Collect Video", category=CATEGORY + "/Custom loop", is_input_list=True,
            description="After the loop, for long projects such as a whole song: decodes one render part at a time straight into a video "
                        "file, so the frames never have to fit in memory at once. Connect SaveVideo.",
            inputs=[io.Latent.Input("latents", tooltip="End Loop output (accumulate on)."), NGChunk.Input("chunks", tooltip="The Director's chunks."),
                    io.Vae.Input("vae"), io.Vae.Input("audio_vae"),
                    io.Boolean.Input("smooth_source_join", default=True, optional=True, advanced=True,
                                     tooltip="Ease the source/VAE picture difference over the first six new frames of Continue. Sound is unchanged.")],
            outputs=[io.Video.Output(display_name="video"), io.String.Output(display_name="warnings")],
        )

    @classmethod
    def execute(cls, latents, chunks, vae, audio_vae, smooth_source_join=None):
        project = _jobs_of(chunks)
        decode_audio = audio_nodes().vae_decode_audio
        path = os.path.join(folder_paths.get_temp_directory(), "ng_collect_%s.mp4" % uuid.uuid4().hex)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        issues = collect.write_video(path, latents, project.plan, lambda video: _decode_video(vae[0], video),
                                     lambda audio: decode_audio(audio_vae[0], {"samples": audio}),
                                     restore_audio=lambda index, wave, rate: audio_locks.restore_waveform(chunks[index], wave, rate),
                                     restore_picture=_picture_restorer(chunks, smooth_source_join))
        return io.NodeOutput(InputImpl.VideoFromFile(path), "\n".join(str(i) for i in issues))


def _decode_video(vae, video):
    frames = vae.decode(video)
    return frames.reshape(-1, *frames.shape[-3:]) if frames.ndim == 5 else frames


NODES = [NGChunkConditioning, NGCollect, NGCollectVideo]
