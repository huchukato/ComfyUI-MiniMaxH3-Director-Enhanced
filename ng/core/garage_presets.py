"""Garage prompt-style presets, resolved through QwenVL-Mod's synced catalog.

QwenVL-Mod (ComfyUI-QwenVL-Mod) owns the preset files and mirrors Garage's
presets/ into presets_remote/ at import. This module only finds that catalog —
first in sys.modules (the usual case once ComfyUI has loaded the node), then by
loading qwenvl_presets.py straight from the sibling custom-node folder, which
works regardless of node load order. Pure Python, no ComfyUI import.
"""
import importlib.util
import sys
from pathlib import Path

_mod = None
_tried = False


def _module():
    global _mod, _tried
    if _tried:
        return _mod
    _tried = True
    for name, candidate in list(sys.modules.items()):
        if name.split(".")[-1] == "qwenvl_presets" and hasattr(candidate, "VL_PRESET_NAMES"):
            _mod = candidate
            return _mod
    # <custom_nodes>/<repo>/ng/core/garage_presets.py -> parents[3] is custom_nodes
    custom_nodes = Path(__file__).resolve().parents[3]
    for candidate in sorted(custom_nodes.glob("*/qwenvl_presets.py")):
        try:
            spec = importlib.util.spec_from_file_location("qwenvl_presets", candidate)
            module = importlib.util.module_from_spec(spec)
            sys.modules["qwenvl_presets"] = module
            spec.loader.exec_module(module)
            _mod = module
            return _mod
        except Exception:
            continue
    return None


def names():
    """The vl preset names (MiniMax, LTX, ...), or [] when QwenVL-Mod is absent."""
    mod = _module()
    return list(getattr(mod, "VL_PRESET_NAMES", [])) if mod else []


def text(name, duration=None):
    """The preset's prompt text for a duration key ("5s".."20s") or its default; "" when unknown."""
    mod = _module()
    if not mod or not name:
        return ""
    try:
        base, key = mod.resolve_vl_preset(name, duration)
        return mod.VL_PROMPTS.get(key) or mod.VL_PROMPTS.get(base) or ""
    except Exception:
        return ""
