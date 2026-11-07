"""Keep the confirmed Bug-Hunter cases in the standard suite without moving their originals."""
import importlib.util
from pathlib import Path
import unittest


def load_tests(loader, tests, pattern):
    for filename in ("bug_045_usage_role_pair.py", "bug_046_fl2va_picture_label_refused.py",
                     "bug_057_lyrics_negative_start_offset.py", "bug_054_split_narrator_named_card.py",
                     "bug_060_video_images_duration.py", "bug_061_ai_json_trailing_prose.py"):
        path = Path(__file__).parent / "regressions" / filename
        spec = importlib.util.spec_from_file_location("fixer_" + path.stem, path)
        suite = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(suite)
        tests.addTests(loader.loadTestsFromModule(suite))
    return tests


if __name__ == "__main__":
    unittest.main()
