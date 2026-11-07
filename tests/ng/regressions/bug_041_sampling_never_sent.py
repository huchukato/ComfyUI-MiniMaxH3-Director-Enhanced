"""BUG-041: the AI Loader's sampling settings never reach the provider.

The H3 AI Loader offers Temperature, Top P, Top K, Min P, Frequency penalty,
Presence penalty and a Seed with a "Fixed seed" switch, each with a tooltip
saying what it changes, and /ng/providers advertises per provider which of them
that provider accepts. The user drags them and expects the answer to change.

Nothing happens. ng/adapters/analysis.py:_wire() builds the sampling half of the
request with providers.provider_payload() and then forwards only three values:

    flat = {name: values[name] for name in ("max_tokens", "keep_alive") if name in values}
    return {"max_tokens": ..., "keep_alive": ..., "timeout": ...}

so temperature, top_p, top_k, min_p, both penalties and the seed are computed and
thrown away. The transport it calls into, minimax_media.vlm_generate(), has no
parameter for any of them either.

ng/adapters/h3_prompt.py:build() and ng/adapters/auto_direct.py:direct() do not
build the payload at all; they pass max_tokens, timeout and keep_alive by hand.

Measured end to end against a local Ollama through a recording proxy: an
Analyze with temperature 0.3/top_k 40 and the same request with temperature
1.9/top_k 100/Fixed seed ticked/seed 12345 produced byte-identical bodies,
options = {"num_predict": 512}. Same for Build H3 prompt and for the Studio's
split into shots.

The test calls the three real adapters and inspects what they hand to the
transport, which is the product's own boundary.
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module, stub_prompt_server

stub_prompt_server()
providers = module("ng.core.providers")
analysis_mod = module("ng.adapters.analysis")
analysis_core = module("ng.core.analysis")
h3_prompt_mod = None   # removed module, see REMOVED below
REMOVED = 'The text card\'s "Build H3 prompt" (ng/adapters/h3_prompt.py) was removed; Make H3 prompt in the Studio replaced it.'
auto_direct_mod = module("ng.adapters.auto_direct")
legacy = module("minimax_media")

# What the AI Loader panel sends after the user drags every sampling control.
DRAGGED = {"schema_version": 2, "provider": "ollama", "base_url": "http://127.0.0.1:11434",
           "model": "some-model", "api_key_env": "", "vision": True, "audio": False,
           "timeout_seconds": 120, "max_tokens": 512, "keep_alive": 0,
           "temperature": 1.9, "top_p": 0.5, "top_k": 100, "min_p": 0.5,
           "frequency_penalty": 1.2, "presence_penalty": 0.8, "seed": 12345,
           "fixed_seed": True}

ANSWER = json.dumps({"description": "A mage in a dark hall.", "content": "character", "why": "Dark."})


def sent_sampling(call_kwargs):
    """The sampling values that reached the transport, from wherever the adapter put them."""
    flat = {key: value for key, value in (call_kwargs or {}).items()
            if key not in ("system_prompt", "timeout", "auth", "api_key")}
    sampling = flat.pop("sampling", None) or {}       # the adapters hand the provider payload on whole as `sampling`
    options = flat.pop("options", None) or sampling.pop("options", None) or {}
    return dict(flat, **sampling, **options)


def run_analyze():
    with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as send:
        send.return_value = ANSWER
        asyncio.run(analysis_mod.analyze({
            "media": "text", "provider": DRAGGED,
            "widgets": {"text": "A mage sings.", "name": "N", "content": "shot", "usage": "style"}}))
        assert send.await_args, "the analysis must reach the provider"
        return sent_sampling(send.await_args.kwargs)


def run_build():
    with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as send:
        send.return_value = "A mage stands in a dark hall."
        asyncio.run(h3_prompt_mod.build(
            {"note": "A mage sings.", "seconds": 8, "preset": "global", "provider": DRAGGED}))
        assert send.await_args, "Build H3 prompt must reach the provider"
        return sent_sampling(send.await_args.kwargs)


def run_direct():
    payload = {"director": {"idea": "A mage sings.", "project_seconds": 10, "shots": ""},
               "contexts": [], "provider": DRAGGED, "mode": "auto"}
    answer = ('{"shots":[{"start_s":0,"end_s":10,"action":"A mage sings.","camera":"Static",'
              '"dialogue":""}],"soundscape":"Room tone","music":"N/A"}')
    with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as send:
        send.return_value = answer
        asyncio.run(auto_direct_mod.direct(payload))
        assert send.await_args, "split into shots must reach the provider"
        return sent_sampling(send.await_args.kwargs)


class SamplingReachesProvider(unittest.TestCase):
    def test_bug_041_the_registry_says_ollama_takes_temperature(self):
        # Precondition of the whole report: the product itself lists the field.
        payload = providers.provider_payload("ollama", {"temperature": 1.9, "top_k": 100,
                                                        "fixed_seed": True, "seed": 1})
        self.assertIn("temperature", payload.get("options", {}),
                      "the registry must list temperature for Ollama")

    def test_bug_041_analyze_must_send_the_sampling_settings_the_user_chose(self):
        got = run_analyze()
        self.assertEqual(got.get("temperature"), 1.9,
                         "the Temperature the user chose never reached the provider: %r" % (got,))
        self.assertEqual(got.get("top_k"), 100,
                         "the Top K the user chose never reached the provider: %r" % (got,))
        self.assertEqual(got.get("seed"), 12345,
                         "a ticked Fixed seed never reached the provider: %r" % (got,))

    @unittest.skip(REMOVED)
    def test_bug_041_build_h3_prompt_must_send_the_sampling_settings(self):
        got = run_build()
        self.assertEqual(got.get("temperature"), 1.9,
                         "Build H3 prompt drops the Temperature: %r" % (got,))

    def test_bug_041_split_into_shots_must_send_the_sampling_settings(self):
        got = run_direct()
        self.assertEqual(got.get("temperature"), 1.9,
                         "split into shots drops the Temperature: %r" % (got,))

    def test_control_max_tokens_timeout_and_keep_alive_still_arrive(self):
        # The green control: the three values that are forwarded today must keep arriving.
        wire = analysis_mod.wire(analysis_core.ProviderConfig.from_dict(DRAGGED))
        self.assertEqual(wire["max_tokens"], 512)
        self.assertEqual(wire["keep_alive"], 0)
        self.assertEqual(wire["timeout"], 120)

    def test_control_an_unticked_fixed_seed_stays_out_of_the_request(self):
        # The green control for the rule behind the seed: it is only sent when asked for.
        payload = providers.provider_payload("ollama", {"seed": 12345, "fixed_seed": False,
                                                        "temperature": 1.9})
        self.assertNotIn("seed", payload.get("options", {}))


if __name__ == "__main__":
    unittest.main()

def run_analyze():
    with patch.object(legacy, "vlm_generate", new_callable=AsyncMock) as send:
        send.return_value = ANSWER
        asyncio.run(analysis_mod.analyze({
            "media": "text", "provider": DRAGGED,
            "widgets": {"text": "A mage sings.", "name": "N", "content": "shot", "usage": "style"}}))
        assert send.await_args, "the analysis must reach the provider"
        return sent_sampling(send.await_args.kwargs)
