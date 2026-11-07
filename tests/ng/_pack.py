"""Import the repo as a package without running its __init__ (which needs ComfyUI).

The folder name has a hyphen, so the pack is registered under a synthetic name. Relative imports inside `ng`
(for example `from ... import minimax_plan`) then resolve against the repo root exactly as they do inside ComfyUI.
"""
import importlib
import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACK = "mmxd_pack"


def load():
    if PACK not in sys.modules:
        module = types.ModuleType(PACK)
        module.__path__ = [REPO]
        sys.modules[PACK] = module
    return sys.modules[PACK]


def module(name):
    load()
    return importlib.import_module("%s.%s" % (PACK, name))


COMFY_ROOT = os.path.dirname(os.path.dirname(REPO))


def load_full_pack():
    """Execute the pack's real __init__ (all nodes registered) under a synthetic name, as test_node.py does."""
    comfy_available()
    stub_prompt_server()
    name = "mmxd_full_pack"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, "__init__.py"), submodule_search_locations=[REPO])
        pack = importlib.util.module_from_spec(spec)
        sys.modules[name] = pack
        spec.loader.exec_module(pack)
    return sys.modules[name]


def stub_prompt_server():
    """minimax_media registers aiohttp routes when imported, so a PromptServer must exist first (same trick as test_node.py)."""
    import server

    if getattr(server.PromptServer, "instance", None) is not None:
        return

    class _Routes:
        def post(self, *_a, **_k):
            return lambda fn: fn

        def get(self, *_a, **_k):
            return lambda fn: fn

    server.PromptServer.instance = types.SimpleNamespace(routes=_Routes())


def comfy_available():
    """Put the ComfyUI root on sys.path and report whether its tensor and layout modules import (they need torch)."""
    if COMFY_ROOT not in sys.path:
        sys.path.insert(0, COMFY_ROOT)
    try:
        importlib.import_module("comfy.nested_tensor")
        importlib.import_module("comfy.ldm.minimax.model")
    except Exception:
        return False
    return True
