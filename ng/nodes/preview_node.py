"""Attach the shared H3 TAEHV preview to a native sampler's model."""
import logging

import comfy.sd
import comfy.utils
import folder_paths
from comfy_api.latest import io

from ...minimax_preview import execute_preview, preview_schema
from ...minimax_preview_runtime import require_taehv
from .context_nodes import CATEGORY

log = logging.getLogger(__name__)
_DEFAULT_TAEH3 = None


def _load_default_taeh3():
    global _DEFAULT_TAEH3
    if _DEFAULT_TAEH3 is not None:
        return _DEFAULT_TAEH3
    name = next((fn for fn in folder_paths.get_filename_list("vae_approx") if fn.startswith("taeh3")), None)
    path = folder_paths.get_full_path("vae_approx", name) if name else None
    if not path:
        return None
    sd, metadata = comfy.utils.load_torch_file(path, return_metadata=True)
    vae = comfy.sd.VAE(sd=sd, metadata=metadata)
    vae.throw_exception_if_invalid()
    _DEFAULT_TAEH3 = vae
    return vae


def _resolve_vae(vae):
    if vae is not None:
        try:
            return require_taehv(vae)
        except ValueError:
            fallback = _load_default_taeh3()
            if fallback is not None:
                log.warning("[H3 Director] Connected preview VAE is not H3 TAEHV; using taeh3 from vae_approx.")
                return fallback
            raise
    return _load_default_taeh3()


class NGH3Preview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return preview_schema("NGH3Preview", "H3 Live Preview", CATEGORY, optional_vae=True)

    @classmethod
    def execute(cls, model, vae=None, **values):
        resolved = _resolve_vae(vae)
        if resolved is None:
            return io.NodeOutput(model)
        return execute_preview(cls, model, resolved, **values)


NODES = [NGH3Preview]

