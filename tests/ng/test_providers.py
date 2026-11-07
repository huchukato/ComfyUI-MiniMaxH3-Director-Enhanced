"""The provider registry is the one list; these tests hold it to that.

Each test is a mistake we have actually made at some point: a second address list, a sampling
field sent to a provider that rejects it, or a provider marked verified without a run.
"""
import os
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from _pack import module, stub_prompt_server

providers = module("ng.core.providers")


class Registry(unittest.TestCase):
    def test_every_provider_is_complete_and_addressed(self):
        for key, provider in providers.PROVIDERS.items():
            self.assertEqual(provider.id, key, "%s is filed under the wrong id" % provider.label)
            self.assertIn(provider.kind, ("local", "api"))
            # A provider with no address and no custom entry could never be reached.
            self.assertTrue(provider.base_url or provider.id == "custom",
                            "%s has no address" % provider.label)
            self.assertTrue(provider.fields, "%s declares no settings" % provider.label)

    def test_every_declared_field_is_known_readable_and_explained(self):
        for provider in providers.PROVIDERS.values():
            for name in provider.fields:
                self.assertIn(name, providers.SETTING_TYPES,
                              "%s offers %s, which has no type" % (provider.label, name))
                self.assertIn(name, providers.SETTING_HELP,
                              "%s offers %s with no help text" % (provider.label, name))
                self.assertIn(name, providers.DEFAULT_SETTINGS)

    def test_only_providers_with_a_real_run_claim_to_be_verified(self):
        """Guards the honesty rule: a new entry must not arrive claiming to be verified. Ollama has
        four GPU runs behind it and OpenRouter one live API run; anything else says so itself."""
        verified = [p.label for p in providers.PROVIDERS.values() if p.verified]
        self.assertEqual(verified, ["Ollama", "OpenRouter"], "verified=%s" % verified)

    def test_a_listing_that_works_proves_nothing_about_a_key(self):
        """Measured on OpenRouter: /v1/models answers 466 names with no key and with a wrong one.
        The panel must not read a successful listing as "the key is good"."""
        self.assertFalse(providers.key_is_checked_on_listing("openrouter"))
        # A local server needs no key at all, so there is nothing to check there either.
        self.assertFalse(providers.key_is_checked_on_listing("ollama"))
        self.assertTrue(providers.key_is_checked_on_listing("openai"))

    def test_an_unverified_provider_says_why(self):
        for provider in providers.PROVIDERS.values():
            if not provider.verified:
                self.assertTrue(provider.verified_note,
                                "%s is unverified without saying so" % provider.label)

    def test_local_providers_need_no_key_and_api_providers_do(self):
        for provider in providers.PROVIDERS.values():
            if provider.kind == "local" and provider.id != "custom":
                self.assertEqual(provider.auth, "none", "%s should need no key" % provider.label)
            if provider.kind == "api":
                self.assertIn(provider.auth, ("bearer", "x-api-key"),
                              "%s needs an auth scheme" % provider.label)

    def test_only_the_two_known_wire_formats_are_used(self):
        for provider in providers.PROVIDERS.values():
            self.assertIn(provider.generate_path, (providers.OLLAMA_GENERATE, providers.OPENAI_CHAT),
                          "%s speaks a format we have no transport for" % provider.label)

    def test_ollama_keeps_its_own_endpoint_and_fields(self):
        """Ollama is the one provider with a real run behind it; do not quietly reshape it."""
        ollama = providers.get("ollama")
        self.assertEqual(ollama.base_url, "http://127.0.0.1:11434")
        self.assertEqual(ollama.generate_path, providers.OLLAMA_GENERATE)
        self.assertEqual(ollama.models_path, "/api/tags")
        # Ollama has no penalties and no /v1: sending them would be an error, not a default.
        for absent in ("frequency_penalty", "presence_penalty"):
            self.assertNotIn(absent, ollama.fields)

    def test_claude_never_offers_a_seed_or_top_p(self):
        claude = providers.get("anthropic")
        self.assertNotIn("seed", claude.fields, "Claude's API has no seed parameter")
        self.assertNotIn("top_p", claude.fields, "Claude rejects top_p together with temperature")

    def test_custom_is_a_provider_not_a_source_card(self):
        self.assertIn("custom", providers.PROVIDERS)
        for source in providers.SOURCES:
            self.assertNotEqual(source["id"], "custom")
        api = next(s for s in providers.SOURCES if s["id"] == "api")
        self.assertIn("custom", api["providers"], "custom belongs inside the api card")

    def test_every_source_card_lists_providers_that_exist(self):
        for source in providers.SOURCES:
            for key in source["providers"]:
                self.assertIn(key, providers.PROVIDERS, "%s lists the unknown %s" % (source["id"], key))

    def test_there_are_exactly_three_source_cards(self):
        """Local, API and CLIP / Encoder. A fourth "load from disk" card was removed: an installed
        encoder and a connected Load CLIP node reach Generate Text by the same route."""
        self.assertEqual([s["id"] for s in providers.SOURCES], ["local", "api", "clip"])
        for gone in ("disk", "custom"):
            self.assertNotIn(gone, [s["id"] for s in providers.SOURCES],
                             "%s is not a card of its own" % gone)

    def test_an_unknown_provider_is_refused_by_name(self):
        with self.assertRaises(ValueError) as caught:
            providers.get("not-a-provider")
        self.assertIn("ollama", str(caught.exception))

    def test_defaults_only_cover_fields_the_provider_accepts(self):
        for provider in providers.PROVIDERS.values():
            self.assertEqual(set(provider.setting_defaults()), set(provider.fields))
            # A default of 0 would be sent as an explicit choice; False means "leave it out".
            self.assertEqual(provider.setting_defaults().get("fixed_seed"), False)

    def test_media_support_refuses_what_the_provider_cannot_read(self):
        self.assertTrue(providers.get("ollama").supports_media("image"))
        self.assertTrue(providers.get("ollama").supports_media("text"))
        self.assertFalse(providers.get("ollama").supports_media("audio"))
        self.assertFalse(providers.get("llamacpp").supports_media("image"))
        self.assertFalse(providers.get("lmstudio").supports_media("nonsense"),
                         "an unknown medium must not be treated as supported")

    def test_describe_carries_the_list_and_no_secret(self):
        payload = providers.describe()
        self.assertEqual(len(payload["providers"]), len(providers.PROVIDERS))
        self.assertEqual([s["id"] for s in payload["sources"]], [s["id"] for s in providers.SOURCES])
        entry = next(p for p in payload["providers"] if p["id"] == "openai")
        self.assertEqual(entry["fields"], list(providers.get("openai").fields))
        self.assertTrue(entry["help"], "the panel needs the text behind every ?")
        # A description is public information; nothing here may hold a key.
        self.assertNotIn("api_key", str(payload))


class Payload(unittest.TestCase):
    """The matrix has to survive contact with the wire: a field sent to the wrong provider is a
    400 with no useful message, and a field dropped when it should be sent is a silent default."""

    def settings(self, **over):
        base = {"max_tokens": 800, "seed": 42, "fixed_seed": True, "temperature": 0.4,
                "top_p": 0.8, "top_k": 30, "min_p": 0.05, "frequency_penalty": 0.2,
                "presence_penalty": 0.1, "timeout_seconds": 90, "keep_alive": 60}
        base.update(over)
        return base

    def flat(self, provider_id, **over):
        """One level, so a test can assert on names without caring where each one is nested."""
        payload = providers.provider_payload(provider_id, self.settings(**over))
        return {**payload.get("options", {}), **{k: v for k, v in payload.items() if k != "options"}}

    def test_ollama_nests_its_knobs_and_spells_the_limit_num_predict(self):
        payload = providers.provider_payload("ollama", self.settings())
        self.assertEqual(payload["options"], {"temperature": 0.4, "top_p": 0.8, "top_k": 30,
                                              "min_p": 0.05, "num_predict": 800, "seed": 42})
        # keep_alive belongs beside options, not inside them.
        self.assertEqual(payload["keep_alive"], 60)

    def test_ollama_never_receives_the_penalties(self):
        """The single most likely mistake: these two have no place in an Ollama request."""
        flat = self.flat("ollama")
        for absent in ("frequency_penalty", "presence_penalty"):
            self.assertNotIn(absent, flat, "%s reached Ollama" % absent)

    def test_openai_takes_its_knobs_flat(self):
        payload = providers.provider_payload("openai", self.settings())
        self.assertEqual(payload, {"max_tokens": 800, "seed": 42, "temperature": 0.4,
                                   "top_p": 0.8, "frequency_penalty": 0.2, "presence_penalty": 0.1})
        self.assertNotIn("options", payload, "OpenAI takes a flat body")

    def test_claude_never_receives_a_seed_or_top_p(self):
        payload = providers.provider_payload("anthropic", self.settings())
        self.assertNotIn("seed", payload)
        self.assertNotIn("top_p", payload)
        self.assertEqual(payload["max_tokens"], 800, "the fields it does accept must still arrive")

    def test_timeout_and_the_switch_itself_are_never_in_the_body(self):
        for provider in ("ollama", "openai", "anthropic"):
            flat = self.flat(provider)
            self.assertNotIn("timeout_seconds", flat, "%s got a timeout in its body" % provider)
            self.assertNotIn("fixed_seed", flat, "%s got the switch in its body" % provider)

    def test_an_unticked_fixed_seed_sends_no_seed_at_all(self):
        """The reason the checkbox exists: a provider reads a seed as "be reproducible"."""
        for provider in ("openai", "ollama", "openrouter"):
            self.assertNotIn("seed", self.flat(provider, fixed_seed=False),
                             "%s was pinned without being asked" % provider)

    def test_only_declared_fields_survive_the_matrix(self):
        for provider_id, provider in providers.PROVIDERS.items():
            flat = self.flat(provider_id)
            # num_predict is Ollama's own name for max_tokens; everything else is a registry name.
            allowed = set(provider.fields)
            if provider.generate_path == providers.OLLAMA_GENERATE:
                allowed.add("num_predict")
            for name in flat:
                self.assertIn(name, allowed, "%s sent %s, which it does not accept"
                              % (provider.label, name))

    def test_defaults_alone_produce_an_empty_body(self):
        """No field the user did not touch: a fresh node must not override provider defaults."""
        for provider in providers.PROVIDERS.values():
            self.assertEqual(providers.provider_payload(provider.id, {}), {}, provider.label)
            self.assertEqual(providers.provider_payload(provider.id, None),
                             providers.provider_payload(provider.id, {}))

    def test_an_unknown_provider_is_refused_before_any_payload(self):
        with self.assertRaises(ValueError):
            providers.provider_payload("gpt9", {"temperature": 1})


class ModelListing(unittest.IsolatedAsyncioTestCase):
    """Both protocols, and the one promise that matters: a key goes out as a header and nowhere
    else. A name that came back must be readable by the user, and a wrong address must say so."""

    async def asyncSetUp(self):
        from aiohttp import web
        stub_prompt_server()
        self.models = module("ng.adapters.models")
        self.seen = []
        self.status = 200

        async def serve(request):
            self.seen.append((request.path, request.headers.get("Authorization")))
            if self.status != 200:
                return web.Response(status=self.status, text="nope")
            if request.path.endswith("/api/tags"):
                return web.json_response({"models": [{"name": "qwen2.5vl:7b"}, {"name": "llama3:8b"}]})
            return web.json_response({"data": [{"id": "gpt-4o-mini"}, {"id": "o3-mini"}]})

        app = web.Application()
        app.router.add_get("/{tail:.*}", serve)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = "http://127.0.0.1:%d" % site._server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_ollama_asks_its_own_path(self):
        names, reason = await self.models.listing("ollama", self.url)
        self.assertEqual(names, ["llama3:8b", "qwen2.5vl:7b"])
        self.assertEqual(reason, "")
        self.assertEqual(self.seen[0][0], "/api/tags")

    async def test_an_openai_provider_asks_v1_models(self):
        names, reason = await self.models.listing("openai", self.url + "/v1")
        self.assertEqual(names, ["gpt-4o-mini", "o3-mini"])
        self.assertEqual(self.seen[0][0], "/v1/models")

    async def test_a_base_with_v1_is_not_doubled(self):
        """The old /v1/v1 404, in a new costume: asking twice would be a silent empty list."""
        for base in (self.url, self.url + "/v1", self.url + "/v1/"):
            with self.subTest(base=base):
                self.seen.clear()
                await self.models.listing("openai", base)
                self.assertEqual(self.seen[0][0], "/v1/models")

    async def test_the_key_travels_as_a_header_and_in_nothing_else(self):
        key = "sk-or-v1-secret-value"
        names, _ = await self.models.listing("openrouter", self.url + "/v1", key)
        self.assertTrue(names)
        self.assertEqual(self.seen[0][1], "Bearer " + key)

    async def test_empty_override_uses_the_registry_default_address(self):
        for provider in ("ollama", "openai", "lmstudio"):
            entry = providers.get(provider)
            # Registry fallback is exercised against the local fixture; production default hosts stay unused.
            with self.subTest(provider=provider), patch.object(self.models.providers, "get",
                                                             return_value=replace(entry, base_url=self.url)):
                names, reason = await self.models.listing(provider, "")
                self.assertTrue(names)
                self.assertEqual(reason, "")
                self.assertEqual(self.seen[-1][0], entry.models_path)
        self.assertEqual(len(self.seen), 3)

    async def test_custom_without_a_default_address_is_refused_without_a_request(self):
        with patch.object(self.models.aiohttp, "ClientSession") as client:
            with self.assertRaisesRegex(ValueError, "address"):
                await self.models.listing("custom", "")
            client.assert_not_called()
        self.assertEqual(self.seen, [], "an empty address must not produce a request")

    async def test_an_unreachable_server_is_an_empty_list_and_a_reason(self):
        names, reason = await self.models.listing("ollama", "http://127.0.0.1:9")
        self.assertEqual(names, [], "no names and no exception: the panel can still be typed into")
        self.assertIn("Could not reach", reason)

    async def test_a_refusal_names_the_status_and_the_address(self):
        self.status = 401
        names, reason = await self.models.listing("openrouter", self.url + "/v1", "sk-test-key")
        self.assertEqual(names, [])
        self.assertIn("401", reason)
        self.assertIn("/v1/models", reason)

    async def test_a_reply_we_cannot_read_says_so(self):
        # A dict that carries no list at all reads as nothing, not as a crash.
        for payload in ({}, {"data": {"a": 1}}, {"models": {}}, {"data": [{"nothing": 1}]}):
            with self.subTest(payload=payload):
                self.assertEqual(self.models._ids(payload), [])
        # A bare string where a list belongs must be refused: iterating it would read the words
        # of the error message as a list of model names.
        for payload in ("gpt-4o", {"data": "gpt-4o"}, {"models": "gpt-4o"}):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "single model name"):
                self.models._ids(payload)
        # Names sent as bare strings are still names, sorted and without duplicates.
        self.assertEqual(self.models._ids(["b", "a", "b"]), ["a", "b"])
        self.assertEqual(self.models._ids({"data": [{"id": "z"}, {"id": "a"}]}), ["a", "z"])

    async def test_an_unknown_provider_is_refused_before_any_request(self):
        with self.assertRaisesRegex(ValueError, "Choose one of"):
            await self.models.listing("gpt9", self.url)
        self.assertEqual(self.seen, [])


class KeyStore(unittest.TestCase):
    """A widget value is serialised into every saved and shared workflow, so a key must never be
    one. These tests hold that line: the secret lives in one file and the panel is told only that
    a key exists."""

    def setUp(self):
        self.keys = module("ng.adapters.keys")
        self.directory = tempfile.TemporaryDirectory()
        self.root = self.directory.name

    def tearDown(self):
        self.directory.cleanup()

    def test_a_key_is_stored_and_read_back(self):
        self.assertTrue(self.keys.write(self.root, "openrouter", "sk-or-v1-abcdefghijklmnop"))
        self.assertEqual(self.keys.resolve(self.root, "openrouter"), "sk-or-v1-abcdefghijklmnop")

    def test_an_empty_key_forgets_the_old_one(self):
        self.keys.write(self.root, "openai", "sk-abcdefghijklmnop")
        self.assertFalse(self.keys.write(self.root, "openai", ""))
        self.assertIsNone(self.keys.resolve(self.root, "openai"))
        self.assertEqual(self.keys.read(self.root), {})

    def test_two_providers_keep_their_own_key(self):
        self.keys.write(self.root, "openai", "sk-aaaaaaaaaaaaaaaa")
        self.keys.write(self.root, "openrouter", "sk-bbbbbbbbbbbbbbbb")
        self.assertEqual(self.keys.resolve(self.root, "openai"), "sk-aaaaaaaaaaaaaaaa")
        self.assertEqual(self.keys.resolve(self.root, "openrouter"), "sk-bbbbbbbbbbbbbbbb")

    def test_the_panel_is_told_that_a_key_exists_and_never_what_it_is(self):
        self.keys.write(self.root, "openrouter", "sk-or-v1-abcdefghijklmnop", "OPENROUTER_API_KEY")
        described = self.keys.describe(self.root)
        self.assertTrue(described["openrouter"]["set"])
        self.assertEqual(described["openrouter"]["env"], "OPENROUTER_API_KEY")
        self.assertNotIn("sk-or-v1", str(described), "the answer handed to the panel carried the key")
        self.assertNotIn("key", described["openrouter"], "only a flag, never the secret")

    def test_the_stored_file_never_leaves_the_key_folder(self):
        """A name like ..\\.. must not write outside the user's own folder."""
        for hostile in ("../../evil", "..\\..\\evil", "C:/evil"):
            with self.subTest(name=hostile):
                with self.assertRaises(ValueError):
                    self.keys.write(self.root, hostile, "sk-abcdefghijklmnop")

    def test_only_a_registered_provider_may_hold_a_key(self):
        with self.assertRaisesRegex(ValueError, "Choose a provider"):
            self.keys.write(self.root, "not-a-provider", "sk-abcdefghijklmnop")
        self.assertEqual(self.keys.read(self.root), {})

    def test_something_that_is_not_a_key_is_refused(self):
        for value in ("short", "x" * 500, 123):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.keys.write(self.root, "openai", value)

    def test_a_broken_file_reads_as_no_keys_rather_than_raising(self):
        """A damaged key store must not stop the panel from opening."""
        with open(os.path.join(self.root, "api_keys.json"), "w", encoding="utf8") as stream:
            stream.write("{not json")
        self.assertEqual(self.keys.read(self.root), {})
        self.assertEqual(self.keys.describe(self.root), {})

    def test_the_stored_key_wins_and_without_one_the_fallback_still_works(self):
        # Nothing stored yet: the caller's key (the env-var route) is passed through untouched, so
        # a user who already sets OPENAI_API_KEY keeps working without storing anything.
        self.assertEqual(self.keys.resolve(self.root, "openai", "sk-from-environment"), "sk-from-environment")
        self.assertIsNone(self.keys.resolve(self.root, "openai"))
        # A stored key takes precedence over the environment, which is what "I typed mine here" means.
        self.keys.write(self.root, "openai", "sk-stored-here-1234")
        self.assertEqual(self.keys.resolve(self.root, "openai", "sk-from-environment"),
                         "sk-stored-here-1234")
        # A key stored for one provider serves only that provider, whichever fallback was offered.
        self.keys.write(self.root, "openrouter", "sk-openrouter-only-1")
        self.assertEqual(self.keys.resolve(self.root, "openai", "sk-from-environment"),
                         "sk-stored-here-1234")
        self.assertEqual(self.keys.resolve(self.root, "openrouter", "sk-from-environment"),
                         "sk-openrouter-only-1")


if __name__ == "__main__":
    unittest.main()
