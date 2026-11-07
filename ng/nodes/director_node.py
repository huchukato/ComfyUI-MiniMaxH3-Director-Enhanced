"""NG Director: the idea, the length, the shots and the context items in; one job per chunk out.

It renders nothing. Wire `chunks` into a Start Loop (List mode) and the loop body renders one chunk per iteration.
"""
from comfy_api.latest import io

from ..core.chunks import ContinuityPlan
from ..core.context import ContextItem, DirectorContext
from ..core.limits import DEFAULT_CHUNK_SECONDS, DEFAULT_SOUNDSCAPE, PIN_AUDIO_DEFAULT
from ..adapters.probe import image_size
from ..core.project import describe, jobs, plan_project
from .context_nodes import CATEGORY, NGContext

NGChunk = io.Custom("NG_CHUNK")
MODES = ["auto", "fl2va", "ref2va"]
CONTINUITY = ["video_audio", "video", "none"]
PIN_FRAMES = ["22", "5", "39", "56"]


class NGDirector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        contexts = io.Autogrow.TemplatePrefix(input=NGContext.Input("context"), prefix="context_", min=0, max=15)
        return io.Schema(
            node_id="NGDirector", display_name="NG Chunk Planner", category=CATEGORY + "/Custom loop",
            description="Plans a video of any length as chunks of H3 runs. Describe it, add context items, wire the chunks into a loop.",
            inputs=[
                io.String.Input("idea", multiline=True, default="", tooltip="What the video is about. Without shots below, this carries the whole project."),
                io.String.Input("shots", multiline=True, default="", tooltip="Optional. One shot per line: 0-8: Alice enters the station.  Lines below a shot belong to it; "
                                "@Alice says: ... writes dialogue."),
                io.Float.Input("project_seconds", default=10.0, min=0.5, max=3600.0, step=0.1, tooltip="Length of the finished video. Chunks sit on H3's frame grid, so it can differ by a fraction of a second."),
                io.Float.Input("chunk_seconds", default=0.0, min=0.0, max=30.0, step=0.5, advanced=True,
                               tooltip="Target length of one H3 run. 0 = automatic (%.0f s)." % DEFAULT_CHUNK_SECONDS),
                io.Int.Input("width", default=768, min=0, max=16384, step=32, tooltip="0 together with height 0: the size of the first picture, as H3 picks it."),
                io.Int.Input("height", default=1152, min=0, max=16384, step=32, tooltip="0 together with width 0: the size of the first picture, as H3 picks it."),
                io.Combo.Input("mode", options=MODES, default="auto", advanced=True, tooltip="auto: references selected -> ref2va, otherwise fl2va."),
                io.Combo.Input("continuity", options=CONTINUITY, default="video_audio", advanced=True,
                               tooltip="How a chunk continues the one before: video_audio pins the last frames and the last second of sound; video only the frames; none = independent clips."),
                io.Combo.Input("pin_frames", options=PIN_FRAMES, default="22", advanced=True, tooltip="Frames of the previous chunk pinned in front of the next. 22 costs 0.9 s per join."),
                io.String.Input("soundscape", default=DEFAULT_SOUNDSCAPE, tooltip="Ambience of the whole video; N/A for silence."),
                io.String.Input("music", default="", tooltip="Score of the whole video; N/A for none."),
                io.String.Input("prepend_text", default="", force_input=True, optional=True, tooltip="Text in front of every prompt, for example LoRA trigger words."),
                io.Autogrow.Input("contexts", template=contexts, optional=True),
            ],
            outputs=[NGChunk.Output(display_name="chunks", is_output_list=True), io.String.Output(display_name="warnings"),
                     io.String.Output(display_name="plan")],
        )

    @classmethod
    def execute(cls, idea, shots, project_seconds, chunk_seconds, width, height, mode, continuity, pin_frames,
                soundscape, music, prepend_text="", contexts=None):
        items = tuple(c for c in (contexts or {}).values() if isinstance(c, ContextItem))
        context = DirectorContext(idea=idea, project_seconds=project_seconds, width=width, height=height, mode=mode, shots_text=shots,
                                  soundscape=soundscape, music=music, prepend_text=prepend_text or "", items=items)
        plan = ContinuityPlan(mode=continuity, video_frames=int(pin_frames), audio_frames=PIN_AUDIO_DEFAULT)
        project = plan_project(context, chunk_seconds, plan, image_size)
        return io.NodeOutput(jobs(project), "\n".join(str(i) for i in project.issues), describe(project))


NODES = [NGDirector]
