"""Measure executable core lines with the standard library; no coverage dependency needed."""
import json
import os
import sys
import trace
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import REPO

CORE = os.path.normcase(os.path.join(REPO, "ng", "core")) + os.sep
hits = {}


def count_lines(frame, event, arg):
    filename = os.path.normcase(frame.f_code.co_filename)
    if not filename.startswith(CORE):
        return None
    if event == "line":
        hits.setdefault(filename, set()).add(frame.f_lineno)
    return count_lines


if __name__ == "__main__":
    sys.settrace(count_lines)
    suite = unittest.defaultTestLoader.discover(os.path.dirname(__file__), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.settrace(None)
    rows = []
    for name in sorted(os.listdir(CORE)):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        path = os.path.join(CORE, name)
        executable = {line for line in trace._find_executable_linenos(path) if line > 0}
        executed = hits.get(path, set()) & executable
        rows.append({"module": name, "hit": len(executed), "executable": len(executable), "missing": sorted(executable - executed)})
    total = sum(row["executable"] for row in rows)
    covered = sum(row["hit"] for row in rows)
    print(json.dumps({"coverage_percent": round(100 * covered / total, 2), "modules": rows}, indent=2))
    sys.exit(0 if result.wasSuccessful() and covered / total >= 0.9 else 1)
