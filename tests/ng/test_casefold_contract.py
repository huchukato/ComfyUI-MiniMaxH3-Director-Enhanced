"""Detect runtime Unicode changes that would separate editor names from compiler names."""
import hashlib
import json
import unittest
from pathlib import Path

from _pack import REPO


class CasefoldContract(unittest.TestCase):
    def test_browser_digest_matches_current_python_name_equivalence(self):
        expected = json.loads((Path(REPO) / "tests/ng/js/casefold_digest.json").read_text(encoding="utf8"))
        digest = hashlib.sha256()
        for code in range(0x110000):
            if not 0xd800 <= code <= 0xdfff:
                digest.update((chr(code).casefold() + "\0").encode("utf8"))
        self.assertEqual(digest.hexdigest(), expected["sha256"],
                         "Compiler Unicode changed: regenerate the browser table with tests/ng/generate_casefold.py")
