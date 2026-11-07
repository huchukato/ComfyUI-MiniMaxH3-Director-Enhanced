"""One render part's writing request and its checked answer, from the same plan the Studio shows."""
import json

from .context import DirectorContext
from .context_build import card_id
from .directions import direction
from .part_prompt import check, request
from .preview import plan_preview


def _without_own(director):
    """The plan as compiled: a part's own prompt must be written from the compiled one, never from an earlier own one."""
    text = director.get("shots", "") or ""
    if not text.lstrip().startswith("{"):
        return director
    data = json.loads(text)
    data.pop("part_prompts", None)
    return {**director, "shots": json.dumps(data)}


def guidance(quick):
    """What the chosen Make H3 prompt direction wants a description to dwell on; "" without one."""
    if not quick or quick.get("direction", "auto") == "auto":
        return ""
    text = direction(quick["direction"]).write
    if quick["direction"] == "spicy":
        text += " Everyone is an adult, 18 or older: call them women and men, never girls or boys."
    return text


def _pictures(chunk, contexts):
    """[(label, context id)] of the pictures this part's prompt names, in label order; with none, the image cards for
    their look only (label "")."""
    named = sorted(((label, cid) for label, cid in chunk.get("prompt_labels", {}).items() if label.startswith("<Picture")),
                   key=lambda item: int(item[0][9:-1]))
    if named:
        return named
    return [("", card_id(entry)) for entry in contexts if entry.get("media") == "image" and entry["widgets"].get("image")][:4]


def brief(director, contexts, index, probe=None, quick=None):
    view = plan_preview({"director": _without_own(director), "contexts": contexts}, probe=probe)
    if not view["ok"]:
        raise ValueError(view["error"])
    if not 0 <= index < len(view["chunks"]):
        raise ValueError("There is no render part %d; the plan has %d." % (index + 1, len(view["chunks"])))
    chunk = view["chunks"][index]
    context = DirectorContext.from_dict(view["director_context"])
    figures = "\n".join("%s: %s" % (item.name, item.description) for item in context.items
                        if item.media == "image" and item.description.strip())
    scenes = [item.source.strip() for item in context.items if item.media == "text" and "scene" in item.effective_usage]
    return {"index": index, "key": chunk["prompt_key"], "compiled": chunk["prompt"], "mode": chunk["mode"],
            "seconds": chunk["sampled_frames"] / 24.0, "continues": chunk["head_frames"] > 0, "parts": len(view["chunks"]),
            "story": "\n\n".join(text for text in [context.idea.strip(), *scenes] if text), "figures": figures,
            "guidance": guidance(quick), "pictures": _pictures(chunk, contexts)}


def write_prompt(facts):
    return request(facts["compiled"], facts["mode"], facts["seconds"], facts["story"], facts["figures"], facts["continues"],
                   (facts["index"] + 1, facts["parts"]), facts.get("guidance", ""), [label for label, _ in facts.get("shown", ())])


def finish(answer, facts):
    """What the Studio shows for Accept: the checked prompt, or why the AI's version was refused (then nothing changes)."""
    text, problems = check(facts["compiled"], answer)
    # Whole song (2026-10-05): 5 of 18 parts came back with the compiled description word for word, which passes every
    # check; the Studio says so instead of offering it as a rewrite.
    same = bool(text) and " ".join(text.split()) == " ".join(facts["compiled"].split())
    out = {"index": facts["index"], "key": facts["key"], "text": text or "", "problems": problems, "unchanged": same}
    if problems:
        out["answer"] = (answer or "")[:6000]  # what the AI wrote, so a refusal can be read and fixed by hand
    return out
