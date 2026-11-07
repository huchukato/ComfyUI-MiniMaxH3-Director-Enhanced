"""Build explicit AI jobs with ComfyUI's Generate Text, using its model management."""
import json

from comfy_execution.graph_utils import GraphBuilder

from ... import minimax_media as media
from ..core.analysis import analysis_prompt, parse_suggestion
from ..core.auto_direct import direct_tokens, direction_prompt, parse_direction, timing_hints
from ..core.builder import SYSTEM as BUILD_SYSTEM, parse_plan, pictures, plan_prompt, plan_tokens, read_quick
from ..core.fields import need_dict, read_number, read_str
from ..core.part_prompt import SYSTEM as WRITE_SYSTEM, write_tokens
from ..core.part_writer import brief, finish, write_prompt
from ..core.storyboard import read_board
from ..core.storyboard_texts import SYSTEM as STORYBOARD_SYSTEM, parse_texts, texts_prompt, texts_tokens
from ..core.system_prompts import framed, for_node
from . import probe
from .ai_provider import NativeAIProvider

# MiniMax H3's own text encoder is cut to 50 of Qwen3-VL-32B's 64 layers and ships no final norm and no lm_head
# (ComfyUI says so in Qwen3VL_32BConfig). It turns a prompt into conditioning but cannot write text: a job on it ran
# about ten minutes and answered with commas. Name it before the job instead of letting it run into the timeout.
CONDITIONING_ONLY = ("This CLIP is MiniMax H3's conditioning encoder (Qwen3-VL-32B cut to 50 layers, no output head). "
                     "It cannot write text. Connect a generative model to the AI Loader instead, e.g. Load CLIP with "
                     "qwen3vl_4b or qwen3vl_8b (type stable_diffusion), or switch the AI Loader to Local (Ollama).")


def conditioning_only(clip):
    """True for a loaded CLIP that is H3's conditioning encoder."""
    model = getattr(clip, "cond_stage_model", None)
    return any(kind.__name__ == "MiniMaxH3TEModel" for kind in type(model).__mro__)


def conditioning_file(name, model_type):
    return model_type == "minimax" or "minimax_h3" in name.lower()


def _write_facts(payload):
    # The native encoder takes one picture at most; a part is written from the cards' descriptions instead.
    facts = brief(need_dict(payload["director"], "director"), payload["contexts"], int(read_number(payload, "part", "request", minimum=0)),
                  probe.duration_seconds, read_quick(payload))
    facts["shown"] = []
    return facts


def request_prompt(action, payload, config):
    need_dict(payload, "AI request")
    if action == "direct":
        director = need_dict(payload["director"], "director")
        seconds = read_number(director, "project_seconds", "director", minimum=0.1)
        idea = read_str(director, "idea", "director").strip()
        timing = timing_hints(director, payload["contexts"], probe.duration_seconds)
        return direction_prompt(idea, seconds, payload["contexts"], read_str(director, "shots", "director", ""), timing), None
    if action == "write":
        return write_prompt(_write_facts(payload)), None
    if action == "storyboard":
        # Generate Text takes one picture at most: the cards' descriptions carry the characters instead.
        return texts_prompt(read_board(payload.get("board") or ""), payload["contexts"]), None
    if action == "build":
        director = need_dict(payload["director"], "director")
        timing = timing_hints(director, payload["contexts"], probe.duration_seconds)
        # Generate Text takes one picture: the first card's is shown (it set the style), the others go by their descriptions.
        shown = 1 if config.vision and pictures(payload["contexts"]) else 0
        return plan_prompt(read_quick(payload), read_str(director, "idea", "director", ""),
                           read_number(director, "project_seconds", "director", minimum=0.1), payload["contexts"], shown,
                           *timing), "image" if shown else None
    if action != "analyze":
        raise ValueError("Choose Analyze or Auto Direct.")
    media, widgets = payload["media"], need_dict(payload["widgets"], "context.widgets")
    if media not in ("image", "video", "audio", "text"):
        raise ValueError("Choose an image, video, audio or text context.")
    if media in ("image", "video") and not config.vision:
        raise ValueError("Vision is off on the H3 AI Loader, so the AI is not shown this picture. Switch Vision on if the "
                         "connected model reads images (Qwen3-VL does), or write the description yourself.")
    if media == "audio" and not config.audio:
        raise ValueError("Audio is off on the H3 AI Loader, so the AI is not given this sound. Qwen3-VL cannot hear; switch "
                         "Audio on only for a model that accepts audio, or write the description yourself.")
    prompt = analysis_prompt(media, widgets.get("content", ""), payload.get("offer"))
    if media == "text":
        prompt += "\n\nContext text:\n" + widgets.get("text", "")
    return prompt, media if media != "text" else None


def native_request(provider, action, request_json):
    if not isinstance(provider, NativeAIProvider):
        raise ValueError("Select CLIP / Encoder on the connected H3 AI Loader.")
    payload = json.loads(request_json)
    prompt, media = request_prompt(action, payload, provider.config)
    graph = GraphBuilder()
    clip = provider.clip
    if provider.local_model:
        if conditioning_file(provider.local_model, provider.local_type):
            raise ValueError(CONDITIONING_ONLY)
        clip = graph.node("CLIPLoader", clip_name=provider.local_model, type=provider.local_type, device="default").out(0)
    # A connected clip is only a link here; whether it is the conditioning encoder is known once it is loaded.
    clip = graph.node("NGAICheckEncoder", clip=clip).out(0)
    max_length = (direct_tokens(provider.config.max_tokens) if action == "direct"
                  else write_tokens(provider.config.max_tokens) if action == "write"
                  else plan_tokens(provider.config.max_tokens) if action == "build"
                  else texts_tokens(provider.config.max_tokens) if action == "storyboard" else provider.config.max_tokens)
    inputs = dict(clip=clip, prompt=prompt, max_length=max_length,
                  sampling_mode="off", thinking=False, use_default_template=True,
                  # The role comes from system_prompts.py and the schema framing from there too, so
                  # the two cannot be edited apart. Auto Direct plans, an Analyze describes: the same
                  # framing with the wrong role produced answers that read as the wrong task.
                  # "write" is the exception and carries no schema framing: its answer is the prose of a
                  # render part's prompt, labelled fields rather than JSON.
                  system_prompt=(WRITE_SYSTEM if action == "write" else BUILD_SYSTEM if action == "build"
                                 else STORYBOARD_SYSTEM if action == "storyboard"
                                 # The card's medium, not `media` (which only says what is sent along and is None for a
                                 # text note): with None a Text card got the generic role and Qwen3-VL 4B lost the JSON.
                                 else framed(for_node("director" if action == "direct" else "context", payload.get("media")))))
    if media:
        source = (pictures(payload["contexts"])[0][0]["widgets"]["image"] if action == "build"
                  else payload["widgets"].get(media, ""))
        loaded = graph.node("NGAIReadMedia", media=media, source=source)
        inputs["image" if media in ("image", "video") else "audio"] = loaded.out(0 if media != "audio" else 1)
    generated = graph.node("TextGenerate", **inputs)
    result = graph.node("NGAIResult", text=generated.out(0), action=action, request_json=request_json)
    return graph.finalize(), result.out(0)


def parse_result(text, action, request_json):
    payload = json.loads(request_json)
    # qwen3vl_4b_fp8_scaled sometimes decodes the user's turn again instead of answering; "not readable JSON, maybe
    # Max tokens" sent the user the wrong way.
    if text.lstrip().startswith("user\n"):
        raise ValueError("The model repeated the request instead of answering. Ask again; if it keeps doing it, "
                         "use another encoder (qwen3vl_4b_bf16 answered reliably) or Ollama.")
    if action == "write":
        return finish(text, _write_facts(payload))
    if action == "storyboard":
        return parse_texts(text.removeprefix("assistant\n"), read_board(payload.get("board") or ""), payload["contexts"])
    if action == "build":
        _, sung = timing_hints(payload["director"], payload["contexts"], probe.duration_seconds)
        return parse_plan(text, float(payload["director"]["project_seconds"]), payload["contexts"], read_quick(payload), sung)
    # Generic Qwen CLIP tokenizers can decode the assistant role header with the answer.
    text = text.removeprefix("assistant\n").strip()
    if action == "analyze":
        # The medium decides which content roles the answer may name: a picture cannot be dialogue.
        return parse_suggestion(text, payload.get("media", "text")).to_dict()
    _, sung = timing_hints(payload["director"], payload["contexts"], probe.duration_seconds)
    return parse_direction(text, float(payload["director"]["project_seconds"]), payload["contexts"],
                           payload["director"].get("shots", ""), payload.get("keep", ""), sung)
