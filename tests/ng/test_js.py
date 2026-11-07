"""Runs the frontend module tests with Node, and syntax-checks every NG module, so one command covers both languages."""
import os
import shutil
import subprocess
import unittest

from _pack import REPO

JS_DIR = os.path.join(REPO, "js", "ng")
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed; the NG frontend was NOT checked")
class Frontend(unittest.TestCase):
    def test_every_module_parses(self):
        for name in sorted(os.listdir(JS_DIR)):
            if name.endswith(".js"):
                result = subprocess.run([NODE, "--check", os.path.join(JS_DIR, name)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, "%s: %s" % (name, result.stderr))

    def test_every_frontend_suite_passes(self):
        """Every tests/ng/js/*.mjs runs, so a new suite cannot be forgotten here."""
        suites = sorted(name for name in os.listdir(os.path.join(REPO, "tests", "ng", "js")) if name.endswith(".mjs"))
        self.assertIn("test_h3s_model.mjs", suites)
        for name in suites:
            with self.subTest(suite=name):
                result = subprocess.run([NODE, os.path.join(REPO, "tests", "ng", "js", name)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()
