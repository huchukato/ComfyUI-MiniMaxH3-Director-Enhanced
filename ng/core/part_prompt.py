"""The final prompt of one render part: written out by an AI from the compiled one, or edited by hand, and checked.

The compiler's prompt is always valid H3 notation but terse. MiniMax's own pipeline (H3-Context-IR, not released) turns
free-form input into long, detailed prompts; this is our version of that last step. The AI writes only what is prose -
the description body and the two sound fields. Everything the planner computed stays the planner's: the alignment line,
subject_definitions, summary, retention_analysis, the shot markers and cut times, every <d> line and speaker ID, and the
labels. An answer that changes any of those is refused and the compiled prompt stays.

A part's own prompt is stored in the shot document with the key of the compiled prompt it was written from. When the
plan changes (timing, shots, media, Look), the key no longer matches, the compiled prompt is used and the user is told.
"""
import hashlib
import re

SECTIONS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "integrated_multimodal_description",
            "overall_soundscape", "non_diegetic_music")
HEADER_RE = re.compile(r"(?m)^(%s):[ \t]*" % "|".join(SECTIONS))
ANSWER_RE = re.compile(r"(?mi)^\s*\**\s*(summary|description|detailed_description|integrated_multimodal_description|overall_soundscape|non_diegetic_music)\s*\**\s*:[ \t]*")
DIALOGUE_RE = re.compile(r"<d>.*?</d>", re.S)
CUT_RE = re.compile(r"\[Shot (\d+)\](?:\s*At (\d{2}:\d{2}\.\d{3}))?")
LABEL_RE = re.compile(r"<(?:Subject|Picture|Video|Audio) \d+>")
SPEAKER_RE = re.compile(r"\(S\d+(?:,\s*S\d+)*\)")
BEAT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*s?\s*[–-]\s*\d+(?:[.,]\d+)?\s*s\s*:")
NESTED_RE = re.compile(r"\b(?:%s)\s*:" % "|".join(SECTIONS))
WRITE_TOKENS = 2048
MIN_WORDS = 40
SYSTEM = ("You write the description of one render part of a MiniMax H3 video. You keep the planner's structure, cut times, "
          "labels and spoken or sung lines exactly, and make the description concrete, visual and detailed. You answer with the "
          "labelled fields asked for, and nothing else.")


def prompt_key(prompt):
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]


def write_tokens(max_tokens):
    return max(max_tokens, WRITE_TOKENS)


def split_sections(prompt):
    """(text before the first section, {section: body}) of a compiled prompt; bodies keep their own line breaks."""
    found = list(HEADER_RE.finditer(prompt))
    head = prompt[:found[0].start()].strip() if found else prompt.strip()
    sections = {}
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(prompt)
        sections[match.group(1)] = prompt[match.end():end].strip()
    return head, sections


def vocal_lines(body):
    """Each planned spoken or sung line with the speaker clause in front of it ("<Subject 1> (S1) sings, <d>...</d>")."""
    out, start = [], 0
    for match in DIALOGUE_RE.finditer(body):
        before = body[start:match.start()]
        clause = re.split(r"(?:[.!?]|\]|</d>)\s+", before)[-1].strip()
        out.append((clause + " " + match.group(0)).strip())
        start = match.end()
    return out


def _body_name(sections):
    return "detailed_description" if "detailed_description" in sections else "integrated_multimodal_description"


def _labels(compiled, head):
    labels = set(LABEL_RE.findall(compiled))
    if head.startswith("How the reference pictures align with the target video"):
        labels.update("<Picture %s>" % number for number in re.findall(r"\bPicture ([1-9]\d*)\b", head))
    return labels


def _summary_rule(sections):
    labels = ", ".join(sorted(set(LABEL_RE.findall(sections.get("subject_definitions", "")))))
    # qwen3.5:9b summed up the pictures instead of the part ("then widens to ... finally settles on her seated") for a part
    # of one shot; the summary has to say what this part's description says.
    return ("summary: one or two English sentences that sum up this part's description (the same events, nothing else) and "
            "what each reference contributes (%s). No square brackets, no spoken words." % labels)


ARRIVAL = ("Spend the last sentences on the arrival: name the final pose, the framing and the light of that picture concretely, so the motion reaches it in time; otherwise H3 catches up in the last frames and the picture morphs into place.")


def _extra_rules(head, reference, guidance, pictures):
    """Rules for keyframes, the chosen direction and the attached pictures."""
    rules = []
    labels = _labels(head, head)
    if not reference and "<Picture 2>" in labels:
        # base-en 3.2: the body supplies the path between the two frames, it does not describe two still pictures.
        # Measured 2026-10-11: without the end pose in the text, 4-step H3 pulled the last 4 frames onto Picture 2 (a morph);
        # with it the approach was even.
        rules.append("Picture 1 is the first and Picture 2 the last frame: begin in the position and framing established by Picture 1, "
                     "describe how pose, framing and light change in between, and settle into the pose and composition established "
                     "by Picture 2. " + ARRIVAL)
    elif not reference and "<Picture 1>" in labels:
        rules.append("<Picture 1> is the %s frame: %s" % (("last", "the last shot arrives at what it shows. " + ARRIVAL) if "aligns with" in head
                                                          else ("first", "begin with what it shows and develop forward from it.")))
    if guidance:
        rules.append("Direction: " + guidance)
    named = [label for label in pictures if label]
    if named:
        rules.append("The attached pictures are, in order: %s. Describe what they show concretely and never against them: faces, "
                     "hair, clothing, colours, the place and its light. They are references, not the video: never describe a "
                     "character sheet, its layout, labels or several views as such." % ", ".join(named))
    elif pictures:
        rules.append("The attached pictures show how the characters and the place look; describe that in words, without labels.")
    return rules


# H3 community findings, checked against our parts (comparison 2026-10-20): a still pose froze the face, a push-in that ran
# over a seam was pushed again by the next part, and these skin words gave oily, retouched faces. An effect is the user's.
CRAFT = ("Write movement and expression as a change from one state to another (for example easing out of a smile into a "
         "searching look); never call a figure completely still. A camera move starts and ends inside this part: no push-in, "
         "pull-out or arc that would go on past its end. Never describe skin as flawless, glowing, shimmering or wet. Keep every "
         "embedding:... word of the draft exactly as written, after the same sentence: it is an effect the user chose.")


def request(compiled, mode, seconds, story="", figures="", continues=False, part=(1, 1), guidance="", pictures=()):
    """The user turn for the writer: rules, the compiled draft, and the story and figures as material for detail only.

    guidance: what the chosen direction wants the description to dwell on (Make H3 prompt); pictures: the labels of the
    pictures attached to the request, in order ("" for a picture shown only for its look)."""
    head, sections = split_sections(compiled)
    body = sections.get(_body_name(sections), "")
    labels = sorted(_labels(compiled, head))
    reference = mode == "ref2va"
    fields = ("summary", "description", "overall_soundscape", "non_diegetic_music") if reference else (
        "description", "overall_soundscape", "non_diegetic_music")
    rules = [
        "Rewrite the description of part %d of %d of a MiniMax H3 video (%s, %.2f s). Return exactly these %s labelled fields "
        "and nothing else:\n%s" % (part[0], part[1], mode.upper(), seconds, "four" if reference else "three",
                                    "\n".join(name + ": ..." for name in fields)),
        "description: " + ("start with one or two sentences of the overall visual style, then [Shot 1]." if reference
                           else "start with [Shot 1], then the visual style and the opening composition in one sentence, then what happens."),
        "Keep every shot marker and cut time exactly as in the draft (for example [Shot 2] At 00:04.500, the camera cuts to ...); "
        "this part has exactly %s: add no shot and no cut." % ("1 shot" if len(CUT_RE.findall(body)) < 2 else "%d shots" % len(CUT_RE.findall(body))),
        "Copy every <d>...</d> block exactly as written in the draft, with its speaker in front of it, in the same order. "
        "Add no other spoken or sung words and never write lyrics outside <d>.%s" % (
            " The lines, each to be written exactly like this where it is heard:\n" + "\n".join("- " + line for line in vocal_lines(body))
            if DIALOGUE_RE.search(body) else ""),
        ("Use only these labels: %s, and keep the speaker IDs such as (S1)." % ", ".join(labels)) if labels
        else "Use no <...> labels; keep the speaker IDs such as (S1).",
        "The draft is only a skeleton: write new sentences of your own, two or three for every shot, describing what is visible "
        "and audible: appearance, position in the frame, actions and small movements, facial expression, light, and the camera "
        "movement as a sentence with amplitude and speed (e.g. The camera pushes in with small amplitude at slow speed), or The camera "
        "holds a static shot when it does not move. Only the shot markers, the labels and the lines above are taken over word for "
        "word. About %s words. English, except inside <d>."
        % ("350 to 500" if reference else "250 to 400"),  # ref-en 5.2: a generation task's description is normally 350-500 words
        "overall_soundscape: one to three English sentences of ambience and physical sounds; no speech, no singing.",
        "non_diegetic_music: the score only the audience hears (instruments, tempo, dynamics), or N/A.",
        "The story and the figures below are material for detail only; they never change times, cuts or words.",
        CRAFT,
    ]
    if BEAT_RE.search(body):
        # shot_share.py gives a part the time beats of its own share of a shot; dropped, the part plays the whole action again
        rules.append("Keep each time beat of the draft (such as 0–2.5s:) at the start of its own sentences, in the same order and "
                     "with the same times, and describe only what the draft puts into that beat.")
    if continues:
        rules.append("This part continues the previous part: open in the middle of the same action, do not introduce the scene "
                     "again, and keep the camera's framing unless the draft names a new move.")
    if reference:
        rules.insert(1, _summary_rule(sections))
    rules += _extra_rules(head, reference, guidance, pictures)
    draft = "\n".join(part_ for part_ in (head, "description: " + body, "overall_soundscape: " + sections.get("overall_soundscape", ""),
                                          "non_diegetic_music: " + sections.get("non_diegetic_music", "")) if part_)
    out = "\n".join(rules) + "\n\nDraft:\n" + draft
    if reference and sections.get("subject_definitions"):
        out += "\n\nFigures:\n" + sections["subject_definitions"]
    elif figures.strip():
        out += "\n\nFigures:\n" + figures.strip()
    if story.strip():
        out += "\n\nStory:\n" + story.strip()
    return out


def _answer_fields(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).removeprefix("assistant\n").strip()
    if "```" in text:
        fences = list(re.finditer(r"(?m)^[ \t]*```([^\n\r`]*)\r?$", text))
        # Only one complete block supplies a prompt. Never merge ambiguous blocks or use an unfinished one.
        if len(fences) != 2 or fences[1].group(1).strip():
            return {}
        text = text[fences[0].end():fences[1].start()].strip()
        if "```" in text:
            return {}
    found = list(ANSWER_RE.finditer(text))
    fields = {}
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(text)
        name = match.group(1).lower()
        name = "description" if name in ("detailed_description", "integrated_multimodal_description") else name
        fields.setdefault(name, " ".join(text[match.end():end].split()))
    return fields


def _words(text):
    # The language tag does not count: qwen3.5:9b copied "<d>The void calls to me.</d>" without its "[English]".
    return re.findall(r"\w+", re.sub(r"^<d>\s*\[[^\]]*\]", "<d>", text).lower())


def _lines_back(written, body):
    """A description that left every spoken or sung line out gets each one back at the end of the shot it belongs to
    (qwen3.5:9b wrote a fine 300-word part without its two lyric lines)."""
    owner = {}
    for line, match in zip(vocal_lines(body), DIALOGUE_RE.finditer(body)):
        shots = CUT_RE.findall(body[:match.start()])
        owner.setdefault(shots[-1][0] if shots else "1", []).append(line)
    pieces = re.split(r"(?=\[Shot \d+\])", written)
    out = []
    for piece in pieces:
        number = re.match(r"\[Shot (\d+)\]", piece)
        lines = owner.get(number.group(1), []) if number else []
        out.append(" ".join([piece.rstrip()] + lines) + (" " if piece.endswith(" ") else "") if lines else piece)
    return "".join(out)


def repair(written, body):
    """Put back what a model reliably gets slightly wrong, where the plan says unambiguously what it must be.

    Measured with Ollama qwen3.5:9b on the elf song (2026-10-05): "[Shot 1] At 00:00.000," for the first shot (the guide
    gives it no time), "(S1) sings" without the "<Subject 1>" in front, and a lyric line with changed punctuation. Anything
    else - a moved cut, a changed or extra word, a lost line - is not repaired; the answer is refused instead."""
    written = re.sub(r"\[Shot 1\]\s*At 00:00\.000,?\s*", "[Shot 1] ", written)
    if not DIALOGUE_RE.search(body):
        # A part without words got an invented line (music video, 25 s test): the sentence carrying it goes.
        written = re.sub(r"[^.!?\]]*<d>.*?</d>[^.!?\[]*[.!?]?\s*", "", written, flags=re.S)
    written = re.sub(r"\[Shot 1\] ([a-z])", lambda m: "[Shot 1] " + m.group(1).upper(), written)
    planned, found = CUT_RE.findall(body), CUT_RE.findall(written)
    if len(found) > len(planned) and [n for n, _ in found[:len(planned)]] == [n for n, _ in planned]:
        # qwen3.5:9b added a [Shot 3] to a two-shot part (25 s test); its text stays as the end of the last planned shot.
        extra = r"\[Shot (?:%s)\](?:\s*At \d{2}:\d{2}\.\d{3},?)?\s*(?:the (?:camera|shot) cuts to\s*)?" % "|".join(n for n, _ in found[len(planned):])
        written = re.sub(extra + r"(\w?)", lambda m: m.group(1).upper(), written)
    times = dict(CUT_RE.findall(body))
    written = re.sub(r"\[Shot (\d+)\](?!\s*At )", lambda m: "[Shot %s] At %s," % (m.group(1), times[m.group(1)])
                     if times.get(m.group(1)) else m.group(0), written)
    if not DIALOGUE_RE.search(written) and DIALOGUE_RE.search(body) and CUT_RE.findall(written) == CUT_RE.findall(body):
        written = _lines_back(written, body)
    for speaker, owner in {m.group(2): m.group(1) for m in re.finditer(r"(<(?:Subject|Audio) \d+>) (\(S\d+\))", body)}.items():
        written = re.sub(r"(?<!%s )%s" % (re.escape(owner), re.escape(speaker)), "%s %s" % (owner, speaker), written)
    # A line whose speaker clause was dropped ("As she sings, <d>...") gets the planned speaker right in front of it.
    planned = [re.search(r"(?:<(?:Subject|Audio) \d+> )?\(S[\d,\s]+\)", line) for line in vocal_lines(body)]
    pieces, out, start = list(DIALOGUE_RE.finditer(written)), [], 0
    if len(pieces) == len(planned):
        for match, speaker in zip(pieces, planned):
            clause = re.split(r"(?:[.!?]|\]|</d>)\s+", written[start:match.start()])[-1]
            out.append(written[start:match.start()])
            if speaker and "(S" not in clause:
                out.append(speaker.group(0) + " ")
            out.append(match.group(0))
            start = match.end()
        written = "".join(out) + written[start:]
    planned, found = DIALOGUE_RE.findall(body), DIALOGUE_RE.findall(written)
    if len(planned) == len(found) and all(_words(a) == _words(b) for a, b in zip(planned, found)):
        pieces = DIALOGUE_RE.split(written)
        written = "".join(piece + (planned[index] if index < len(planned) else "") for index, piece in enumerate(pieces))
    return written


def _summary(sections, written):
    """The planner's task type ("[reference generation]") with the AI's sentences after it, when they only name defined
    labels and hold no spoken words; otherwise the planner's summary as it was. A weak summary never refuses a part."""
    planned = sections["summary"]
    prefix = re.match(r"\[[^\]]*\]", planned)
    written = re.sub(r"^\s*\[[^\]]*\]\s*", "", written or "").strip()
    defined = set(LABEL_RE.findall(sections.get("subject_definitions", "")))
    if (not prefix or not 5 <= len(written.split()) <= 120 or "<d>" in written or NESTED_RE.search(written)
            or not set(LABEL_RE.findall(written)) <= defined):
        return planned
    return "%s %s" % (prefix.group(0), written)


def _anchors(written, head):
    """Name the keyframes in the description as the guide's examples do, when the writer left them out: FL2VA begins "in the
    position and framing established by Picture 1" and settles into "the pose and composition established by Picture 2";
    I2VA begins from <Picture 1>."""
    def opening(sentence):
        found = re.search(r"\[Shot 1\] [^.]*\.\s*", written)
        return written[:found.end()] + sentence + " " + written[found.end():] if found else written
    if "Picture 2" in head and "<Picture" not in head:
        if "Picture 1" not in written:
            written = opening("The shot begins in the position and framing established by Picture 1.")
        if "Picture 2" not in written:
            written = written.rstrip() + " At the end, the scene settles into the pose and composition established by Picture 2."
    elif "<Picture 1>" in head and "fully referenced" in head and "<Picture 1>" not in written:
        written = opening("The shot begins from <Picture 1>.")
    return written


def check(compiled, answer):
    """(final prompt, problems). With problems the final prompt is None and the compiled prompt is to be kept."""
    head, sections = split_sections(compiled)
    name = _body_name(sections)
    body = sections.get(name, "")
    fields = _answer_fields(answer)
    written = _anchors(repair(fields.get("description", ""), body), head)
    problems = []
    if len(written.split()) < MIN_WORDS:
        problems.append("the description is missing or shorter than %d words" % MIN_WORDS)
    if CUT_RE.findall(written) != CUT_RE.findall(body):
        problems.append("the shot markers or cut times differ from the plan")
    if name == "integrated_multimodal_description" and not written.startswith("[Shot 1]"):
        problems.append("the description does not start with [Shot 1]")
    if DIALOGUE_RE.findall(written) != DIALOGUE_RE.findall(body):
        problems.append("the spoken or sung lines (<d>) are not exactly the planned ones")
    labels = _labels(compiled, head)
    if not set(LABEL_RE.findall(written)) <= labels:
        problems.append("it uses labels the plan does not have: %s" % ", ".join(sorted(set(LABEL_RE.findall(written)) - labels)))
    if not {l for l in LABEL_RE.findall(body) if l.startswith("<Subject")} <= set(LABEL_RE.findall(written)):
        problems.append("a planned subject label is missing")
    if not set(SPEAKER_RE.findall(body)) <= set(SPEAKER_RE.findall(written)):
        problems.append("a speaker ID such as (S1) is missing")
    if NESTED_RE.search(written) or ("summary" in fields and "summary" not in sections):
        problems.append("it nests another prompt section inside the description")
    if problems:
        return None, problems
    parts = [head] if head else []
    if "summary" in sections:
        sections = {**sections, "summary": _summary(sections, fields.get("summary", ""))}
    for key in ("subject_definitions", "summary", "retention_analysis"):
        if key in sections:
            parts.append("%s:%s%s" % (key, "\n" if key != "summary" else " ", sections[key]))
    parts.append("%s: %s" % (name, written))
    for key in ("overall_soundscape", "non_diegetic_music"):
        value = fields.get(key) or sections.get(key, "")
        if value:
            parts.append("%s: %s" % (key, value))
    return "\n\n".join(parts), []
