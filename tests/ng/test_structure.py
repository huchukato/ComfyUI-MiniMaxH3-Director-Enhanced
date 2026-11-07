"""Guards for _notes/NG/06-code-rules.md: size limits, layering, persisted types.

These fail the build instead of relying on review, because the legacy monoliths grew exactly where nobody was checking.
"""
import ast
import os
import unittest

from _pack import REPO

NG = os.path.join(REPO, "ng")
WEB_NG = os.path.join(REPO, "js", "ng")
MAX_PY_LINES = 400
MAX_FUNCTION_LINES = 60
MAX_JS_LINES = 500
CORE_FORBIDDEN = {"torch", "numpy", "comfy", "comfy_api", "comfy_extras", "folder_paths", "nodes", "server", "aiohttp",
                  "av", "PIL", "librosa", "cv2"}
# per-file exceptions: path relative to ng/ -> reason; keep this empty unless there is a measured reason
SIZE_EXCEPTIONS = {}


def python_files(root):
    for base, _dirs, files in os.walk(root):
        if "__pycache__" in base:
            continue
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(base, name)


def rel(path):
    return os.path.relpath(path, NG).replace("\\", "/")


def parse(path):
    with open(path, encoding="utf8") as f:
        return ast.parse(f.read(), filename=path)


def imported_roots(tree):
    """Top-level module names imported absolutely, and the layer names reached through relative imports."""
    absolute, relative = set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.append((node.level, node.module or "", [a.name for a in node.names]))
            elif node.module:
                absolute.add(node.module.split(".")[0])
    return absolute, relative


class SizeLimits(unittest.TestCase):
    def test_python_modules_stay_small(self):
        for path in python_files(NG):
            if rel(path) in SIZE_EXCEPTIONS:
                continue
            with open(path, encoding="utf8") as f:
                lines = sum(1 for _ in f)
            self.assertLessEqual(lines, MAX_PY_LINES, "%s has %d lines (limit %d); split it" % (rel(path), lines, MAX_PY_LINES))

    def test_functions_stay_short(self):
        for path in python_files(NG):
            for node in ast.walk(parse(path)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = node.end_lineno - node.lineno + 1
                    self.assertLessEqual(length, MAX_FUNCTION_LINES,
                                         "%s:%s() has %d lines (limit %d)" % (rel(path), node.name, length, MAX_FUNCTION_LINES))

    def test_js_modules_stay_small(self):
        if not os.path.isdir(WEB_NG):
            return
        for base, _dirs, files in os.walk(WEB_NG):
            for name in files:
                if name.endswith(".js"):
                    with open(os.path.join(base, name), encoding="utf8") as f:
                        lines = sum(1 for _ in f)
                    self.assertLessEqual(lines, MAX_JS_LINES, "%s has %d lines (limit %d)" % (name, lines, MAX_JS_LINES))


class Layering(unittest.TestCase):
    def test_core_is_pure(self):
        for path in python_files(os.path.join(NG, "core")):
            absolute, _ = imported_roots(parse(path))
            bad = absolute & CORE_FORBIDDEN
            self.assertFalse(bad, "%s imports %s; core must stay free of ComfyUI/torch" % (rel(path), sorted(bad)))

    def test_lower_layers_do_not_reach_up(self):
        forbidden = {"core": ("adapters", "nodes"), "adapters": ("nodes",)}
        for layer, upper in forbidden.items():
            for path in python_files(os.path.join(NG, layer)):
                _, relative = imported_roots(parse(path))
                for level, module, names in relative:
                    # `from ..adapters import x` inside ng/core/x.py, or `from . import nodes`
                    targets = [module.split(".")[0]] + list(names)
                    hit = [t for t in targets if t in upper]
                    self.assertFalse(hit, "%s (layer %s) imports upward: %s" % (rel(path), layer, hit))


class PersistedTypes(unittest.TestCase):
    def test_serialisable_types_are_versioned(self):
        for path in python_files(NG):
            for node in ast.walk(parse(path)):
                if not isinstance(node, ast.ClassDef):
                    continue
                methods = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
                if "to_dict" not in methods:
                    continue
                self.assertIn("from_dict", methods, "%s:%s has to_dict but no from_dict" % (rel(path), node.name))
                attrs = {t.id for n in node.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                         for t in ([n.target] if isinstance(n, ast.AnnAssign) else n.targets) if isinstance(t, ast.Name)}
                self.assertTrue({"schema_version", "SCHEMA_VERSION"} & attrs,
                                "%s:%s serialises itself but carries no schema_version" % (rel(path), node.name))


if __name__ == "__main__":
    unittest.main()
