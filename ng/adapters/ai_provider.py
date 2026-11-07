"""A native AI provider holds a loader link, never a loaded model or a model cache."""
from dataclasses import dataclass

from ..core.analysis import ProviderConfig


@dataclass(frozen=True)
class NativeAIProvider:
    clip: object
    config: ProviderConfig
    local_model: str = ""
    local_type: str = "stable_diffusion"


def provider_from_values(source, clip, values):
    """The three source cards, and nothing else. There used to be a fourth, "load from disk",
    but choosing an installed encoder and connecting a Load CLIP node reach Generate Text by the
    same path, so they belong to one card. Which of the two is in use is now decided by what is
    actually present - a connected clip, or a chosen model - rather than by a dropdown that had
    to be kept in step with the card above it."""
    model = values.pop("local_model", "")
    model_type = values.pop("local_type", "stable_diffusion")
    legacy_backend = values.pop("local_backend", "")
    if source == "local" and legacy_backend == "disk":
        source = "clip"
    if source == "clip":
        # The encoder runs inside ComfyUI: an address or key left from an HTTP card is not used and must not stop it.
        values = {**values, "base_url": "", "api_key_env": ""}
    config = ProviderConfig.from_dict({"schema_version": ProviderConfig.SCHEMA_VERSION, **values})
    if source == "clip":
        if clip is not None:
            # A connected encoder wins over a chosen model name, so switching from one to the
            # other cannot leave two candidates and leave it to the request to guess.
            return NativeAIProvider(clip, config)
        # No clip connected: the installed encoder is what the card uses. This used to need
        # local_backend="disk" as well, so choosing a model without that switch did nothing.
        if not model:
            raise ValueError("Connect Load CLIP, or choose an installed text encoder.")
        return NativeAIProvider(None, config, model, model_type)
    if source not in ("local", "api"):
        raise ValueError("Choose Local, API or CLIP / Encoder.")
    return config
