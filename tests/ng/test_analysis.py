import base64
import io
import json
import os
import tempfile
import unittest
import wave
from unittest.mock import patch

from _pack import module, comfy_available, stub_prompt_server

core = module("ng.core.analysis")


class ContentRoles(unittest.TestCase):
    """Found by a real OpenRouter run: gemma answered `content: dialogue` for a picture. The value
    passed every check because the parse only knew the union of all media, so a card could end up
    holding a role it can never have."""

    def test_a_picture_cannot_be_answered_as_dialogue(self):
        answer = '{"description": "a red rectangle", "content": "dialogue"}'
        got = core.parse_suggestion(answer, "image")
        # Named and left out; the description is still offered.
        self.assertEqual((got.description, got.content), ("a red rectangle", None))
        self.assertIn("“dialogue” does not fit this image card", got.why)
        self.assertIsNone(core.parse_suggestion('{"description": "x", "content": "voice"}', "image").content)

    def test_every_medium_only_accepts_its_own_roles(self):
        for media, allowed in core.CONTENT_BY_MEDIA.items():
            for wrong in set(core.CONTENT_KINDS) - set(allowed):
                with self.subTest(media=media, wrong=wrong):
                    self.assertIsNone(core.parse_suggestion('{"description": "x", "content": "%s"}' % wrong, media).content)

    def test_the_roles_a_medium_does_offer_are_accepted(self):
        for media, allowed in core.CONTENT_BY_MEDIA.items():
            for good in allowed:
                with self.subTest(media=media, good=good):
                    got = core.parse_suggestion('{"description": "x", "content": "%s"}' % good, media)
                    self.assertEqual(got.content, good)

    def test_the_prompt_offers_only_what_the_card_can_hold(self):
        """Asking for the whole union is what invited the wrong answer in the first place. Checked
        on the offered list itself: "effect" is a substring of "sound_effect", so a substring test
        over the whole prompt would flag a role the audio card really can hold."""
        for media, allowed in core.CONTENT_BY_MEDIA.items():
            offered = core.analysis_prompt(media, "").split("content (exactly one of: ")[1].split(")")[0]
            self.assertEqual([name.strip() for name in offered.split(",")], list(allowed),
                             "the %s prompt offers the wrong roles" % media)

    def test_usage_is_asked_from_the_roles_the_card_shows_not_as_prose(self):
        # "usage (optional, how the director should use it)" got "To capture the emotional depth ..." from Ollama,
        # which no card can hold; the card's role was never filled by an analysis.
        prompt = core.analysis_prompt("image", "", {"content": ["character", "face", "nonsense"], "usage": ["reference", "first_frame"]})
        self.assertIn("content (exactly one of: character, face)", prompt)
        self.assertIn("usage (exactly one of: reference = keep this figure or thing recognizable; first_frame = the opening picture)", prompt)
        self.assertNotIn("how the director should use it", prompt)
        # The image description becomes the Subject definition; one sentence lost the elf's dress, choker and fangs.
        self.assertIn("clothing with colours, accessories and props", prompt)
        self.assertIn("one concise sentence", core.analysis_prompt("audio", ""))
        self.assertNotIn("content (", core.analysis_prompt("text", "", {"content": [], "usage": ["rule"]}), "the Text card shows no content choice")
        for media, roles in core.USAGE_BY_MEDIA.items():
            self.assertEqual(set(core.USAGE_MEANING[media]), set(roles), "every %s role is explained to the model" % media)
        # A Text card's hidden default content ("rules") made a 4B model call a character description a rule.
        text = core.analysis_prompt("text", "rules")
        self.assertNotIn("Focus on rules", text)
        self.assertIn("character = describes a person or creature", text)
        self.assertIn("camera = how the camera works", text)

    def test_a_video_answered_per_still_becomes_one_suggestion(self):
        # Real Qwen3-VL 4B answer for ng_test_video.mp4; it failed with "analysis.description: is required".
        answer = json.dumps({"stills": [
            {"description": "A hand presses down on a ball of dough.", "content": "motion", "usage": "motion", "why": "The hand presses."},
            {"description": "The hand shapes the dough.", "content": "motion", "usage": "motion", "why": "It goes on."}]})
        got = core.parse_suggestion(answer, "video")
        self.assertEqual(got.description, "A hand presses down on a ball of dough. The hand shapes the dough.")
        self.assertEqual((got.content, got.usage, got.why), ("motion", "motion", "The hand presses."))
        self.assertIn("one object for the whole clip", core.analysis_prompt("video", ""))
        with self.assertRaises(ValueError):
            core.parse_suggestion(json.dumps({"stills": [{"content": "motion"}]}), "video")

    def test_a_role_written_as_a_key_is_read_as_the_usage(self):
        # Real Qwen3-VL 4B answer for "Never show any text, logos or watermarks on screen." on a Text card.
        got = core.parse_suggestion('{"constraint": "Never show any text, logos or watermarks on screen", "why": "Keeps it clean."}', "text")
        self.assertEqual((got.usage, got.why), ("constraint", "Keeps it clean."))
        self.assertEqual(core.parse_suggestion('{"usage": "camera"}', "text").usage, "camera", "a Text card needs no description")
        with self.assertRaises(ValueError):
            core.parse_suggestion('{"usage": "reference"}', "image")
        self.assertIn('"usage": "<one word from the usage list>"', core.analysis_prompt("text", "", {"content": [], "usage": ["rule"]}))

    def test_an_answer_with_no_role_at_all_is_still_fine(self):
        got = core.parse_suggestion('{"description": "just a sentence"}', "image")
        self.assertIsNone(got.content)

    def test_unreadable_answers_distinguish_refusal_syntax_and_cutoff(self):
        for answer in ("", "I cannot help with that.", "{not JSON"):
            with self.subTest(answer=answer):
                with self.assertRaisesRegex(ValueError, "not readable JSON") as caught:
                    core.parse_suggestion(answer, "image")
                self.assertNotIn("Max tokens", str(caught.exception))
        with self.assertRaisesRegex(ValueError, "not readable JSON") as caught:
            core.parse_suggestion('{"description": "A woman', "image")
        self.assertIn("Max tokens", str(caught.exception))

    def test_the_nodes_and_the_core_share_one_list(self):
        """The parse checks against core, so the node's dropdown has to be the very same list."""
        nodes = module("ng.nodes.context_nodes")
        self.assertEqual(nodes.CONTENT_BY_MEDIA, core.CONTENT_BY_MEDIA)


class Suggestions(unittest.TestCase):
    def test_provider_roundtrip_and_unknown_credentials(self):
        config = core.ProviderConfig(model="local-model", vision=False, audio=True, api_key_env="MY_VLM_KEY")
        self.assertEqual(core.ProviderConfig.from_dict(config.to_dict()), config)
        # 3 is a version nobody has written yet: a future field must not slip into an old workflow
        # by simply raising the number. 2 is current and therefore accepted, so the guard moves on.
        for change in ({"provider": "magic"}, {"vision": "yes"}, {"audio": 1}, {"fixed_seed": "yes"},
                       {"api_key": "secret"}, {"schema_version": 3}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                core.ProviderConfig.from_dict({**config.to_dict(), **change})
        for address in ("ftp://server", "http://name:key@server", "https://server?api_key=secret", "https://server#key"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                core.ProviderConfig.from_dict({**config.to_dict(), "base_url": address})

    def test_panel_settings_are_range_checked_and_defaulted(self):
        # The panel offers timeout, max_tokens and keep_alive, so the core has to hold their bounds.
        defaults = core.ProviderConfig.from_dict({"schema_version": 1})
        self.assertEqual((defaults.timeout_seconds, defaults.max_tokens, defaults.keep_alive), (120, 512, 0))
        self.assertEqual(core.ProviderConfig.from_dict({"schema_version": 1, "timeout_seconds": 30}).timeout_seconds, 30)
        for change in ({"timeout_seconds": 0}, {"timeout_seconds": 5000}, {"max_tokens": 12}, {"max_tokens": 99999},
                       {"keep_alive": -1}, {"timeout_seconds": 12.5}, {"timeout_seconds": "120"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                core.ProviderConfig.from_dict({"schema_version": 1, **change})

    def test_panel_only_field_is_not_part_of_the_saved_provider(self):
        # `source` steers the cards; a saved workflow must not carry it into the config.
        self.assertNotIn("source", core.ProviderConfig().to_dict())


class SchemaMigration(unittest.TestCase):
    """Version 2 added the sampling fields. An old workflow must open, and must not acquire a
    sampling choice the user never made."""

    def old(self, **over):
        """Exactly what version 1 wrote: nine fields and the version number."""
        data = {"schema_version": 1, "provider": "ollama", "base_url": "http://127.0.0.1:11434",
                "model": "qwen2.5vl:7b", "api_key_env": "", "vision": True, "audio": False,
                "timeout_seconds": 90, "max_tokens": 1024, "keep_alive": 30}
        data.update(over)
        return data

    def test_a_version_1_workflow_still_reads(self):
        config = core.ProviderConfig.from_dict(self.old())
        self.assertEqual((config.provider, config.model, config.max_tokens), ("ollama", "qwen2.5vl:7b", 1024))
        self.assertEqual(config.timeout_seconds, 90)
        self.assertEqual(config.keep_alive, 30)

    def test_an_old_workflow_keeps_the_settings_it_did_have(self):
        old = self.old(vision=False, audio=True)
        config = core.ProviderConfig.from_dict(old)
        self.assertFalse(config.vision)
        self.assertTrue(config.audio)

    def test_an_old_workflow_gets_defaults_and_not_a_chosen_sampling(self):
        """The important half: defaults are the provider's, and fixed_seed is off."""
        config = core.ProviderConfig.from_dict(self.old())
        self.assertEqual(config.temperature, core.ProviderConfig().temperature)
        self.assertEqual(config.top_p, core.ProviderConfig().top_p)
        self.assertEqual(config.top_k, core.ProviderConfig().top_k)
        self.assertEqual(config.seed, 0)
        self.assertFalse(config.fixed_seed, "an old workflow must not come back pinned")

    def test_an_old_workflow_saves_as_the_current_version(self):
        saved = core.ProviderConfig.from_dict(self.old()).to_dict()
        self.assertEqual(saved["schema_version"], 2)
        # And it survives a second round trip, which is what reopening the saved file does.
        self.assertEqual(core.ProviderConfig.from_dict(saved), core.ProviderConfig.from_dict(self.old()))

    def test_a_new_field_cannot_be_sneaked_into_an_old_workflow(self):
        """Version 1 drops anything it did not know, so nothing back-fills a value silently."""
        config = core.ProviderConfig.from_dict(self.old(temperature=1.9, fixed_seed=True, seed=7))
        self.assertNotEqual(config.temperature, 1.9)
        self.assertEqual(config.seed, 0)
        self.assertFalse(config.fixed_seed)

    def test_a_sampling_value_outside_its_range_is_refused(self):
        for change in ({"temperature": -0.1}, {"temperature": 2.5}, {"top_p": 1.4}, {"top_k": 500},
                       {"min_p": -1}, {"frequency_penalty": 3}, {"presence_penalty": -9},
                       {"top_k": 30.5}, {"temperature": "warm"}, {"seed": -1}, {"seed": 2 ** 33},
                       {"fixed_seed": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                core.ProviderConfig.from_dict({"schema_version": 2, **change})

    def test_every_boolean_round_trips_both_ways(self):
        """fixed_seed was once validated but never handed to the constructor, so a ticked box came
        back unticked and the seed was silently dropped from every request. Check every flag."""
        for name in ("vision", "audio", "fixed_seed"):
            for value in (True, False):
                with self.subTest(name=name, value=value):
                    config = core.ProviderConfig.from_dict({"schema_version": 2, name: value})
                    self.assertIs(getattr(config, name), value, "%s did not survive" % name)
                    self.assertEqual(core.ProviderConfig.from_dict(config.to_dict()), config)

    def test_a_ticked_fixed_seed_reaches_the_request_and_an_unticked_one_does_not(self):
        for value, expected in ((True, 5), (False, None)):
            with self.subTest(fixed_seed=value):
                config = core.ProviderConfig.from_dict({"schema_version": 2, "provider": "ollama",
                                                        "seed": 5, "fixed_seed": value})
                options = core.providers.provider_payload(config.provider, config.to_dict())["options"]
                self.assertEqual(options.get("seed"), expected)


class ThroughTheNode(unittest.IsolatedAsyncioTestCase):
    """The path a real request takes: node input -> config -> payload. provider_from_values used
    to stamp schema_version 1 on fresh values, so the migration dropped every new field on the
    floor and the panel's settings never reached the provider."""

    @classmethod
    def setUpClass(cls):
        cls.available = comfy_available()

    def values(self, **over):
        """Only what a node really hands to the config. execute() pops source, clip and the three
        local_* fields before this point, so passing them would test a path that never happens."""
        data = {"provider": "ollama", "base_url": "http://127.0.0.1:11434",
                "model": "qwen2.5vl:7b", "api_key_env": "", "vision": True, "audio": False,
                "timeout_seconds": 120, "max_tokens": 512, "keep_alive": 0, "temperature": 0.3,
                "top_p": 0.9, "top_k": 40, "min_p": 0.0, "frequency_penalty": 0.0,
                "presence_penalty": 0.0, "seed": 0, "fixed_seed": False}
        data.update(over)
        return data

    def test_a_chosen_sampling_value_survives_the_node(self):
        adapter = module("ng.adapters.ai_provider")
        config = adapter.provider_from_values(
            "local", None, self.values(temperature=0.65, top_k=7, seed=99, fixed_seed=True))
        self.assertEqual(config.temperature, 0.65)
        self.assertEqual(config.top_k, 7)
        self.assertEqual(config.seed, 99)
        self.assertTrue(config.fixed_seed)

    def test_the_nodes_own_values_reach_the_request_body(self):
        adapter = module("ng.adapters.ai_provider")
        registry = module("ng.core.providers")
        config = adapter.provider_from_values("local", None, self.values(top_k=7, fixed_seed=True, seed=99))
        options = registry.provider_payload(config.provider, config.to_dict())["options"]
        self.assertEqual(options["top_k"], 7)
        self.assertEqual(options["seed"], 99)

    def test_clip_source_ignores_a_stale_http_address(self):
        """A connected CLIP is used directly; the HTTP fields left from another card must not stop it (user workflow 2026-10-04)."""
        adapter = module("ng.adapters.ai_provider")
        clip = object()
        provider = adapter.provider_from_values("clip", clip, self.values(provider="custom", base_url="custom", api_key_env="NOPE"))
        self.assertIs(provider.clip, clip)
        self.assertEqual(provider.config.base_url, "")
        with self.assertRaises(ValueError):
            adapter.provider_from_values("local", None, self.values(base_url="custom"))

    def test_the_node_refuses_a_source_the_panel_no_longer_offers(self):
        adapter = module("ng.adapters.ai_provider")
        with self.assertRaises(ValueError):
            adapter.provider_from_values("custom", None, self.values())

    def test_the_edges_of_every_sampling_range_are_accepted(self):
        for key, (low, high) in core.SAMPLING_RANGES.items():
            value = int(high) if key in core.SAMPLING_WHOLE else high
            for edge in (low, value):
                with self.subTest(key=key, edge=edge):
                    core.ProviderConfig.from_dict({"schema_version": 2, key: edge})

    def test_a_registry_default_and_a_config_default_agree(self):
        """The panel shows the registry's number; the config must not quietly use another."""
        for name, value in core.providers.DEFAULT_SETTINGS.items():
            with self.subTest(name=name):
                if name in core.SAMPLING_RANGES:
                    self.assertEqual(getattr(core.ProviderConfig.from_dict({"schema_version": 2}), name), value)

    def test_every_sampling_field_reaches_the_provider_it_belongs_to(self):
        """The point of carrying these: a chosen value survives into the request, not just the file."""
        config = core.ProviderConfig.from_dict({"schema_version": 2, "provider": "ollama",
                                                "temperature": 0.75, "top_k": 12,
                                                "seed": 5, "fixed_seed": True})
        payload = core.providers.provider_payload(config.provider, config.to_dict())
        self.assertEqual(payload["options"]["temperature"], 0.75)
        self.assertEqual(payload["options"]["top_k"], 12)
        self.assertEqual(payload["options"]["seed"], 5)

    def test_json_fences_and_bad_suggestions(self):
        answer = '{"description":"A woman in a red coat.","content":"character"}'
        self.assertEqual(core.parse_suggestion("```json\n" + answer + "\n```"), core.parse_suggestion(answer))
        # "not json" used to be refused by the bare decoder; it is now refused with a message that
        # names the likelier cause, so the wording is what changed, not what is refused.
        for text in (None, [], "not json", "[]", '{"description":""}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                core.parse_suggestion(text, "image")
        # An unknown role is left out and named; a description on its own is a complete, usable answer.
        self.assertIsNone(core.parse_suggestion('{"description":"x","content":"made_up"}').content)
        self.assertIsNone(core.parse_suggestion('{"description":"x"}').content)

    def test_prompts_disclose_sampling_limits(self):
        self.assertIn("ordered stills", core.analysis_prompt("video", "motion"))
        self.assertIn("15 seconds", core.analysis_prompt("audio", "voice"))
        self.assertIn("context text", core.analysis_prompt("text", "rules"))

    def test_a_suggestion_carries_its_reason_and_round_trips(self):
        # The panel shows why, so a provider that returns nothing for it must still produce a usable suggestion.
        answer = '{"description":"A woman in a red coat.","content":"character","why":"she fills the frame."}'
        parsed = core.parse_suggestion(answer)
        self.assertEqual(parsed.why, "she fills the frame.")
        self.assertEqual(core.AnalysisSuggestion.from_dict(parsed.to_dict()), parsed)
        bare = core.parse_suggestion('{"description":"A woman.","content":"character"}')
        self.assertEqual(bare.why, "", "a missing reason is allowed, a wrong one is not")
        for text in ('{"description":"x","content":"character","why":5}',
                     '{"description":"x","content":"character","usage":7}',
                     json.dumps({"description": "x" * 601, "content": "character", "why": "y" * 601})):
            with self.subTest(text=text[:40]), self.assertRaises(ValueError):
                core.parse_suggestion(text)
        # A model may answer with extra keys; that is not saved data, so it is ignored rather than refused.
        extra = core.parse_suggestion('{"description":"x","content":"character","schema_version":9,"tone":"warm"}')
        self.assertEqual(extra.description, "x")

    def test_only_filled_fields_are_offered(self):
        partial = core.parse_suggestion('{"description":"A woman.","content":"character"}')
        self.assertEqual(partial.offered(), {"description": "A woman.", "content": "character"})
        self.assertEqual(core.parse_suggestion('{"description":"A woman.","content":"character"}').offered().get("usage", None), None)
        empty = core.AnalysisSuggestion(description="A woman.")
        self.assertEqual(empty.offered(), {"description": "A woman."})


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class ProviderTransport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import web
        from PIL import Image
        stub_prompt_server()
        self.adapter = module("ng.adapters.analysis")
        self.preview = module("ng.adapters.preview_media")
        self.directory = tempfile.TemporaryDirectory()
        self.path_patch = patch("folder_paths.get_input_directory", return_value=self.directory.name)
        self.path_patch.start()
        Image.new("RGB", (32, 32), "red").save(os.path.join(self.directory.name, "image.png"))
        with wave.open(os.path.join(self.directory.name, "sound.wav"), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
            stream.writeframes(b"\x10\x00" * 16000 * 20)
        self.status, self.answer, self.requests, self.media = 200, self.reply("image", "red object"), [], "image"

        async def respond(request):
            self.requests.append((request.path, request.headers.get("Authorization"), await request.json()))
            if self.status != 200:
                return web.Response(status=self.status, text="request rejected")
            if request.path == "/api/generate":
                return web.json_response({"response": self.answer})
            return web.json_response({"choices": [{"message": {"content": self.answer}}]})

        async def by_media(request):
            """Answer in the role this medium allows, like a real model asked our prompt. The path
            names the medium, so one emulator covers image, video, audio and text."""
            self.requests.append((request.path, request.headers.get("Authorization"), await request.json()))
            media = request.match_info.get("media", "image")
            return web.json_response({"choices": [{"message": {"content": self.reply(media, "red object")}}]})

        app = web.Application()
        app.router.add_post("/v1/chat/completions", respond)
        app.router.add_post("/{media}/v1/chat/completions", by_media)
        app.router.add_post("/api/generate", respond)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = "http://127.0.0.1:%d" % site._server.sockets[0].getsockname()[1]
        self.key_patch = patch.object(self.adapter.legacy, "resolve_api_key", return_value="test-key")
        self.key_patch.start()

    async def asyncTearDown(self):
        await self.runner.cleanup()
        self.key_patch.stop(); self.path_patch.stop(); self.directory.cleanup()

    def reply(self, media, description):
        """A well-formed answer for this medium. The emulator used to answer one fixed role whatever
        it was asked about, which is exactly the mistake the parse now refuses."""
        role = core.CONTENT_BY_MEDIA[media][0]
        return json.dumps({"description": description, "content": role})

    def answering(self, media):
        """Point a payload at the endpoint that answers in the role `media` allows, so a card of
        this medium gets a valid answer instead of the one fixed role the emulator used to send."""
        data = self.payload(media, audio=(media == "audio"))
        data["provider"]["base_url"] = self.url + "/" + media
        data["provider"]["model"] = "mock"
        return data

    def payload(self, media="image", **provider):
        config = core.ProviderConfig(**{"provider": "custom", "base_url": self.url + "/v1", "model": "mock", **provider})
        return {"media": media, "widgets": {"image": "image.png", "audio": "sound.wav", "text": "Keep a slow camera.", "content": "style"},
                "provider": config.to_dict()}

    async def test_the_sampling_settings_reach_the_request_body(self):
        # BUG-041: Temperature, Top P/K, Min P and a fixed Seed were computed and dropped; Ollama got only num_predict.
        knobs = dict(temperature=1.9, top_p=0.5, top_k=100, min_p=0.5, seed=12345, fixed_seed=True)
        await self.adapter.analyze(self.payload("text", **knobs))
        body = self.requests[-1][2]
        self.assertEqual((body["temperature"], body["top_p"], body["seed"]), (1.9, 0.5, 12345), "OpenAI-compatible: flat in the body")
        ollama = self.payload("text", provider="ollama", base_url=self.url, model="m", **knobs)
        await self.adapter.analyze(ollama)
        path, _, body = self.requests[-1]
        self.assertEqual(path, "/api/generate")
        self.assertEqual({key: body["options"][key] for key in ("temperature", "top_k", "min_p", "seed")},
                         {"temperature": 1.9, "top_k": 100, "min_p": 0.5, "seed": 12345}, "Ollama: under options")
        self.assertEqual(body["options"]["num_predict"], 512)
        self.answer = json.dumps({"shots": [{"start_s": 0, "end_s": 8, "action": "Alice walks."}]})
        await module("ng.adapters.auto_direct").direct({"provider": ollama["provider"], "contexts": [],
                                                          "director": {"idea": "Alice walks.", "project_seconds": 8}})
        options = self.requests[-1][2]["options"]
        self.assertEqual((options["temperature"], options["num_predict"]), (1.9, 2048), "the split's own token floor still wins")
        await self.adapter.analyze(self.payload("text", **(knobs | {"fixed_seed": False})))
        self.assertNotIn("seed", self.requests[-1][2], "an unticked Fixed seed stays out")

    async def test_split_and_build_reach_a_cloud_provider_like_analyze(self):
        # BUG-033/034: both indexed the local-only _PROVIDER_DEFAULTS and failed with KeyError: 'openrouter'.
        provider = self.payload(provider="openrouter")["provider"]
        self.answer = json.dumps({"shots": [{"start_s": 0, "end_s": 8, "action": "Alice walks.", "camera": "", "dialogue": ""}],
                                  "soundscape": "", "music": ""})
        result = await module("ng.adapters.auto_direct").direct({"provider": provider, "contexts": [],
                                                                 "director": {"idea": "Alice walks.", "project_seconds": 8}})
        self.assertIn("Alice walks.", result["shots"])
        self.answer = "description: [Shot 1] A woman walks through a station."
        written = await module("ng.adapters.part_writer").write({"provider": provider, "contexts": [], "part": 0,
                                                                 "director": {"idea": "Alice walks.", "project_seconds": 8}})
        self.assertTrue(written["problems"], "a 9-word description is refused, but it did reach the provider")
        self.assertEqual([(path, auth, body["model"]) for path, auth, body in self.requests],
                         [("/v1/chat/completions", "Bearer test-key", "mock")] * 2)

    async def test_vision_reuses_auth_and_normalizes_v1(self):
        result = await self.adapter.analyze(self.payload(max_tokens=1024, timeout_seconds=45))
        self.assertEqual(result["description"], "red object")
        path, auth, body = self.requests[0]
        self.assertEqual((path, auth), ("/v1/chat/completions", "Bearer test-key"))
        # The system message comes first and the user's picture is the second one. Looking this up by
        # index is what broke when the role prompt arrived: the test read the system message's plain
        # string content as if it were the user's content array. Finding the user turn by role is
        # what keeps it correct however many messages precede it.
        user = [m for m in body["messages"] if m["role"] == "user"]
        self.assertEqual(len(user), 1, "exactly one user turn carries the picture")
        self.assertEqual(user[0]["content"][1]["type"], "image_url")
        self.assertEqual(body["max_tokens"], 1024)
        self.assertNotIn("test-key", json.dumps(body))
        # The role and the schema framing both travel, and the framing is the last thing said: the
        # parser depends on it, and a role prompt sent without it produced unreadable answers.
        system = [m for m in body["messages"] if m["role"] == "system"]
        self.assertEqual(len(system), 1)
        self.assertTrue(system[0]["content"].endswith("code fence."))

    async def test_every_role_carries_its_own_prompt(self):
        """One prompt per medium, never the loader's. A card that analyses a picture must not be
        told it is reading a note - the two ask for different things and the answers do not match."""
        seen = {}
        # Image, audio and text only: those are the three the transport fixture actually holds files
        # for. Video shares the vision role with image by design, and asking for a clip the fixture
        # does not have would fail on a missing file long before the prompt could be compared.
        for media in ("image", "audio", "text"):
            await self.adapter.analyze(self.answering(media))
            body = self.requests[-1][2]
            system = [m for m in body["messages"] if m["role"] == "system"]
            self.assertEqual(len(system), 1, "%s sent no role prompt" % media)
            seen[media] = system[0]["content"]
        self.assertEqual(len(set(seen.values())), len(seen),
                         "each medium needs its own role text, got %d distinct texts for %d media"
                         % (len(set(seen.values())), len(seen)))
        # Every one of them still ends in the framing, or the parser is not being told the format.
        for media, text in seen.items():
            self.assertTrue(text.endswith("code fence."), "%s lost the schema framing" % media)

    async def test_ollama_and_text_without_vision(self):
        data = self.payload("text", vision=False, keep_alive=60)
        data["provider"]["provider"] = "ollama"
        data["provider"]["base_url"] = self.url
        await self.adapter.analyze(data)
        body = self.requests[0][2]
        self.assertEqual((body["images"], body["keep_alive"]), ([], 60))
        self.assertIn("Keep a slow camera", body["prompt"])

    async def test_audio_is_bounded_and_uses_wav_content(self):
        await self.adapter.analyze(self.answering("audio"))
        body = self.requests[0][2]
        # By role, not by index: the system message now precedes the audio and index 0 is its plain
        # string. The test that read messages[0] was reading the role prompt, not the sound.
        user = [m for m in body["messages"] if m["role"] == "user"]
        audio = user[0]["content"][1]
        self.assertEqual(audio["type"], "input_audio")
        with wave.open(io.BytesIO(base64.b64decode(audio["input_audio"]["data"])), "rb") as stream:
            self.assertEqual((stream.getframerate(), stream.getnframes()), (16000, 15 * 16000))

    async def test_capabilities_stop_before_network(self):
        for payload in (self.payload(vision=False), self.payload("audio")):
            with self.assertRaisesRegex(ValueError, "is off on the H3 AI Loader"):
                await self.adapter.analyze(payload)
        self.assertEqual(self.requests, [])

    async def test_missing_address_and_model_stop_before_network(self):
        # A remote endpoint has no default and no model list, so both are named as a missing
        # setting rather than surfacing as a connection error against an empty address.
        with self.assertRaisesRegex(ValueError, "not a usable address"):
            await self.adapter.analyze(self.payload(base_url=""))
        with self.assertRaisesRegex(ValueError, "No model name set"):
            await self.adapter.analyze(self.payload(model=""))
        self.assertEqual(self.requests, [], "an unconfigured provider must not reach the network")

    async def test_http_failures_and_malformed_answer(self):
        for status in (401, 403, 500):
            self.status = status
            with self.assertRaises(ValueError):
                await self.adapter.analyze(self.payload())
        self.status, self.answer = 200, "this is not JSON"
        with self.assertRaises(ValueError):
            await self.adapter.analyze(self.payload())

    async def test_media_previews_and_missing_files(self):
        image = self.preview.preview("image", "image.png")
        self.assertTrue(image["thumbnail"].startswith("data:image/jpeg;base64,"))
        audio = self.preview.preview("audio", "sound.wav")
        self.assertEqual((len(audio["peaks"]), audio["sampled_seconds"]), (80, 15.0))
        with self.assertRaisesRegex(ValueError, "missing"):
            self.preview.preview("image", "missing.png")

    async def test_full_waveform_has_duration_metadata_and_streamed_peaks(self):
        waveform = module("ng.adapters.waveform")
        data = waveform.envelope("sound.wav")
        self.assertEqual(data["duration_s"], 20.0)
        self.assertEqual((data["sample_rate"], data["channels"], len(data["peaks"])), (16000, 1, 320))
        self.assertGreater(data["peaks"][-1], 0)

    async def test_analyze_all_covers_usable_cards_and_names_the_rest(self):
        adapter = module("ng.adapters.analyze_all")
        base = self.payload(audio=True)
        # The endpoint answers in the role each medium allows, so an image card and an audio card can
        # both succeed - which they could not while one fixed role was sent for every medium.
        provider = self.answering("image")["provider"]
        provider["audio"] = True  # one provider serves both cards here, so it must accept audio
        # Both cards share one provider, so the emulator answers every request with the image role.
        # The audio card is therefore checked separately below, against an audio answer.
        payload = {"provider": provider, "mode": "assist", "contexts": [
            {"media": "image", "widgets": base["widgets"]},
            {"media": "audio", "widgets": base["widgets"]},
            {"media": "text", "widgets": {"text": "  ", "name": "Empty"}},
            {"media": "image", "widgets": {"image": "", "name": "Blank"}}]}
        result = await adapter.analyze_all(payload)
        self.assertEqual([entry["index"] for entry in result["results"]], [0, 1])
        self.assertTrue(result["results"][0]["ok"], result["results"][0])
        self.assertEqual(result["results"][0]["suggestion"]["description"], "red object")
        # The image card got a role an image can hold.
        self.assertIn(result["results"][0]["suggestion"]["content"], core.CONTENT_BY_MEDIA["image"])
        # The audio card names the role it cannot have and leaves it out instead of writing it down.
        self.assertIsNone(result["results"][1]["suggestion"]["content"])
        self.assertIn("does not fit this audio card", result["results"][1]["suggestion"]["why"])
        # Asked on its own, with a provider that answers for audio, the same card succeeds.
        alone = await adapter.analyze(self.answering("audio"))
        self.assertIn(alone["content"], core.CONTENT_BY_MEDIA["audio"])
        # Only the two usable cards of the batch reached the provider; the third request is ours.
        self.assertEqual(len(self.requests) - 1, 2, "only the usable cards reach the provider")
        # Two cards were skipped outright, plus one note that the batch shared a single failure. That note
        # is new and wanted: a provider answering in the wrong role fails every card the same way.
        self.assertGreaterEqual(len(result["skipped"]), 2)
        self.assertTrue(any("text is empty" in reason for reason in result["skipped"]))
        self.assertTrue(any("no file chosen" in reason for reason in result["skipped"]))

    async def test_an_undeclared_capability_is_a_result_not_a_crash(self):
        # The same card works with audio enabled and reports the reason here; the batch keeps its other results.
        adapter = module("ng.adapters.analyze_all")
        base = self.payload()
        payload = {"provider": base["provider"], "mode": "assist", "contexts": [
            {"media": "audio", "widgets": base["widgets"]},
            {"media": "image", "widgets": base["widgets"]}]}
        result = await adapter.analyze_all(payload)
        self.assertEqual([entry["ok"] for entry in result["results"]], [False, True])
        self.assertIn("Audio is off on the H3 AI Loader", result["results"][0]["error"])
        self.assertEqual(result["results"][1]["suggestion"]["description"], "red object")

    async def test_analyze_all_keeps_going_after_one_card_fails_and_says_so(self):
        adapter = module("ng.adapters.analyze_all")
        base = self.payload()
        payload = {"provider": base["provider"], "mode": "assist", "contexts": [
            {"media": "image", "widgets": base["widgets"]},
            {"media": "image", "widgets": {**base["widgets"], "content": "still fine"}}]}
        self.status = 500
        result = await adapter.analyze_all(payload)
        self.assertEqual([entry["ok"] for entry in result["results"]], [False, False])
        self.assertIn("same error", result["skipped"][-1].lower())

    async def test_analyze_all_respects_manual_mode_without_any_request(self):
        adapter = module("ng.adapters.analyze_all")
        base = self.payload()
        payload = {"provider": base["provider"], "mode": "manual",
                   "contexts": [{"media": "image", "widgets": base["widgets"]}]}
        result = await adapter.analyze_all(payload)
        self.assertEqual(result["results"], [])
        self.assertEqual(self.requests, [], "Manual must not contact the provider")

    async def test_auto_direct_uses_existing_transport_and_returns_a_proposal(self):
        adapter = module("ng.adapters.auto_direct")
        self.answer = json.dumps({"shots": [{"start_s": 0, "end_s": 8, "action": "Alice walks.", "camera": "Static", "dialogue": ""}],
                                 "soundscape": "wind", "music": "N/A"})
        payload = {"provider": self.payload("text", max_tokens=1024)["provider"], "director": {"idea": "Alice walks.", "project_seconds": 8}, "contexts": []}
        result = await adapter.direct(payload)
        self.assertEqual([(s["start"], s["end"], s["text"]) for s in json.loads(result["shots"])["shots"]], [(0, 8, "Alice walks. Static.")])
        self.assertEqual(self.requests[0][1], "Bearer test-key")
        # A shot list cut off at the loader's Max tokens is useless JSON: Auto Direct asks for at least 2048.
        self.assertEqual(self.requests[0][2]["max_tokens"], 2048)
        self.assertEqual(payload["director"], {"idea": "Alice walks.", "project_seconds": 8})
        payload["provider"]["max_tokens"] = 4096
        await adapter.direct(payload)
        self.assertEqual(self.requests[-1][2]["max_tokens"], 4096, "a larger setting is kept")
        self.answer = "malformed"
        with self.assertRaises(ValueError):
            await adapter.direct(payload)
