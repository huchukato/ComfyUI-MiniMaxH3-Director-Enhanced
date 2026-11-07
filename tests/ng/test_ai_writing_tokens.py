"""Writing shots and part prompts gets at least WRITING_TOKENS, whatever the AI Loader's lower default (2026-10-18: a 10 s
shot with two beats stopped mid-JSON at 512 tokens)."""
import unittest

from _pack import module, stub_prompt_server

stub_prompt_server()
routes = module("ng.nodes.analysis_routes")


class WritingTokens(unittest.TestCase):
    def test_a_low_setting_is_raised_for_writing(self):
        payload = routes._writing({"provider": {"model": "qwen3.5:9b", "max_tokens": 512}, "idea": "x"})
        self.assertEqual(payload["provider"]["max_tokens"], routes.WRITING_TOKENS)
        self.assertEqual(payload["provider"]["model"], "qwen3.5:9b")
        self.assertEqual(payload["idea"], "x")

    def test_a_higher_setting_stays(self):
        self.assertEqual(routes._writing({"provider": {"max_tokens": 4096}})["provider"]["max_tokens"], 4096)

    def test_a_payload_without_provider_is_left_alone(self):
        self.assertEqual(routes._writing({"idea": "x"}), {"idea": "x"})
        self.assertEqual(routes._writing(None), None)


if __name__ == "__main__":
    unittest.main()
