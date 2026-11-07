"""MiniMax H3 Enhance Prompt — a local vision model writes the prompt from your references.

The node hands up to nine reference images plus a one-line wish to Ollama / LM Studio /
any OpenAI-compatible endpoint, and returns text meant for the Director's `global_prompt`
input. The same images come back out of `ref_images`, so what the model described is
exactly what the Director conditions on.

The single thing that has to be right here: the Director already compiles a structured
MiniMax prompt (subject_definitions / retention_analysis / detailed_description /
overall_soundscape / non_diegetic_music). The global prompt is one ingredient inside that.
If the VLM emits section labels or reference numbers of its own, you get structure nested
inside structure and numbering that collides with the Director's own — so the system
prompts forbid both, and `_clean()` removes them anyway when the model ignores that.
"""
import logging
import re

import torch

from comfy_api.latest import io

from . import minimax_media as media
from .minimax_core import extra

log = logging.getLogger(__name__)

MAX_IMAGES = 9          # matches plan.MAX_REF_IMAGES (ref2va path, from the model card)

PRESET_GLOBAL = "global (scene + style)"
PRESET_STORYBOARD = "storyboard (shots + timings)"

# Length guidance below is the model card's own: "For generation tasks, detailed_description
# is normally 350-500 English words." When the timeline carries no shot text, the global
# prompt IS the whole detailed_description, so it needs that length rather than a lead-in.
_CAMERA = """CAMERA VOCABULARY - use only these motion types:
Zoom In, Zoom Out, Push In, Pull Out, Pan Left, Pan Right, Truck Left, Truck Right,
Tilt Up, Tilt Down, Pedestal Up, Pedestal Down, Arc Shot, Tracking Shot, Static Shot,
Shake Slightly, Shake Strongly, POV, Roll Clockwise, Roll Counterclockwise.
Add amplitude ("with small amplitude" / "with large amplitude") and speed ("at slow speed" /
"at fast speed") only when they carry meaning. Camera motion is written as a natural English
action within the shot, never stacked as separate labels at the end of a sentence.
Example: "The camera pushes in with small amplitude at slow speed toward the folded letter
in her hands."
"""

_AUDIO = """AUDIO
End with exactly two lines, in this order, as the last two lines, with no blank line
between them and nothing after them.

The first line starts with "Audio: " and then one to four sentences of ambience, physical
action sounds and non-verbal human sounds - wind, rain, traffic, footsteps, fabric,
impacts, breathing, laughter. No dialogue, no singing, no diegetic music. Write "Audio: N/A"
only if total silence was asked for.

The second line starts with "Music: " and then one to three sentences describing score the
characters cannot hear: instrumentation, tempo, rhythm, dynamic change. No mood words, no
explanation of what the music conveys. Write "Music: N/A" if there should be no score.

Write the sentences directly after the colon. Do not wrap them in angle brackets, braces,
parentheses or quotation marks.
"""

_FORBIDDEN = """NEVER WRITE
- Any section label: subject_definitions, summary, retention_analysis,
  detailed_description, integrated_multimodal_description, overall_soundscape,
  non_diegetic_music. A separate tool adds them; a second set would nest structure inside
  structure.
- <Picture 1>, <Subject 1>, <Video 1>, <Audio 1> or any numbered reference tag. That tool
  assigns the numbers and yours would collide with them.
- Talk about the input: no "Image 1 shows", no "in the second photo", no "the reference
  images". Describe what is in them.
- Markdown of any kind: no headings, bullets, bold, code fences, no wrapping quotes.
- Any preamble, commentary, question, apology or explanation of your choices.

OUTPUT
Only the prompt text. Nothing before it, nothing after it.
"""

SYSTEM_GLOBAL = """You write the opening block of a MiniMax-H3 video prompt.

You receive reference images and a short, informal wish from the user. Your output is
inserted verbatim into a larger, already-structured MiniMax prompt that a separate tool
compiles. That tool adds every section label, the shot markers, all timestamps and all
reference numbering. You write only the opening block.

LENGTH
About {budget} English words for the description, then the two audio lines. Stop there.

FORM
One or two paragraphs of flowing English prose. Never a list. Never a heading. The words
below name what the prose has to cover - they are not labels to print. Writing "Style and
format:" or "Lighting:" into your answer is wrong; write the sentence instead.

Open by naming the visual style and format, chosen from: Cinematic, live-action,
2D-animated, 3D CG, claymation, watercolor, vintage film - derived from the reference
images when they show one. Then the opening framing and composition, e.g. "a medium-wide
shot frames ...". Then the subjects: for every person, animal or object that matters,
the visible identity - age, build, hair, face, clothing with colours, distinctive props.
Describe them in words; never number them. Then the environment: location, key props, time
of day, weather. Then the lighting: direction, hardness, colour temperature, visible
practical sources. Then the actions and state changes, and finally how the camera behaves,
written as a natural English action inside the sentence.

Every detail must correspond to something visible or audible. Do not write intentions,
feelings, symbolism or backstory, and do not reduce the text to a plot summary.

ON-SCREEN TEXT
Any sign, banner, label or subtitle actually visible goes in English double quotation
marks, verbatim and untranslated: A red neon sign reading "OPEN" glows above the doorway.

%s
%s
%s""" % (_CAMERA, _AUDIO, _FORBIDDEN)

SYSTEM_STORYBOARD = """You write the shot-by-shot body of a MiniMax-H3 video prompt.

You receive reference images, a short informal wish from the user, and the target duration
of the video in seconds. Your output is inserted verbatim into a larger, already-structured
MiniMax prompt. The surrounding tool adds every section label and all reference numbering.
You write the shot sequence and nothing else.

OPENING
Begin with one or two sentences establishing style and initial composition, before the
first shot marker. Style is one of: Cinematic, live-action, 2D-animated, 3D CG, claymation,
watercolor, vintage film - derived from the reference images when they show one.

SHOT NOTATION
- First shot: "[Shot 1] " with NO timestamp.
- Every later shot: "[Shot N] At MM:SS.mmm, " - two-digit minutes, two-digit seconds,
  three-digit milliseconds. Example: "[Shot 2] At 00:03.500, the camera cuts to a close-up
  of steam rising from the sliced bread."
- Cut times strictly increase and all fall inside the given duration.
- Shots follow each other as continuous prose separated by a single space. No line breaks
  between shots, no list, no numbering other than the [Shot N] marker.

WHEN TO CUT
A cut should introduce new information about the subject, space, state, viewpoint, or time.
If only the distance or a slight angle needs to change, prefer camera motion. A five-second
video is usually one or two shots.
Cut wording: "the camera cuts to", "the shot cuts to", "the shot transitions to", "the shot
changes to", "the shot switches to". Use cross-dissolve, fade or wipe only when asked for.

WHAT EACH SHOT MUST ESTABLISH, in this order:
composition -> subject appearance and position -> environment and lighting -> actions and
state changes -> camera movement -> current sound.
These name what the prose has to cover; they are not labels to print. Never write
"composition:" or "lighting:" into your answer - write the sentence instead.

LENGTH
About {budget} English words in total. Dialogue-dense content prioritises fitting the
complete spoken timeline over reaching a word count.

ON-SCREEN TEXT
Any sign, banner, label or subtitle actually visible goes in English double quotation
marks, verbatim and untranslated.

%s
%s
%s""" % (_CAMERA, _AUDIO, _FORBIDDEN)

_SYSTEM = {PRESET_GLOBAL: SYSTEM_GLOBAL, PRESET_STORYBOARD: SYSTEM_STORYBOARD}

# The guide's own figure, used when the budget is switched off.
_GUIDE_WORDS = "350 to 500"


SYSTEM_AUDIO_ONLY = """You add the two sound lines to a video prompt.

You are given the finished visual description of a video. Reply with exactly two lines and
nothing else.

The first line starts with "Audio: " and then one to four sentences of ambience, physical
action sounds and non-verbal human sounds that fit that description - wind, rain, traffic,
footsteps, fabric, impacts, breathing, laughter. No dialogue, no singing, no diegetic music.

The second line starts with "Music: " and then one to three sentences describing score the
characters cannot hear: instrumentation, tempo, rhythm, dynamic change. No mood words, no
explanation of what the music conveys.

No preamble, no commentary, no markdown, no quotation marks, no angle brackets. Two lines,
then stop."""


def system_for(preset, max_words):
    """The preset's instructions with the user's actual word budget filled in.

    Hardcoding "350 to 500" made the widget a lie: the model aimed at 500 whatever the
    setting, and the surplus was silently trimmed afterwards.
    """
    template = _SYSTEM.get(preset, SYSTEM_GLOBAL)
    return template.replace("{budget}", str(int(max_words)) if max_words else _GUIDE_WORDS)

# --------------------------------------------------------------------------------------
# post-processing: what the model was told not to write, removed when it wrote it anyway
# --------------------------------------------------------------------------------------

_SECTION_LABELS = ("subject_definitions", "summary", "retention_analysis",
                   "detailed_description", "integrated_multimodal_description",
                   "overall_soundscape", "non_diegetic_music")
_RE_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")
_RE_LABEL = re.compile(r"^\s*(?:%s)\s*:\s*" % "|".join(_SECTION_LABELS), re.I | re.M)
_RE_REFTAG = re.compile(r"<\s*(?:picture|subject|video|audio|image)\s*\d+\s*>", re.I)
_RE_SHOT = re.compile(r"\[\s*shot\s*\d+\s*\]\s*", re.I)
# "[Shot 1] At 00:00.000," — the guide is explicit that the first shot carries no
# timestamp, and the system prompt says so, but the model writes one anyway often enough
# that it belongs in the filter rather than in more instruction text.
_RE_SHOT1_TIME = re.compile(
    r"(\[\s*shot\s*1\s*\]\s*)At\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*,\s*", re.I)
_RE_TIMESTAMP = re.compile(r"\bAt\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*,\s*", re.I)
_RE_MD_HEAD = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_RE_MD_BULLET = re.compile(r"^\s{0,3}[-*+]\s+", re.M)
_RE_BLANKS = re.compile(r"\n{3,}")
# Instruction words echoed back as labels. Small models answer a numbered brief point by
# point; the system prompt forbids it, this catches the ones that do it anyway.
_RE_ECHO = re.compile(
    r"^\s*(?:style(?: and format)?|form|length|opening framing(?: and composition)?|"
    r"composition|subjects?|environment|lighting|actions?(?: and state changes)?|"
    r"camera(?: movement| behaviour| behavior)?|on-screen text|output)\s*:\s*", re.I | re.M)


def _first_sentences(value, count):
    """Keep at most `count` sentences. The guide allows 1-4 for the soundscape and 1-3 for
    the score; a small model asked for "one to four sentences" wrote 210 words in testing."""
    parts = [p for p in _RE_SENTENCE.split(value.strip()) if p]
    return " ".join(parts[:count]).strip() if len(parts) > count else value.strip()


def _unwrap(value):
    """Strip a bracket or quote pair the model wrapped a value in.

    The system prompt used to show placeholders as <one to four sentences ...>; small
    models copied the angle brackets into the answer. The wording no longer does that,
    but the guard is one line and the failure is silent.
    """
    value = value.strip()
    for opener, closer in (("<", ">"), ("{", "}"), ("[", "]"), ("(", ")"),
                           ('"', '"'), ("'", "'")):
        if len(value) > 1 and value.startswith(opener) and value.endswith(closer):
            value = value[1:-1].strip()
    return value


_RE_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _trim_to_words(text, budget):
    """Cut the body back to `budget` words, ending on a sentence.

    A 9B model told "350 to 500 words" happily wrote 6446 in testing. The token cap on the
    request stops the runaway; this puts the tail on a sentence boundary instead of
    mid-word. The Audio:/Music: lines are extracted before this runs, so trimming can
    never lose them.
    """
    words = text.split()
    if budget <= 0 or len(words) <= budget:
        return text
    kept, used = [], 0
    for sentence in _RE_SENTENCE.split(text):
        n = len(sentence.split())
        if used + n > budget:
            break
        kept.append(sentence)
        used += n
    if not kept:                      # one sentence longer than the whole budget
        return " ".join(words[:budget]).rstrip(",;:") + "."
    return " ".join(kept).strip()


def clean_prompt(text, preset, max_words=0):
    """Strip everything the compiler owns, so the two cannot fight over structure."""
    text = media.strip_thinking(text)
    text = _RE_FENCE.sub("", text).strip()
    text = _RE_LABEL.sub("", text)
    text = _RE_REFTAG.sub("", text)
    text = _RE_MD_HEAD.sub("", text)
    text = _RE_MD_BULLET.sub("", text)
    text = text.replace("**", "")

    if preset != PRESET_STORYBOARD:
        # shot markers and their timestamps belong to the timeline, not to the global block
        text = _RE_SHOT.sub("", text)
        text = _RE_TIMESTAMP.sub("", text)
    else:
        text = _RE_SHOT1_TIME.sub(r"\1", text)
        if text.strip() and not _RE_SHOT.search(text):
            # Storyboard prose with no markers at all is just a global prompt with extra
            # steps — measured in 1 of 4 runs. What it describes *is* one shot, so label
            # it as one and the notation is valid again.
            text = "[Shot 1] " + text.lstrip()

    # a wrapping pair of quotes the model added around the whole answer
    stripped = text.strip()
    if len(stripped) > 2 and stripped[0] in "\"'" and stripped[-1] == stripped[0]:
        text = stripped[1:-1]

    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    # split_audio_music() reads line by line and stops at a blank line, so the Audio: and
    # Music: lines have to sit together at the end with nothing blank between them
    body, audio, music, taken = [], None, None, set()
    labels = ("audio:", "sound:", "sfx:", "music:", "score:")
    for index, ln in enumerate(lines):
        if index in taken:
            continue
        low = ln.strip().lower()
        if low.startswith(labels) and not ln.partition(":")[2].strip():
            # A label alone on its line carries the next paragraph: Qwen3-VL 4B wrote "Audio:" and the sound below it,
            # which became an empty "Audio:" line at the end and the sound as loose prose.
            following = next((i for i in range(index + 1, len(lines)) if lines[i].strip()), None)
            if following is not None and not lines[following].strip().lower().startswith(labels):
                taken.add(following)
                ln = ln.rstrip() + " " + lines[following].strip()
                low = ln.strip().lower()
        if low.startswith(("audio:", "sound:", "sfx:")) and audio is None:
            head, _, rest = ln.strip().partition(":")
            audio = "%s: %s" % (head.strip(), _first_sentences(_unwrap(rest), 4))
        elif low.startswith(("music:", "score:")) and music is None:
            head, _, rest = ln.strip().partition(":")
            music = "%s: %s" % (head.strip(), _first_sentences(_unwrap(rest), 3))
        else:
            body.append(_RE_ECHO.sub("", ln))
    out = _RE_BLANKS.sub("\n\n", "\n".join(body).strip())
    if max_words:
        out = _trim_to_words(out, max_words)
    tail = [x for x in (audio, music) if x]
    if tail:
        out = (out + "\n" + "\n".join(tail)).strip()
    return out


def _tensor_to_b64(images, max_edge, quality):
    """ComfyUI IMAGE batch -> JPEG base64, downscaled.

    Nine reference frames at full resolution are megabytes of JSON and minutes of VLM
    time; for "describe what you see" a 768 px long edge is plenty.
    """
    from PIL import Image
    import base64
    import io as _io

    out = []
    for frame in images:
        arr = (frame.clamp(0, 1) * 255.0).to(torch.uint8).cpu().numpy()
        img = Image.fromarray(arr)
        if img.mode != "RGB":
            img = img.convert("RGB")
        longest = max(img.width, img.height)
        if max_edge > 0 and longest > max_edge:
            scale = max_edge / float(longest)
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                             Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    return out


def _collect(images_dict):
    """Autogrow hands over {"image0": tensor, ...}; unconnected slots are simply absent,
    and a connected-but-unresolved one can still be None."""
    if not images_dict:
        return []
    def order(name):
        digits = "".join(ch for ch in name if ch.isdigit())
        return int(digits) if digits else 0
    return [images_dict[k] for k in sorted(images_dict, key=order)
            if images_dict[k] is not None]


class MiniMaxH3EnhancePrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3EnhancePromptCS",
            display_name="MiniMax H3 Enhance Prompt",
            category="MiniMax H3/Legacy",
            description=(
                "Turns a one-line idea plus reference images into a MiniMax-H3 prompt, "
                "using a local vision model (Ollama / LM Studio / OpenAI-compatible). "
                "Wire `prompt` into the Director's global_prompt and `ref_images` into its "
                "ref_images, so the model describes exactly the images H3 conditions on."
            ),
            inputs=[
                io.Autogrow.Input(
                    "images",
                    io.Autogrow.TemplatePrefix(
                        io.Image.Input("image", optional=True,
                                       tooltip="A reference image. A new socket appears as you "
                                               "connect; disconnecting closes the gap."),
                        prefix="image", min=0, max=MAX_IMAGES),
                    optional=True,
                    tooltip="Up to %d reference images. They are described by the vision model "
                            "and passed straight through to ref_images." % MAX_IMAGES),
                io.String.Input("idea", multiline=True, default="",
                                tooltip="What you want, in plain words. The vision model turns "
                                        "this plus the images into a MiniMax-shaped prompt."),
                io.Combo.Input("preset", options=[PRESET_GLOBAL, PRESET_STORYBOARD],
                               default=PRESET_GLOBAL,
                               tooltip="'global' writes scene, style, subjects and lighting and "
                                       "leaves the shots to your timeline. 'storyboard' writes "
                                       "the whole shot sequence with timestamps — use it only "
                                       "when your timeline segments carry no prompt text, or "
                                       "the two shot numberings will collide."),
                io.String.Input("system_prompt", multiline=True, default="", optional=True,
                                tooltip="Overrides the built-in instructions. Leave empty to use "
                                        "the preset's own, which is derived from MiniMax's "
                                        "prompt-writing guide."),
                io.Float.Input("duration_seconds", default=5.0, min=1.0, max=60.0, step=0.5,
                               optional=True,
                               tooltip="Told to the model so its timestamps fit. Match the "
                                       "Director's duration."),
                io.Combo.Input("provider", options=["ollama", "lmstudio", "custom"],
                               default="ollama", optional=True,
                               tooltip="Where the vision model runs."),
                io.String.Input("base_url", default="", optional=True,
                                tooltip="Empty = the provider's default (Ollama "
                                        "http://127.0.0.1:11434, LM Studio "
                                        "http://127.0.0.1:1234). http:// is added if you "
                                        "leave it off. Host and port; a trailing /v1 is fine."),
                io.String.Input("model", default="", optional=True,
                                tooltip="Model name. Must be a VISION model — a text-only model "
                                        "will ignore your images without saying so. Empty falls "
                                        "back to the provider default."),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True, optional=True,
                             tooltip="ComfyUI caches node outputs, so an unchanged input means "
                                     "the model is never asked again. Change this to force a "
                                     "fresh answer."),
                io.Int.Input("max_image_size", default=768, min=128, max=2048, step=64,
                             optional=True,
                             tooltip="Long edge the images are downscaled to before they are "
                                     "sent. Larger costs time and buys little."),
                io.Int.Input("max_words", default=500, min=0, max=2000, step=50,
                             optional=True,
                             tooltip="Hard limit on the description. MiniMax's guide puts a "
                                     "detailed_description at 350-500 words; small models "
                                     "ignore that when asked politely, so the request is "
                                     "capped and the result trimmed to a sentence end. "
                                     "0 disables both."),
                io.Boolean.Input("unload_after", default=True, optional=True,
                                 tooltip="Drop the vision model from VRAM when done, so it is "
                                         "not still resident while H3 samples. Turn off only "
                                         "while iterating on prompts — reloading costs seconds, "
                                         "an OOM costs the render. Works with Ollama, and with "
                                         "llama-server in router mode. A plain llama-server or "
                                         "LM Studio cannot be told to let go over HTTP — give "
                                         "those an idle timeout of their own "
                                         "(llama.cpp: --sleep-idle-seconds N)."),
                io.Combo.Input("on_error", options=["passthrough", "fail"],
                               default="passthrough", optional=True,
                               tooltip="'passthrough' hands your raw idea on and warns, so a "
                                       "stopped Ollama does not kill the whole run."),
                # Last, and it always will be: widgets are serialised positionally, so
                # inserting one anywhere else hands every value after it to the wrong
                # input in workflows already saved (see MAINTAINING, trap 9).
                io.String.Input("api_key_env", default="", optional=True,
                                tooltip="Name of an ENVIRONMENT VARIABLE holding the API key "
                                        "for a cloud endpoint — not the key itself. Widget "
                                        "values are saved inside the workflow, so a key typed "
                                        "here would travel with every copy you share. Empty "
                                        "falls back to MINIMAX_DIRECTOR_VLM_API_KEY, then "
                                        "OPENAI_API_KEY. Local Ollama and LM Studio need none."),
            ],
            outputs=[
                io.String.Output(display_name="prompt",
                                 tooltip="Wire into the Director's global_prompt."),
                io.Image.Output(display_name="ref_images",
                                tooltip="The same images, batched. Wire into the Director's "
                                        "ref_images."),
                io.Float.Output(display_name="duration_seconds",
                                tooltip="The duration you set above, passed on so you only "
                                        "type it once. Wire into the Director's `duration` "
                                        "input (the connection-only one, in seconds)."),
            ],
        )

    @classmethod
    async def execute(cls, images=None, idea="", preset=PRESET_GLOBAL, system_prompt="",
                      duration_seconds=5.0, provider="ollama", base_url="", model="",
                      seed=0, max_image_size=768, max_words=500, unload_after=True,
                      on_error="passthrough", api_key_env="") -> io.NodeOutput:
        tensors = _collect(images)
        if len(tensors) > MAX_IMAGES:
            log.warning("[MiniMaxEnhance] %d images connected, MiniMax H3 takes at most %d — "
                        "dropping the rest.", len(tensors), MAX_IMAGES)
            tensors = tensors[:MAX_IMAGES]

        batched = None
        if tensors:
            flat = []
            for t in tensors:
                flat.extend([t[i:i + 1] for i in range(t.shape[0])])
            flat = flat[:MAX_IMAGES]
            sizes = {tuple(t.shape[1:3]) for t in flat}
            if len(sizes) > 1:
                log.warning("[MiniMaxEnhance] reference images have different sizes %s — "
                            "scaling them to the first one.", sorted(sizes))
            batched = extra("nodes_post_processing", "batch_images").batch_images(flat)

        provider = (provider or "ollama").lower()
        defaults = media._PROVIDER_DEFAULTS.get(provider, media._PROVIDER_DEFAULTS["ollama"])
        url = media.normalize_base_url(base_url, defaults["url"])
        model_name = model or defaults["model"]
        # the widget names an environment variable; the key is read here and never stored
        api_key = media.resolve_api_key({"api_key_env": api_key_env})
        system = (system_prompt or "").strip() or system_for(preset, max_words)

        user = (idea or "").strip() or "Describe what these images show as a video."
        if preset == PRESET_STORYBOARD:
            user = "%s\n\nTarget duration: %.1f seconds." % (user, float(duration_seconds))
        # Recency matters more than instruction count for small models: without this
        # reminder qwen3.5:9b dropped the two closing lines in roughly half the runs.
        user += ("\n\nRemember: finish with the Audio: line and then the Music: line, "
                 "and write nothing after them.")

        b64 = _tensor_to_b64(batched, int(max_image_size), 88) if batched is not None else []
        log.info("[MiniMaxEnhance] %s via %s (%s, model '%s'%s), %d image(s)...",
                 "storyboard" if preset == PRESET_STORYBOARD else "global",
                 provider, url, model_name, ", authenticated" if api_key else "", len(b64))

        # The token cap is only a runaway backstop; the shaping is done afterwards by
        # _trim_to_words and _first_sentences. It has to stay generous, because the model
        # writes the description first and the Audio:/Music: lines last — cut it too close
        # and those never get written, which leaves the Director's overall_soundscape and
        # non_diegetic_music empty. Measured: 300 words at 600 tokens lost them entirely.
        cap = int(max_words * 2.2) + 400 if max_words else None
        # Ollama drops the model right after answering when keep_alive is 0. That matters
        # here: the VLM and H3 are usually on the same card, and a 7B vision model still
        # resident when sampling starts is the difference between a render and an OOM.
        keep_alive = 0 if unload_after else 300
        # keep_alive is Ollama's own field; for everyone else the release happens in the
        # `finally` below, over whatever protocol that server actually speaks.
        try:
            raw = await media.vlm_generate(b64, user, provider, url, model_name,
                                           system_prompt=system, timeout=300,
                                           max_tokens=cap, keep_alive=keep_alive,
                                           api_key=api_key)
            prompt = clean_prompt(raw, preset, max_words=int(max_words))
            if not prompt:
                raise media.VLMError("The model returned nothing usable.")

            # Small models reliably drop the two closing lines after a long description --
            # qwen3.5:9b managed both in 0 of 4 measured runs. Asking again, on its own,
            # is far more dependable than asking harder in the first prompt, and it only
            # costs a few seconds when it is actually needed.
            has_audio = re.search(r"^\s*(?:audio|sound|sfx)\s*:", prompt, re.I | re.M)
            has_music = re.search(r"^\s*(?:music|score)\s*:", prompt, re.I | re.M)
            if not (has_audio and has_music):
                log.info("[MiniMaxEnhance] no %s line — asking for the sound lines separately.",
                         "Audio/Music" if not (has_audio or has_music)
                         else ("Music" if has_audio else "Audio"))
                try:
                    tail = await media.vlm_generate(
                        [], prompt, provider, url, model_name,
                        system_prompt=SYSTEM_AUDIO_ONLY, timeout=120, max_tokens=300,
                        keep_alive=keep_alive, api_key=api_key)
                    merged = clean_prompt("%s\n%s" % (prompt, tail), preset)
                    if re.search(r"^\s*(?:audio|sound|sfx)\s*:", merged, re.I | re.M):
                        prompt = merged
                except media.VLMError as e:
                    log.warning("[MiniMaxEnhance] sound lines unavailable: %s", e)
        except Exception as e:
            # Deliberately broad: 'passthrough' promises the run survives, and the thing
            # that took a run down in practice was aiohttp rejecting a URL without a
            # scheme -- not a VLMError at all. The traceback still reaches the console.
            if on_error == "fail":
                if isinstance(e, media.VLMError):
                    raise ValueError("MiniMax H3 Enhance Prompt: %s" % e)
                raise
            log.warning("[MiniMaxEnhance] %s — passing your text through unchanged.", e,
                        exc_info=not isinstance(e, media.VLMError))
            prompt = (idea or "").strip()
        finally:
            # Backstop for keep_alive, and it also runs when the call blew up half way —
            # that is exactly when a model is left sitting in VRAM.
            if unload_after:
                await media.unload_model(provider, url, model_name, api_key)

        log.info("[MiniMaxEnhance] %d chars:\n%s", len(prompt), prompt)
        return io.NodeOutput(prompt, batched, float(duration_seconds))


NODE_CLASS_MAPPINGS = {"MiniMaxH3EnhancePromptCS": MiniMaxH3EnhancePrompt}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3EnhancePromptCS": "MiniMax H3 Enhance Prompt"}
