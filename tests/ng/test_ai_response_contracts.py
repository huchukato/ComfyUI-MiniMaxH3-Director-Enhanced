"""AI parser and batch contracts through product code and real local HTTP.

The local test provider serves deterministic replies. No real inference or external service is called.
Timeout controls use actual aiohttp deadlines; only the route's default 15-second deadline is shortened.
"""
import asyncio
from collections import deque
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

TESTS_NG = Path(__file__).resolve().parent
if (TESTS_NG / '_pack.py').is_file():
    sys.path.insert(0, str(TESTS_NG))
from _pack import COMFY_ROOT, module, stub_prompt_server

if COMFY_ROOT not in sys.path:
    sys.path.insert(0, COMFY_ROOT)
saved_argv = sys.argv
try:
    sys.argv = [sys.argv[0], '--cpu']
    stub_prompt_server()
    analysis = module('ng.core.analysis')
    part = module('ng.core.part_prompt')
    writer = module('ng.core.part_writer')
    models = module('ng.adapters.models')
    context_routes = module('ng.nodes.context_routes')
    analysis_routes = module('ng.nodes.analysis_routes')
finally:
    sys.argv = saved_argv

SUGGESTION = {'description': 'A stone gateway beside tall pines.', 'content': 'location',
              'usage': 'reference', 'why': 'The stonework establishes the place.'}
TEXT_SUGGESTION = {'description': 'A scene at a gateway.', 'usage': 'scene', 'why': 'It describes the action.'}
DESCRIPTION = ('[Shot 1] The camera gently pushes toward the old gateway, showing moss on its stone walls and pine branches '
               'swaying slowly above the empty path. Soft morning light passes through the branches and makes bright patches '
               'on the ground, while cool mist drifts across the stone steps. The composition stays quiet and balanced '
               'as the leaves move in the light breeze.')
FIELDS = 'description: ' + DESCRIPTION + '\noverall_soundscape: Wind moves through the pines.\nnon_diegetic_music: Slow strings.'


class AIParserBoundaries(unittest.TestCase):
    def test_analysis_json_with_surrounding_prose_is_one_valid_object(self):
        raw = json.dumps(SUGGESTION)
        for text in (raw, raw + '\nHope this helps!', 'Here is the analysis:\n```json\n' + raw + '\n```\nDone.'):
            with self.subTest(text=text):
                got = analysis.parse_suggestion(text, 'image')
                self.assertEqual(got.description, SUGGESTION['description'])
                self.assertEqual(got.usage, 'reference')

    def test_refusal_early_syntax_and_truncation_have_distinct_diagnostics(self):
        for text in ('', 'I cannot help with that.', '{not JSON', '{} {}'):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, 'not readable JSON') as caught:
                    analysis.parse_suggestion(text, 'image')
                self.assertNotIn('Max tokens', str(caught.exception))
        with self.assertRaisesRegex(ValueError, 'not readable JSON') as caught:
            analysis.parse_suggestion('{"description": "A woman', 'image')
        self.assertIn('Max tokens', str(caught.exception))

    def test_analysis_domain_stays_strict(self):
        for text in ('[]', '[{}]', '{"description": 123}', '{"description": ""}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    analysis.parse_suggestion(text, 'image')
        self.assertEqual(analysis.parse_suggestion('{"constraint": "Never show logos"}', 'text').usage, 'constraint')


class PartFenceBoundaries(unittest.TestCase):
    def setUp(self):
        # Real compiler output, rather than a synthetic prompt header.
        self.facts = writer.brief({'idea': 'The camera looks at an old stone gateway.', 'mode': 'fl2va',
                                   'project_seconds': 5, 'continuity': 'none'}, [], 0)

    def test_one_complete_fence_supplies_the_prompt_and_preserves_fallback_sound(self):
        for text in ('```markdown\n' + FIELDS + '\n```',
                     'Here is your prompt:\n```markdown\n' + FIELDS + '\n```\nHope this helps!',
                     'Introduction.\n  ```text\n' + FIELDS + '\n  ```\nNote: overall_soundscape: kept.'):
            with self.subTest(text=text):
                got = writer.finish(text, self.facts)
                self.assertEqual(got['problems'], [])
                self.assertNotIn('```', got['text'])
                self.assertNotIn('Hope this helps', got['text'])
                self.assertNotIn('Note:', got['text'])
                self.assertIn('non_diegetic_music: Slow strings.', got['text'])
        description_only = 'Here is the prompt:\n```\ndescription: ' + DESCRIPTION + '\n```\nNote: overall_soundscape: kept.'
        got = writer.finish(description_only, self.facts)
        self.assertEqual(got['problems'], [])
        self.assertNotIn('Note:', got['text'])
        self.assertIn('overall_soundscape:', got['text'])

    def test_malformed_and_ambiguous_fences_cannot_produce_a_prompt(self):
        for text in ('```markdown\n' + FIELDS,
                     '```markdown\n' + FIELDS + '\n```text',
                     '```\n' + FIELDS + '\n```\n```\n' + FIELDS + '\n```',
                     FIELDS + '\n```'):
            with self.subTest(text=text):
                got = writer.finish(text, self.facts)
                self.assertEqual(got['text'], '')
                self.assertTrue(got['problems'])

    def test_clean_prompt_and_real_structure_errors_remain_checked(self):
        self.assertEqual(writer.finish(FIELDS, self.facts)['problems'], [])
        for text in (FIELDS.replace('[Shot 1]', '[Shot 2]'), FIELDS.replace('The camera', '<Subject 99>'),
                     'description: [Shot 1] Short.', FIELDS.replace('Soft morning', 'summary: invented. Soft morning')):
            with self.subTest(text=text):
                got = writer.finish(text, self.facts)
                self.assertEqual(got['text'], '')
                self.assertTrue(got['problems'])


class RealLocalHTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.replies = deque()
        self.requests = []
        self.model_delay = 0
        async def generate(request):
            data = await request.json()
            self.requests.append(data)
            return web.json_response({'response': self.replies.popleft()})
        async def tags(request):
            await asyncio.sleep(self.model_delay)
            return web.json_response({'models': [{'name': 'contract-test'}]})
        provider_app = web.Application()
        provider_app.router.add_post('/api/generate', generate)
        provider_app.router.add_get('/api/tags', tags)
        self.provider = TestServer(provider_app)
        await self.provider.start_server()
        self.config = {'schema_version': 2, 'provider': 'ollama', 'base_url': str(self.provider.make_url('/')).rstrip('/'),
                       'model': 'contract-test', 'max_tokens': 512, 'timeout_seconds': 5}
        owner = Path(__file__).resolve().parent
        self.tmp = tempfile.TemporaryDirectory(dir=owner)
        manager = types.SimpleNamespace(get_request_user_filepath=lambda _request, _path: self.tmp.name)
        self.manager_patch = patch.object(context_routes.PromptServer.instance, 'user_manager', manager, create=True)
        self.manager_patch.start()
        app = web.Application()
        app.router.add_post('/ng/analyze', analysis_routes.analyze_context)
        app.router.add_post('/ng/analyze_all', analysis_routes.analyze_every_context)
        app.router.add_post('/ng/write_part', analysis_routes.write_part_prompt)
        app.router.add_post('/ng/models', context_routes.list_models)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.provider.close()
        self.manager_patch.stop()
        self.tmp.cleanup()

    async def post(self, path, payload):
        response = await self.client.post(path, json=payload)
        body_text = await response.text()
        self.assertLess(response.status, 500, body_text)
        return response.status, json.loads(body_text)

    def card(self, name, text='The camera looks at a gateway.'):
        return {'media': 'text', 'widgets': {'name': name, 'text': text, 'context_id': 'text_' + name}}

    async def test_analyze_route_reads_complete_json_with_prose_from_real_transport(self):
        raw = json.dumps(TEXT_SUGGESTION)
        for answer in (raw + '\nHope this helps!', 'Here is your analysis:\n```json\n' + raw + '\n```\nDone.'):
            self.replies.append(answer)
            status, body = await self.post('/ng/analyze', {'provider': self.config, **self.card('Scene')})
            self.assertEqual(status, 200)
            self.assertTrue(body['ok'])
            self.assertEqual(body['suggestion']['usage'], 'scene')
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[0]['options']['num_predict'], 512)
        self.assertIn('Context text:', self.requests[0]['prompt'])

    async def test_skips_are_formatted_once_without_calling_the_provider(self):
        cards = [self.card('Act: One', ''), {'media': 'image', 'widgets': {'name': 'Place', 'image': ''}},
                 {'media': 'audio', 'widgets': {'name': 'Voice', 'audio': 'voice.wav', 'analyzed': True}}]
        status, body = await self.post('/ng/analyze_all', {'provider': self.config, 'mode': 'assist', 'contexts': cards})
        self.assertEqual(status, 200)
        self.assertTrue(body['ok'])
        self.assertEqual(body['results'], [])
        self.assertEqual(body['skipped'], ['Act: One: the text is empty', 'Place: no file chosen', 'Voice: already analyzed'])
        self.assertEqual(self.requests, [])

    async def test_partial_batch_retains_success_and_reports_only_failed_card(self):
        self.replies.extend([json.dumps(TEXT_SUGGESTION), 'I cannot analyze this context.'])
        status, body = await self.post('/ng/analyze_all', {'provider': self.config, 'mode': 'assist',
                                                        'contexts': [self.card('First'), self.card('Second')]})
        self.assertEqual(status, 200)
        self.assertTrue(body['ok'])
        self.assertEqual([entry['ok'] for entry in body['results']], [True, False])
        self.assertEqual(body['results'][0]['suggestion']['usage'], 'scene')
        self.assertIn('error', body['results'][1])
        self.assertEqual(body['skipped'], [])
        self.assertEqual(len(self.requests), 2)

    async def test_uniform_batch_failure_and_full_success_preserve_contract(self):
        payload = {'provider': self.config, 'mode': 'assist', 'contexts': [self.card('First'), self.card('Second')]}
        self.replies.extend(['Refused.', 'Refused.'])
        _, body = await self.post('/ng/analyze_all', payload)
        self.assertEqual([entry['ok'] for entry in body['results']], [False, False])
        self.assertEqual(len(body['skipped']), 1)
        self.assertIn('same error occurred for every card', body['skipped'][0])
        self.replies.extend([json.dumps(TEXT_SUGGESTION), json.dumps(TEXT_SUGGESTION)])
        _, body = await self.post('/ng/analyze_all', payload)
        self.assertEqual([entry['ok'] for entry in body['results']], [True, True])
        self.assertEqual(body['skipped'], [])

    async def test_part_route_extracts_fenced_fields_after_real_transport_and_compilation(self):
        self.replies.append('Here is your prompt:\n```markdown\n' + FIELDS + '\n```\nHope this helps!')
        _, body = await self.post('/ng/write_part', {'provider': self.config, 'contexts': [], 'part': 0,
            'director': {'idea': 'The camera looks at an old stone gateway.', 'mode': 'fl2va',
                         'project_seconds': 5, 'continuity': 'none'}})
        self.assertTrue(body['ok'])
        self.assertEqual(body['suggestion']['problems'], [])
        self.assertNotIn('```', body['suggestion']['text'])
        self.assertNotIn('Hope this helps', body['suggestion']['text'])

    async def test_actual_aiohttp_timeout_is_an_empty_list_with_reason(self):
        self.model_delay = .2
        names, reason = await models.listing('ollama', self.config['base_url'], timeout=.025)
        self.assertEqual(names, [])
        self.assertIn('timed out', reason)
        self.model_delay = 0
        names, reason = await models.listing('ollama', self.config['base_url'], timeout=1)
        self.assertEqual(names, ['contract-test'])
        self.assertEqual(reason, '')

    async def test_model_route_serializes_real_timeout_as_json(self):
        self.model_delay = .2
        original = models.listing
        async def fast_listing(provider, base_url, api_key=None):
            return await original(provider, base_url, api_key, timeout=.025)
        with patch.object(models, 'listing', fast_listing):
            status, body = await self.post('/ng/models', {'provider': 'ollama', 'base_url': self.config['base_url']})
        self.assertEqual(status, 200)
        self.assertFalse(body['ok'])
        self.assertEqual(body['models'], [])
        self.assertIn('timed out', body['reason'])
        self.assertEqual(body['source'], 'live')


if __name__ == '__main__':
    unittest.main()
