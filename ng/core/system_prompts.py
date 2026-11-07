"""The role each AI node plays, in one file, so the loader never carries a system prompt.

The H3 AI Loader is the connection, not the instance. A loader that held a prompt would apply one
persona's wording to every request that passes through it, and the node that actually knows the role
- "you are looking at a picture" versus "you are planning a video" - would have no say. So the
prompts live here, keyed by the node that needs one, and each node places its own text when it
builds the request.

English on purpose: the models follow English prompts more reliably, and the raw answer then lands
in the JSON schema without a translation step in between. The parser only ever sees the model's
output, never this text.

One rule holds this file together: the schema framing stays in the backend and is appended LAST.
Everything here may change freely; the part that decides whether `parse_suggestion` can read the
answer may not. That is why these prompts describe the role and never the format.

Pure Python with no ComfyUI import, which is what lets this live in core next to the provider
registry and the analysis schema it is used with.
"""

# Keyed by node id, so a node asks for its own name and gets its own text.
SYSTEM_PROMPTS = {
    "context_image": (
        "You are analysing one reference picture for a video director. Describe what is visible: "
        "who or what is in it, how they look, where it was taken, and what stands out. Judge what the "
        "picture is useful for, not how good it is technically. Answer in the language of the card."
    ),
    "context_video": (
        "You are analysing one reference clip for a video director. Describe the movement, the camera, "
        "what changes over the seconds, and the mood it creates. Mention where it starts and where it "
        "ends, because a following shot has to continue from there. Answer in the language of the card."
    ),
    "context_audio": (
        "You are analysing one sound for a video director. Say what it sounds like, what it can be used "
        "for in a scene, and - for a voice - roughly which character it fits. Do not invent a name for a "
        "speaker; a name comes from the card. Answer in the language of the card."
    ),
    "context_text": (
        "You are reading one note for a video director. Summarise what it asks for and what it rules "
        "out. A note may be a constraint rather than a description, so state both what it wants and what "
        "it forbids. Answer in the language of the card."
    ),
    "director": (
        "You are planning a video. You are given an idea, a duration and the reference material that "
        "must be used. Break the idea into shots that fill the duration, and say for each shot what "
        "happens and which reference it uses. Keep the user's own dialogue untouched: it is written and "
        "must survive. Answer in the language of the idea."
    ),
}

# The rule that keeps a prompt from becoming a schema instruction. A node may override its own text
# freely because the framing below is appended afterwards and cannot be overwritten by it.
SCHEMA_FRAMING = (
    "Follow the requested JSON schema exactly. Return a complete, nonempty JSON object, without a "
    "preface, without markdown and without a code fence."
)


def for_node(node_id, media=None):
    """The role text for one node, or "" when it has none.

    `media` picks between the context prompts, because the same H3 Context node class serves all
    four media and the one it currently holds is exactly what should decide the wording. It is a
    separate argument rather than part of `node_id` so a node can ask for its role without having
    to build a composite name that only this function would understand.

    An unknown node id is not an error: the framing alone is still a working request, and raising
    here would break every node that has no role to declare. An unknown medium on a known node falls
    back to that node's own text, so "context" with something unexpected still gets the general
    context wording rather than nothing.
    """
    if media and "%s_%s" % (node_id, media) in SYSTEM_PROMPTS:
        return SYSTEM_PROMPTS["%s_%s" % (node_id, media)]
    return SYSTEM_PROMPTS.get(node_id, "")


def framed(role):
    """The role text and the schema rule as one string, in that order.

    The order is the whole point. The role goes first so the model reads it as context, and the
    framing goes last so it is the final instruction the model acts on. Appending rather than
    replacing is what lets a node override its role without being able to break the parser - which
    is what happened once already, when the old hard-coded framing was the only thing standing
    between a rewritten prompt and unreadable output.
    """
    role = (role or "").strip()
    return "%s\n\n%s" % (role, SCHEMA_FRAMING) if role else SCHEMA_FRAMING