"""Declared provider capabilities and editable analysis suggestions, independent of transport."""
from dataclasses import dataclass
from urllib.parse import urlsplit

from . import fields
from . import providers
from .ai_json import read_object
from .context import CONTENT_BY_MEDIA, CONTENT_KINDS, USAGE_BY_MEDIA

# The fields an analysis may fill. Everything else on a card stays the user's own text.
ANALYSIS_FIELDS = ("description", "content", "usage")

# Sampling bounds. A value outside them is a typo or a slider dragged too far, and passing it on
# would only come back as a provider error that says nothing about which field was wrong.
SAMPLING_RANGES = {"temperature": (0.0, 2.0), "top_p": (0.0, 1.0), "top_k": (0, 100), "min_p": (0.0, 1.0),
                   "frequency_penalty": (-2.0, 2.0), "presence_penalty": (-2.0, 2.0)}
# top_k is the one whole number among them; a slider that sends 30.5 is a broken control.
SAMPLING_WHOLE = ("top_k",)


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "ollama"
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""
    vision: bool = True
    audio: bool = False
    timeout_seconds: int = 120
    max_tokens: int = 512
    keep_alive: int = 0
    # Version 2 adds the sampling fields the panel now offers. They live here rather than in the
    # registry because a saved workflow has to carry the user's own values; the registry only says
    # which of them a given provider will actually accept.
    temperature: float = 0.3
    top_p: float = 0.9
    top_k: int = 40
    min_p: float = 0.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    seed: int = 0
    fixed_seed: bool = False
    SCHEMA_VERSION = 2

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "provider": self.provider, "base_url": self.base_url,
                "model": self.model, "api_key_env": self.api_key_env, "vision": self.vision, "audio": self.audio,
                "timeout_seconds": self.timeout_seconds, "max_tokens": self.max_tokens, "keep_alive": self.keep_alive,
                "temperature": self.temperature, "top_p": self.top_p, "top_k": self.top_k, "min_p": self.min_p,
                "frequency_penalty": self.frequency_penalty, "presence_penalty": self.presence_penalty,
                "seed": self.seed, "fixed_seed": self.fixed_seed}

    # A version 1 workflow only ever had the nine fields below. Reading one must not fail and must
    # not silently invent a sampling choice: an old config keeps the provider's own defaults,
    # which is what it was already using before these fields existed.
    VERSION_1_FIELDS = ("provider", "base_url", "model", "api_key_env", "vision", "audio",
                        "timeout_seconds", "max_tokens", "keep_alive")

    @classmethod
    def from_dict(cls, data, path="provider"):
        fields.need_dict(data, path)
        version = data.get("schema_version")
        if version == 1:
            # Take only the fields version 1 knew. Anything else in an old payload is not ours to
            # guess at, and dropping it here means a future field cannot be back-filled into an
            # old workflow by accident.
            data = {name: data[name] for name in cls.VERSION_1_FIELDS if name in data}
            data["schema_version"] = 2
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        for key in ("vision", "audio", "fixed_seed"):
            if not isinstance(data.get(key, getattr(cls(), key)), bool):
                raise ValueError("%s.%s must be true or false." % (path, key))
        if set(data) - set(cls().to_dict()):
            raise ValueError("Provider settings contain unknown fields; keys belong in an environment variable.")
        address = fields.read_str(data, "base_url", path, "").strip()
        if address:
            url = urlsplit(address)
            if url.scheme not in ("http", "https") or not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment:
                raise ValueError("Use an HTTP(S) base URL without credentials, query or fragment; keys belong in api_key_env.")
        sampling = {name: _sampling_number(data, name, path) for name in
                    ("temperature", "top_p", "top_k", "min_p", "frequency_penalty", "presence_penalty")}
        return cls(provider=fields.read_choice(data, "provider", path, tuple(providers.PROVIDERS), "ollama"),
                   base_url=address, model=fields.read_str(data, "model", path, ""),
                   api_key_env=fields.read_str(data, "api_key_env", path, ""), vision=data.get("vision", True),
                   audio=data.get("audio", False), fixed_seed=data.get("fixed_seed", False),
                   timeout_seconds=_whole_number(data, "timeout_seconds", path, 120, 5, 900),
                   max_tokens=_whole_number(data, "max_tokens", path, 512, 64, 8192),
                   keep_alive=_whole_number(data, "keep_alive", path, 0, 0, 3600),
                   seed=_whole_number(data, "seed", path, 0, 0, 2 ** 32 - 1), **sampling)


def _whole_number(data, key, path, default, minimum, maximum):
    """A setting the UI offers as a slider; a wrong type must say so instead of being coerced."""
    value = fields.read_number(data, key, path, default)
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("%s.%s must be a whole number, got %r." % (path, key, value))
    value = int(value)
    if not minimum <= value <= maximum:
        raise ValueError("%s.%s must be between %d and %d, got %d." % (path, key, minimum, maximum, value))
    return value


def _sampling_number(data, key, path):
    """One sampling value, checked against its range. The bounds come from SAMPLING_RANGES and the
    registry must agree with them, so a field cannot be offered with a range nobody enforces."""
    low, high = SAMPLING_RANGES[key]
    value = fields.read_number(data, key, path, providers.DEFAULT_SETTINGS[key], minimum=low)
    if key in SAMPLING_WHOLE and isinstance(value, float) and not value.is_integer():
        raise ValueError("%s.%s must be a whole number, got %r." % (path, key, value))
    if value > high:
        raise ValueError("%s.%s must be between %s and %s, got %s." % (path, key, low, high, value))
    return int(value) if key in SAMPLING_WHOLE else value


@dataclass(frozen=True)
class AnalysisSuggestion:
    """What one analysis offers. `why` explains the choice so the panel can show it instead of a bare result."""
    description: str = ""
    content: str = ""
    usage: str = ""
    why: str = ""
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {"schema_version": self.SCHEMA_VERSION, "description": self.description, "content": self.content,
                "usage": self.usage, "why": self.why}

    @classmethod
    def from_dict(cls, data, path="analysis"):
        fields.need_dict(data, path)
        fields.check_version(data, path, cls.SCHEMA_VERSION)
        if set(data) - set(cls().to_dict()):
            raise ValueError("The analysis contains unknown fields; ask again or write the card yourself.")
        return cls(description=fields.read_str(data, "description", path, "").strip(),
                   content=fields.read_choice(data, "content", path, CONTENT_KINDS, ""),
                   usage=fields.read_str(data, "usage", path, "").strip(),
                   why=fields.read_str(data, "why", path, "").strip())

    def offered(self):
        """Only the fields that really carry a value, so Apply never blanks a field it has nothing for."""
        return {name: value for name, value in ((key, getattr(self, key)) for key in ANALYSIS_FIELDS) if value}


USAGE_MEANING = {
    "image": {"reference": "keep this figure or thing recognizable", "first_frame": "the opening picture", "last_frame": "the closing picture",
              "keyframe": "a picture the video passes through", "storyboard": "a sketch of a moment"},
    "video": {"motion": "copy how things move", "camera": "copy the camera movement", "continue": "the video goes on from its end",
              "structure": "copy the whole structure", "control": "a preprocessed Canny, Pose or Depth video for ControlNet on the control lane"},
    "audio": {"voice": "the voice of a figure", "copy": "reuse this sound", "lock": "keep this sound exactly",
              "music_style": "the style of the music", "rhythm": "the rhythm to follow", "sound_reference": "a sound to imitate"},
    "text": {"style": "the look or visual direction", "rule": "a rule the video must follow", "character": "describes a person or creature",
             "world": "background lore of the world", "scene": "what happens in a scene", "camera": "how the camera works",
             "dialogue": "how lines are spoken", "constraint": "something that must not happen", "instruction": "a general instruction"},
}


def analysis_prompt(media, content, offer=None):
    """`offer` is what the card can show ({"content": [...], "usage": [...]}); the answer may only pick from it.
    Asking for usage as free text ("how the director should use it") got prose such as "To capture the emotional
    depth ...", which no card can hold, so the card's role was never filled by an analysis."""
    scope = {"image": "the image", "video": "three ordered stills from the first 15 seconds of a video; avoid inferring unseen motion",
             "audio": "the first 15 seconds of the audio", "text": "the supplied context text"}
    offer = offer if isinstance(offer, dict) else {}
    # Offer only the roles this medium can actually hold. Offering the full union is what let a
    # model answer "dialogue" for a picture: the value passed the parse and the card was unusable.
    kinds = [kind for kind in offer.get("content") or () if kind in CONTENT_BY_MEDIA[media]] or list(CONTENT_BY_MEDIA[media])
    # A card that shows no content choice (the Text card sends []) is not asked for one: Qwen3-VL 4B put the usage
    # "constraint" there, and the whole answer was refused.
    content_part = "" if offer.get("content") == [] else "content (exactly one of: %s), " % ", ".join(kinds)
    roles = [role for role in offer.get("usage") or () if role in USAGE_BY_MEDIA[media]] or list(USAGE_BY_MEDIA[media])
    # A Text card's stored content ("rules" by default) is not something its user chose; as a focus it made a 4B model
    # call a character description a rule. Each role is named with what it means, so a small model can choose.
    focus = content if media != "text" and content else "observable features"
    # The description becomes the Subject's definition in Ref2VA: one sentence ("an elfin woman with white hair holds
    # a staff") lost the dress, choker, earrings and fangs that keep the elf recognizable.
    told = {"image": "one or two sentences naming what keeps it recognizable: for a figure the face, hair, eyes, build, "
                     "clothing with colours, accessories and props; otherwise the place or the thing",
            "video": "one or two sentences: the movement, where it starts and where it ends"}.get(media, "one concise sentence")
    return ("Describe %s as a reference for a video director. Focus on %s. Return only JSON with "
            "description (%s), %susage (exactly one of: %s) "
            "and why (one short sentence naming the visible reason for that choice). Answer with one object for the whole %s, "
            "not one per picture. Use the words of the lists exactly. Do not invent facts. Shape: %s"
            % (scope[media], focus, told, content_part, "; ".join("%s = %s" % (role, USAGE_MEANING[media][role]) for role in roles),
               {"image": "picture", "video": "clip", "audio": "sound", "text": "text"}[media],
               # Qwen3-VL 4B left usage out, or wrote the role as a key ({"constraint": "..."}); a shape to copy helps it.
               '{"description": "<the description>", %s"usage": "<one word from the usage list>", "why": "<one sentence>"}'
               % ("" if not content_part else '"content": "<one word from the content list>", ')))


def parse_suggestion(text, media="text"):
    """Reads a provider answer. Extra keys are tolerated here on purpose: this is a model's reply, not saved data.
    `usage` is kept as free text because only the card knows which roles its medium offers.

    `media` decides which content roles the answer may name. Without it a picture could be called
    "dialogue" or "voice", which passes every check here and produces a card that means nothing.
    A role the medium cannot hold is reported by name instead of being thrown away silently.
    """
    if not isinstance(text, str):
        raise ValueError("The provider must return a JSON text suggestion.")
    allowed = CONTENT_BY_MEDIA.get(media) or CONTENT_KINDS
    try:
        data = read_object(text, "analysis", "The provider's answer was not readable JSON. "
                           "Try another model or describe it manually.")
    except ValueError as error:
        if str(error).startswith("The AI's answer stopped before its JSON was complete."):
            # Preserve the analysis error category and reserve the token hint for a real cutoff.
            raise ValueError("The provider's answer was not readable JSON. " + str(error)) from None
        raise
    if "description" not in data:
        # Qwen3-VL 4B answered a video per still ({"stills": [{...}, {...}, {...}]}) instead of one object for the clip.
        # The descriptions are kept in order; the roles and the reason come from the first still.
        lists = [value for value in data.values() if isinstance(value, list) and value and all(isinstance(item, dict) for item in value)]
        if len(lists) == 1 and all(isinstance(item.get("description"), str) for item in lists[0]):
            data = {**lists[0][0], "description": " ".join(item["description"].strip() for item in lists[0])}
    usage = fields.read_str(data, "usage", "analysis", "").strip()
    role, separator, _meaning = usage.partition("=")
    if separator and role.strip() in USAGE_BY_MEDIA.get(media, ()):
        usage = role.strip()
    if not usage:
        # The role written as a key, as Qwen3-VL 4B did: {"constraint": "Never show any text ..."}.
        keyed = [key for key in data if key in USAGE_BY_MEDIA.get(media, ())]
        if len(keyed) == 1:
            usage = keyed[0]
            if "description" not in data and isinstance(data[usage], str):
                data = {**data, "description": data[usage]}
    description = fields.read_str(data, "description", "analysis", "" if media == "text" else None).strip()
    content, left_out = data.get("content"), ""
    if content is not None and content not in allowed:
        # Named and left out, not mapped to something else and not a reason to throw the description away.
        left_out = "Content “%s” does not fit this %s card and was left out." % (content, media)
        content = None
    # A Text card shows no description (its note is the text), so there only the role matters.
    if (not description and media != "text") or len(description) > 2000:
        raise ValueError("Analysis needs a description of 1 to 2000 characters; try again or describe it manually.")
    why = fields.read_str(data, "why", "analysis", "").strip()
    if len(why) > 600:
        raise ValueError("The reason is longer than 600 characters; ask again or write it yourself.")
    why = " ".join(part for part in (why, left_out) if part)
    return AnalysisSuggestion(description=description, content=content, usage=usage, why=why)
