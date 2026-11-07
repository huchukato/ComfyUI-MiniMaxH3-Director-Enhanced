"""One description per AI provider, so the node schema, the panel and the transport cannot disagree.

Pure data with no ComfyUI import, which is what lets this live in core: the node builds its combo
from it, the panel reads it over /ng/providers and the request builder decides from it which
sampling fields a provider actually accepts. One list, one place to correct.

`verified` is set by hand after a real run against that provider - never by a test and never by
code. Everything else says so in the panel instead of pretending to work.
"""
from dataclasses import dataclass

# The two wire formats vlm_generate actually speaks. A provider that needs a third one gets a
# new transport before it is offered here; there is no "probably works" entry.
OLLAMA_GENERATE = "/api/generate"
OPENAI_CHAT = "/v1/chat/completions"

# Every setting we know, with the type used to read and range-check it. A provider that does not
# list a field never receives it, so a value left over from another provider cannot leak out.
SETTING_TYPES = {
    "max_tokens": "int", "seed": "int", "fixed_seed": "bool", "timeout_seconds": "int",
    "temperature": "float", "top_p": "float", "top_k": "int", "min_p": "float",
    "frequency_penalty": "float", "presence_penalty": "float", "keep_alive": "int",
}

# Shown when a provider has no preference; the panel offers these for every provider.
DEFAULT_SETTINGS = {
    "max_tokens": 512, "seed": 0, "fixed_seed": False, "timeout_seconds": 120,
    "temperature": 0.3, "top_p": 0.9, "top_k": 40, "min_p": 0.0,
    "frequency_penalty": 0.0, "presence_penalty": 0.0, "keep_alive": 0,
}

# The help text behind every "?". English, because that is what the node's own tooltips use and
# what the model sees; one sentence, saying what the field is for and not how it works.
SETTING_HELP = {
    "max_tokens": "Upper bound for the answer length. A short description needs few tokens; splitting into shots always allows at least 2048.",
    "seed": "Start value for the model's random choice. The same seed with the same settings usually gives the same answer.",
    "fixed_seed": "Use the seed above. Without this the provider picks a new one every time and the answer changes.",
    "timeout_seconds": "How long one analysis request may take before it is given up.",
    "temperature": "How creative the answer may be. Lower is more literal and repeatable, higher is more varied.",
    "top_p": "Keep only the most likely answers up to this total probability. Lower means fewer surprises.",
    "top_k": "Consider only this many most likely answers.",
    "min_p": "Drop answers that are far less likely than the best one, relative to how likely it is.",
    "frequency_penalty": "Lower the chance of repeating words that already appear.",
    "presence_penalty": "Lower the chance of talking about the same subjects again.",
    "keep_alive": "Seconds the local server keeps the model loaded. 0 releases it after every request.",
}


# A context card names its medium; a provider names its abilities. `image` and `video` both need
# vision, which is why this mapping exists at all: comparing the two names directly made ollama
# refuse the image requests it has always answered.
MEDIA_ABILITY = {"image": "vision", "video": "vision", "audio": "audio", "text": "text"}

# What a medium is called where the user reads it. The mapping above answers the backend's question
# ("vision or audio?"); this answers the panel's ("image, video, audio or text?"). Both exist because
# one word cannot serve both.
MEDIA_LABEL = {"image": "image", "video": "video", "audio": "audio", "text": "text"}

# The sentence a context card shows when its medium cannot be read. The point is that the user is
# told what to do, not only what is wrong: an error naming the card's own file gives them somewhere
# to go. Written per medium because the way out differs - a text card needs no provider at all,
# while an audio card needs a different model on the same provider.
UNSUPPORTED_HINT = {
    "image": "This provider cannot read images. Choose a vision model, or describe the picture in a Text card.",
    "video": "This provider cannot read video. Choose a vision model and attach a still picture, or describe the clip in a Text card.",
    "audio": "This provider cannot read audio. Choose a model with audio input, or describe the sound in a Text card.",
    "text": "This provider cannot read text.",
}


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    kind: str                  # "local" | "api" - decides which source card offers it
    base_url: str = ""
    generate_path: str = OPENAI_CHAT
    models_path: str = "/v1/models"
    auth: str = "none"         # "none" | "bearer" | "x-api-key"
    supports: tuple = ("text",)
    fields: tuple = ()         # settings this provider accepts; the rest are never sent
    verified: bool = False
    verified_note: str = ""
    # A pre-filled suggestion, not a list of what the provider offers. That list comes from
    # /ng/models, because a hard-coded model list is wrong within a week.
    sample_model: str = ""

    def setting_defaults(self):
        """Only the fields this provider knows, so the panel never shows a setting it drops."""
        return {name: DEFAULT_SETTINGS[name] for name in self.fields if name in DEFAULT_SETTINGS}

    def as_dict(self):
        """The panel's view of this provider: what it is called, where it lives, what it accepts.

        One direction only, and `as_dict` rather than `to_dict` on purpose. Nothing ever parses
        this back into a Provider - the registry is the source, never a saved copy - so a
        from_dict here would be a second, untested way to build an entry. The structure test
        asks for from_dict whenever it sees to_dict; using a different name is the honest answer
        rather than a stub that nothing calls.
        """
        return {"id": self.id, "label": self.label, "kind": self.kind, "base_url": self.base_url,
                "generate_path": self.generate_path, "models_path": self.models_path, "auth": self.auth,
                "supports": list(self.supports), "fields": list(self.fields), "verified": self.verified,
                "verified_note": self.verified_note, "sample_model": self.sample_model,
                "defaults": self.setting_defaults(),
                # The panel explains every field from here, so a wording change is one edit in one
                # place and cannot drift from the list of fields it describes.
                "help": setting_help(self.id),
                # The wire name per field. Only differs where it differs (Ollama nests and renames);
                # a field missing from this map is sent under its own name.
                "wire": {name: WIRE_NAME.get(self.id, {}).get(name, name) for name in self.fields},
                # The capability sentence, per medium. The panel does not compose this itself: what
                # a provider cannot read is a property of the provider, and one text assembled in two
                # places is how the card and the request end up disagreeing.
                "media": {medium: {"ok": self.supports_media(medium),
                                   "hint": UNSUPPORTED_HINT.get(medium, "")}
                          for medium in MEDIA_LABEL}}

    def supports_media(self, media):
        """Whether this provider can read one context medium. Unknown media is refused: the
        point of the check is to say "this cannot work", so a typo must not slip through."""
        ability = MEDIA_ABILITY.get(media)
        return ability is not None and ability in self.supports


PROVIDERS = {
    "ollama": Provider(
        "ollama", "Ollama", "local", "http://127.0.0.1:11434", generate_path=OLLAMA_GENERATE,
        models_path="/api/tags", auth="none", supports=("text", "vision"),
        fields=("max_tokens", "seed", "fixed_seed", "timeout_seconds", "temperature",
                "top_p", "top_k", "min_p", "keep_alive"),
        verified=True, verified_note="Tested: qwen3.5:9b writes shots and prompts and describes pictures.",
        sample_model="qwen2.5vl:7b"),
    "lmstudio": Provider(
        "lmstudio", "LM Studio", "local", "http://127.0.0.1:1234/v1", supports=("text", "vision"),
        fields=("max_tokens", "seed", "fixed_seed", "timeout_seconds", "temperature", "top_p",
                "frequency_penalty", "presence_penalty"),
        verified_note="Not tested yet. Start LM Studio's local server first."),
    "llamacpp": Provider(
        "llamacpp", "llama.cpp server", "local", "http://127.0.0.1:8080/v1", supports=("text",),
        fields=("max_tokens", "seed", "fixed_seed", "timeout_seconds", "temperature", "top_p",
                "frequency_penalty", "presence_penalty"),
        verified_note="Not tested yet. Start llama.cpp's server first."),
    "custom": Provider(
        "custom", "Custom URL", "local", "", supports=("text",),
        fields=("max_tokens", "seed", "fixed_seed", "timeout_seconds", "temperature", "top_p",
                "frequency_penalty", "presence_penalty"),
        verified_note="Any OpenAI-compatible server at the address you type."),
    "openai": Provider(
        "openai", "OpenAI / ChatGPT", "api", "https://api.openai.com/v1", auth="bearer",
        supports=("text", "vision"),
        fields=("max_tokens", "seed", "fixed_seed", "timeout_seconds", "temperature", "top_p",
                "frequency_penalty", "presence_penalty"),
        verified_note="Online, needs your API key. Not tested yet."),
    "anthropic": Provider(
        "anthropic", "Claude", "api", "https://api.anthropic.com/v1", auth="x-api-key",
        supports=("text", "vision"),
        # No top_p next to a temperature: Claude rejects the combination. No seed: the API has none.
        fields=("max_tokens", "fixed_seed", "timeout_seconds", "temperature",
                "frequency_penalty", "presence_penalty"),
        verified_note="Online, needs your API key. Not tested yet."),
    "gemini": Provider(
        "gemini", "Google AI Studio", "api",
        "https://generativelanguage.googleapis.com/v1beta/openai", auth="bearer",
        supports=("text", "vision"),
        fields=("max_tokens", "fixed_seed", "timeout_seconds", "temperature", "top_p"),
        verified_note="Online, needs your API key. Not tested yet."),
    "openrouter": Provider(
        "openrouter", "OpenRouter", "api", "https://openrouter.ai/api/v1", auth="bearer",
        supports=("text", "vision"),
        fields=("max_tokens", "seed", "fixed_seed", "timeout_seconds", "temperature", "top_p",
                "frequency_penalty", "presence_penalty"),
        verified=True,
        # Live run: /models answers with or without a key, so a listing proves the address, not the key; a vision chat on
        # google/gemma-4-26b-a4b-it:free succeeded for cost 0 and needed ~2000 max tokens (it reasons first).
        verified_note="Online, needs your API key. Tested with a free vision model; give it about 2000 max tokens.",
        sample_model="google/gemma-4-26b-a4b-it:free"),
}

# The source cards. Custom is not one of them: it is a provider choice inside Local and API,
# because "custom" only means "I type the address myself" and has no behaviour of its own.
#
# There is no "load from disk" card either. Choosing an installed encoder and connecting a Load CLIP
# node are the same thing to the request - both end up in ComfyUI's Generate Text - so they live
# together under CLIP / Encoder instead of splitting the same path across two cards.
SOURCES = (
    {"id": "local", "title": "Local", "hint": "Load LLM / AI Model", "icon": "monitor",
     "providers": ("ollama", "lmstudio", "llamacpp", "custom"), "key": False,
     "note": "Runs on your own machine. Disk models load only during an explicit AI action."},
    {"id": "api", "title": "API", "hint": "Online provider", "icon": "globe",
     "providers": ("openai", "anthropic", "gemini", "openrouter", "custom"), "key": True,
     "note": "Needs an API key. The key is kept in ComfyUI's user settings, never in the workflow."},
    {"id": "clip", "title": "CLIP / Encoder", "hint": "Text Encoder only", "icon": "paperclip",
     "providers": (), "key": False,
     "note": "Connect Load CLIP, or choose an installed encoder. Both run through Generate Text."},
)


# Ollama nests its sampling knobs under "options" and spells the token limit num_predict; the
# OpenAI-compatible APIs take them flat. Naming both here is what keeps a field from being sent
# in the wrong place, which a provider answers with a 400 and no useful message.
OLLAMA_OPTION_FIELDS = ("max_tokens", "temperature", "top_p", "top_k", "min_p", "seed")

# Not every provider gates its model list behind the key. OpenRouter answers /v1/models without
# one - and with a wrong one - and only rejects the bad key on the chat call. So a listing that
# worked is NOT evidence that the key is good, and the panel must not claim that it is.
#
# Only the providers measured to really reject a bad key are named here. A provider needing no key
# at all is never in it: there is nothing to check. Everyone else stays out and has to be added by
# hand after a real run - a second list, but one that only ever grows on evidence.
KEY_CHECKED_ON_LISTING = ("openai", "anthropic", "gemini")


def key_is_checked_on_listing(provider):
    """Whether a successful listing proves anything about the key. False means: no key is involved,
    or the provider answered anyway, so the first real test of the key is the first request."""
    entry = get(provider)
    return entry.auth != "none" and entry.id in KEY_CHECKED_ON_LISTING


# The "?" text is usually one sentence per field, but a few fields mean something different depending
# on the provider: a seed is a real control on Ollama and simply absent on Claude, and `timeout_seconds`
# never reaches the wire at all because it belongs to the HTTP client. A generic sentence in that
# situation would describe a control the user cannot use, so a provider may say its own.
#
# Only overrides, never replacements: an override that forgets the base sentence would leave a field
# with no help text at all, which is why the base is merged in as_dict() rather than chosen between.
SETTING_HELP_OVERRIDES = {
    "anthropic": {
        "fixed_seed": "Claude has no seed parameter, so this switch changes nothing here. The answer varies a little between runs.",
        "max_tokens": "Claude spends part of this budget reasoning before it answers. Below roughly 2000 a long answer gets cut off.",
    },
    "gemini": {
        "fixed_seed": "Gemini has no seed parameter, so this switch changes nothing here.",
    },
    "openrouter": {
        "max_tokens": "Many free OpenRouter models reason before answering and need roughly 2000. Below that a long answer gets cut off.",
    },
}


def setting_help(provider_id):
    """The help text for every field this provider accepts: the shared sentence, with this
    provider's own wording winning where it has one. A provider nobody overrode reads the shared
    sentences, which is why a new field needs a text there before it is offered anywhere."""
    entry = get(provider_id)
    override = SETTING_HELP_OVERRIDES.get(entry.id, {})
    return {name: override.get(name) or SETTING_HELP[name]
            for name in entry.fields if name in SETTING_HELP}


# The Ollama nesting is the one place a field's wire name differs from the name the user sees. The
# panel has to say so on the tile itself, because a user who reads "Max tokens" and greps their own
# request log for max_tokens will not find it.
WIRE_NAME = {
    "ollama": {"max_tokens": "num_predict", "seed": "options.seed", "temperature": "options.temperature",
               "top_p": "options.top_p", "top_k": "options.top_k", "min_p": "options.min_p",
               "keep_alive": "keep_alive"},
}

# Kept out of the body on purpose: timeout_seconds belongs to the HTTP client, fixed_seed is the
# user's switch rather than a value, and keep_alive only exists on Ollama.
NON_BODY_FIELDS = ("timeout_seconds", "fixed_seed")


def provider_payload(provider_id, settings):
    """The sampling half of one request body: exactly the fields this provider accepts.

    Returns the flat part for an OpenAI-compatible provider, and the {"options": {...}} nesting
    for Ollama. Model, messages and images are the transport's job and are not touched here.

    A field the provider does not list is dropped even when the caller supplies it, so a value
    left over from a different provider can never reach a request that would reject it.
    """
    provider = get(provider_id)
    values = {name: value for name, value in (settings or {}).items()
              if name in provider.fields and name not in NON_BODY_FIELDS}
    # A seed that is never meant to be held still must not be sent at all: providers treat an
    # explicit seed as "answer this reproducibly", which is the opposite of what an unticked
    # fixed_seed asks for. Leaving it out is what makes the checkbox mean something.
    if not (settings or {}).get("fixed_seed"):
        values.pop("seed", None)
    if provider.generate_path == OLLAMA_GENERATE:
        options = {name: values[name] for name in OLLAMA_OPTION_FIELDS if name in values}
        # Ollama's own spelling, set only when the caller actually asked for a token limit.
        if "max_tokens" in options:
            options["num_predict"] = options.pop("max_tokens")
        # keep_alive sits beside options, not inside them, and only Ollama has it.
        payload = {"keep_alive": int(values["keep_alive"])} if "keep_alive" in values else {}
        if options:
            payload["options"] = options
        return payload
    return dict(values)


def get(provider_id):
    """The one place a provider id is validated, so a typo never reaches the transport."""
    found = PROVIDERS.get(provider_id or "")
    if not found:
        raise ValueError("Choose one of: %s." % ", ".join(sorted(PROVIDERS)))
    return found


def describe():
    """The payload for /ng/providers. Descriptions only: no address the user typed, no key."""
    return {"providers": [PROVIDERS[key].as_dict() for key in sorted(PROVIDERS)],
            "sources": [dict(source) for source in SOURCES],
            "types": dict(SETTING_TYPES)}