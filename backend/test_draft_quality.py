"""Deterministic regression tests: no model downloads or network calls."""
import asyncio
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Import the actual generator with isolated dependencies, not the live database.
http = types.ModuleType('httpx')
http.Timeout = lambda *args, **kwargs: None
http.AsyncClient = None
retrieval = types.ModuleType('retrieval')
async def no_search(**kwargs):
    return []
retrieval.search_knowledge = no_search
observability = types.ModuleType('observability')
observability.observed = lambda name: lambda fn: fn
settings = types.ModuleType('settings')
settings.OLLAMA_BASE_URL = 'http://test.invalid'
spec = importlib.util.spec_from_file_location(
    '_quality_generator_under_test', Path(__file__).with_name('ai_service.py'))
ai = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'httpx': http, 'retrieval': retrieval,
                              'observability': observability, 'settings': settings}):
    spec.loader.exec_module(ai)

SECOND = ('Second recovery email never arrived',
          'I checked spam and requested another password reset email. '
          'Another ten minutes have passed without receiving it.')
GOOD = ('Based on what you reported, a human support agent needs to review '
        'this request with the account access team [KB-001].')
BAD = ('You should request one new password reset email. If this third email '
       'does not arrive after 10 more minutes, contact support [KB-001].')

class FakeResponse:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data

class FakeClient:
    def __init__(self, outputs): self.outputs = iter(outputs); self.calls = []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def post(self, url, json):
        self.calls.append(copy.deepcopy(json))
        output = next(self.outputs)
        if isinstance(output, Exception): raise output
        if isinstance(output, str): output = {'message': {'content': output}}
        return FakeResponse(output)

class QualityChecks(unittest.TestCase):
    def test_third_email_variants(self):
        for wording in ('third email', 'third reset email', 'third password reset email',
                        '3rd recovery email', 'third request'):
            with self.subTest(wording=wording):
                issues = ai.check_draft('Request a ' + wording + ' [KB-001].', {'KB-001'})
                self.assertTrue(any('third-reset' in x for x in issues))

    def test_repeated_reset_without_word_third(self):
        issues = ai.check_draft('Please request one new password reset email [KB-001].',
                                {'KB-001'}, '\n'.join(SECOND))
        self.assertTrue(any('reported second attempt' in x for x in issues))

    def test_first_attempt_advice_remains_allowed(self):
        self.assertEqual(ai.check_draft(
            'After 10 minutes, request one new reset email [KB-001].', {'KB-001'},
            'My first reset email has not arrived after fifteen minutes.'), [])

    def test_valid_escalation(self):
        self.assertEqual(ai.check_draft(GOOD, {'KB-001'}, '\n'.join(SECOND)), [])

    def test_missing_citation(self):
        self.assertTrue(any('No article citation' in w for w in
                            ai.check_draft('A human agent needs to review this.', {'KB-001'})))

    def test_bare_reference_requires_brackets(self):
        self.assertTrue(any('bracketed' in w for w in
                            ai.check_draft('See KB-001 for support guidance.', {'KB-001'})))

    def test_unknown_citation(self):
        self.assertTrue(any('not supplied' in w for w in
                            ai.check_draft('Contact billing [KB-999].', {'KB-003'})))

    def test_action_claim(self):
        for draft in ('I will issue a refund. [KB-003]',
                      'Your refund has been approved [KB-003].'):
            with self.subTest(draft=draft):
                self.assertTrue(ai.check_draft(draft, {'KB-003'}))

class GenerationFlow(unittest.IsolatedAsyncioTestCase):
    async def run_generator(self, outputs, sources=True):
        async def search(**kwargs):
            return ([{'source': 'password_reset.md', 'content':
                      'Article ID: KB-001\nSupport queue: account_access\n'
                      'After the second email fails after 10 minutes, a human '
                      'support agent should route the ticket to account access.',
                      'score': 0.8}] if sources else [])
        client = FakeClient(outputs)
        with patch.object(ai, 'search_knowledge', search), \
             patch.object(ai.httpx, 'AsyncClient', return_value=client):
            result = await ai.draft_ticket_response(*SECOND)
        return result, client

    async def test_valid_first_response(self):
        result, client = await self.run_generator([GOOD])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result['draft_strategy'], 'generated')
        self.assertTrue(result['requires_review'])
        self.assertFalse(result['grounding_verified'])

    async def test_missing_citation_corrected(self):
        result, client = await self.run_generator(['Human review is needed.', GOOD])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result['draft'], GOOD)
        self.assertEqual(result['draft_strategy'], 'revised')
        self.assertTrue(result['review_warnings'])
        self.assertEqual(client.calls[0]['messages'][:2], client.calls[1]['messages'][:2])

    async def test_third_attempt_corrected(self):
        result, client = await self.run_generator([BAD, GOOD])
        self.assertEqual(result['draft_strategy'], 'revised')
        self.assertNotIn('third email', result['draft'])
        self.assertEqual(len(client.calls), 2)

    async def test_two_failures_fall_back(self):
        result, client = await self.run_generator([BAD, BAD])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result['draft_strategy'], 'fallback')
        self.assertTrue(result['review_warnings'][0].startswith('FALLBACK:'))
        self.assertNotIn('request one new', result['draft'])
        self.assertTrue(result['requires_review'])
        self.assertFalse(result['grounding_verified'])

    async def test_missing_citations_not_appended_to_generated_text(self):
        result, _ = await self.run_generator(['Unverified answer.', 'Unverified answer.'])
        self.assertEqual(result['draft_strategy'], 'fallback')
        self.assertNotIn('Unverified answer.', result['draft'])

    async def test_empty_sources_skip_model(self):
        result, client = await self.run_generator([], sources=False)
        self.assertEqual(client.calls, [])
        self.assertEqual(result['generation_attempts'], 0)
        self.assertFalse(result['context_used'])

    async def test_network_failure_remains_error(self):
        with self.assertRaises(ConnectionError):
            await self.run_generator([ConnectionError('offline')])

    async def test_correction_failure_remains_error(self):
        with self.assertRaises(ConnectionError):
            await self.run_generator([BAD, ConnectionError('offline')])

    async def test_truncation_remains_error(self):
        with self.assertRaises(ValueError):
            await self.run_generator([{'done_reason': 'length', 'message': {'content': GOOD}}])

    async def test_empty_output_remains_error(self):
        with self.assertRaises(ValueError):
            await self.run_generator([''])

if __name__ == '__main__':
    unittest.main()
