"""Run the reviewed bug regressions with the normal NG suite; pending findings remain separate."""
import os
import shutil
import subprocess
import unittest

from _pack import REPO
from regressions.audio_source_window import AudioSourceWindow, VoiceAndLane
# Codex findings fixed by Claude (2026-10-05); BUG-041's own test guesses a parameter name, test_analysis covers it.
from regressions.bug_033_auto_direct_provider import AutoDirectCloudProvider
# BUG-034 (Build H3 prompt on a cloud provider) left with the button itself (2026-10-05); the writer is tested in test_analysis.
from regressions.bug_036_text_card_no_text import TextCardNoTextWarning
from regressions.bug_037_picture_cap_silent import PictureCapReported
from regressions.bug_038_models_anthropic_headers import ModelsAuthHeadersTest

NODE = shutil.which("node")
VERIFIED_JS = ("timeline_boundaries.test.mjs", "ai_snapshot.test.mjs", "studio_actions.test.mjs", "review_state_pending.test.mjs",
               "bug_035_spoken_language.test.mjs", "bug_039_preset_save_disabled.test.mjs", "bug_040_studio_mode_toggle_auto.test.mjs")


@unittest.skipUnless(NODE, "Node is required for the verified Studio regressions")
class VerifiedFrontendRegressions(unittest.TestCase):
    def test_verified_studio_regressions(self):
        files = [os.path.join(REPO, "tests", "ng", "regressions", name) for name in VERIFIED_JS]
        result = subprocess.run([NODE, "--test", *files], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
