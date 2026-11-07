"""Retain the verified Python Bug-Hunter regressions unchanged in the normal suite."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_tests(loader, tests, pattern):
    for filename in ("bug_068_analysis_json_trailing_prose.py", "bug_069_batch_plan_duplicate_label.py",
                     "bug_070_part_prompt_fenced_prose_leak.py", "bug_071_models_listing_timeout_crash.py",
                     "bug_072_analyze_all_partial_success_false_error.py", "bug_073_context_build_none_coercion.py",
                     "bug_074_split_plain_mentions_none_name_crash.py", "bug_075_text_card_none_text_crash.py",
                     "bug_077_preview_runtime_german_strings.py", "bug_080_character_voice_lane_ref_clip_dropped.py",
                     "bug_081_video_soundtrack_missing_audio_vae.py", "bug_082_motion_segments_negative_length.py",
                     "bug_083_locked_spans_ignores_end_s.py"):
        path = Path(__file__).parent / "regressions" / filename
        spec = importlib.util.spec_from_file_location("latest_" + path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


if __name__ == "__main__":
    unittest.main()
