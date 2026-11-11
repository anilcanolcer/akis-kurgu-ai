import io
import json
import unittest
from urllib.error import HTTPError, URLError

from akis import ai_providers
from akis.ai_providers import (PROVIDERS, post_json, request_plan, ResponseBlockedError, ResponseTruncatedError,
                               EmptyResponseError, ProviderResponseError)
from akis.ai_service import parse_suggestions

KEY = 'sk-proj-SuperSecretValue1234567890'


def plan(provider, response, frames=((0, b'jpeg'),), seen=None, **kwargs):
    def transport(url, headers, body):
        if seen is not None:
            seen.update(url=url, headers=headers, body=body)
        return response
    return request_plan(provider, KEY, PROVIDERS[provider][0], 'prompt', list(frames), transport, **kwargs)


class ResponseShapeTests(unittest.TestCase):
    def test_gemini_safety_block_without_content(self):
        with self.assertRaisesRegex(ResponseBlockedError, 'engelledi.*SAFETY'):
            plan('Gemini', {'candidates': [{'finishReason': 'SAFETY', 'safetyRatings': []}]})

    def test_gemini_prompt_feedback_block(self):
        with self.assertRaisesRegex(ResponseBlockedError, 'PROHIBITED_CONTENT'):
            plan('Gemini', {'promptFeedback': {'blockReason': 'PROHIBITED_CONTENT'}})

    def test_gemini_max_tokens_and_empty(self):
        with self.assertRaises(ResponseTruncatedError) as ctx:
            plan('Gemini', {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{"a":'}]}}]})
        self.assertEqual(ctx.exception.partial, '{"a":')
        with self.assertRaisesRegex(EmptyResponseError, 'boş yanıt'):
            plan('Gemini', {'candidates': []})
        with self.assertRaisesRegex(EmptyResponseError, 'boş yanıt'):
            plan('Gemini', {'candidates': [{'finishReason': 'STOP', 'content': {}}]})

    def test_gemini_uses_system_instruction_and_skips_thoughts(self):
        seen = {}
        text = plan('Gemini', {'candidates': [{'content': {'parts': [{'text': 'düşünce', 'thought': True}, {'text': 'ok'}]}}]},
                    seen=seen, instruction='SİSTEM')
        self.assertEqual(text, 'ok')
        self.assertEqual(seen['body']['systemInstruction'], {'parts': [{'text': 'SİSTEM'}]})
        self.assertEqual(seen['body']['contents'][0]['parts'][0], {'text': 'prompt'})

    def test_xai_refusal_and_null_content(self):
        with self.assertRaisesRegex(ResponseBlockedError, 'reddetti'):
            plan('xAI', {'choices': [{'message': {'content': None, 'refusal': 'Yapamam'}, 'finish_reason': 'stop'}]})
        with self.assertRaises(ResponseBlockedError):
            plan('xAI', {'choices': [{'message': {'content': None}, 'finish_reason': 'content_filter'}]})
        with self.assertRaises(EmptyResponseError):
            plan('xAI', {'choices': [{'message': {'content': None}, 'finish_reason': 'stop'}]})
        with self.assertRaises(EmptyResponseError):
            plan('xAI', {'choices': []})
        with self.assertRaises(ResponseTruncatedError):
            plan('xAI', {'choices': [{'message': {'content': '{"x":'}, 'finish_reason': 'length'}]})

    def test_anthropic_max_tokens_and_refusal(self):
        with self.assertRaises(ResponseTruncatedError) as ctx:
            plan('Anthropic', {'content': [{'type': 'text', 'text': '{"segments":['}], 'stop_reason': 'max_tokens'})
        self.assertIn('yarıda kesildi', str(ctx.exception))
        self.assertIsInstance(ctx.exception, RuntimeError)
        with self.assertRaises(ResponseBlockedError):
            plan('Anthropic', {'content': [], 'stop_reason': 'refusal'})
        with self.assertRaises(EmptyResponseError):
            plan('Anthropic', {'content': [], 'stop_reason': 'end_turn'})
        seen = {}
        plan('Anthropic', {'content': [{'type': 'text', 'text': 'ok'}], 'stop_reason': 'end_turn'}, seen=seen)
        self.assertGreater(seen['body']['max_tokens'], 8192)

    def test_openai_incomplete_refusal_failed(self):
        with self.assertRaises(ResponseTruncatedError):
            plan('OpenAI', {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
                            'output': [{'content': [{'type': 'output_text', 'text': '{"a"'}]}]})
        with self.assertRaises(ResponseBlockedError):
            plan('OpenAI', {'status': 'incomplete', 'incomplete_details': {'reason': 'content_filter'}, 'output': []})
        with self.assertRaisesRegex(ResponseBlockedError, 'Bunu yapamam'):
            plan('OpenAI', {'status': 'completed', 'output': [{'content': [{'type': 'refusal', 'refusal': 'Bunu yapamam'}]}]})
        with self.assertRaises(ProviderResponseError):
            plan('OpenAI', {'status': 'failed', 'error': {'message': 'server_error'}})
        with self.assertRaises(EmptyResponseError):
            plan('OpenAI', {'status': 'completed', 'output': [{'type': 'reasoning', 'summary': []}]})

    def test_text_labels_pass_through_to_every_provider(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                seen = {}
                ok = {'OpenAI': {'output': [{'content': [{'type': 'output_text', 'text': 'ok'}]}]},
                      'Anthropic': {'content': [{'type': 'text', 'text': 'ok'}]},
                      'xAI': {'choices': [{'message': {'content': 'ok'}}]},
                      'Gemini': {'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}}[provider]
                plan(provider, ok, frames=[('K1 @ 12.50s', b'a'), (3.0, b'b')], seen=seen)
                dumped = json.dumps(seen['body'], ensure_ascii=False)
                self.assertIn('"K1 @ 12.50s"', dumped)
                self.assertIn('3.00. saniye', dumped)
                self.assertNotIn(KEY, seen['url'])


class FakeOpener:
    """Plays a script of HTTP outcomes: int status, (status, headers), Exception instance, or a dict body."""

    def __init__(self, *script, detail=b'{}'):
        self.script, self.calls, self.detail = list(script), [], detail

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, dict):
            return io.BytesIO(json.dumps(step).encode())
        code, headers = step if isinstance(step, tuple) else (step, {})
        raise HTTPError(request.full_url, code, 'err', headers, io.BytesIO(self.detail))


def call(opener, waits=None, headers=None, **kwargs):
    return post_json('OpenAI', 'https://api.example/v1', b'{}', headers or {'Authorization': 'Bearer ' + KEY}, 5,
                     opener=opener, sleep=(waits if waits is not None else []).append, **kwargs)


class RetryTests(unittest.TestCase):
    def test_retryable_statuses(self):
        for code in (408, 409, 429, 500, 502, 503, 504, 529):
            with self.subTest(code=code):
                waits, opener = [], FakeOpener(code, code, {'ok': 1})
                self.assertEqual(call(opener, waits), {'ok': 1})
                self.assertEqual(waits, [4, 10])

    def test_non_retryable_statuses_fail_at_once(self):
        for code in (400, 401, 403, 404, 413, 422):
            with self.subTest(code=code):
                waits, opener = [], FakeOpener(code)
                with self.assertRaisesRegex(RuntimeError, f'HTTP {code}'):
                    call(opener, waits)
                self.assertEqual((waits, len(opener.calls)), ([], 1))

    def test_gives_up_after_three_attempts_with_friendly_429(self):
        waits, opener = [], FakeOpener(429, 429, 429)
        with self.assertRaisesRegex(RuntimeError, 'HTTP 429[\\s\\S]*kota'):
            call(opener, waits)
        self.assertEqual(len(opener.calls), 3)

    def test_backoff_jitter_is_bounded(self):
        waits = []
        call(FakeOpener(503, 503, {'ok': 1}), waits, rand=lambda: 1.0)
        self.assertEqual(waits, [5.0, 12.5])

    def test_retry_after_is_honoured_and_capped(self):
        waits = []
        call(FakeOpener((429, {'Retry-After': '7'}), (503, {'retry-after-ms': '1500'}), {'ok': 1}), waits)
        self.assertEqual(waits, [7.0, 1.5])
        # A Retry-After far beyond the cap is reported instead of sleeping for an hour.
        waits, opener = [], FakeOpener((429, {'retry-after': '3600'}), {'ok': 1})
        with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
            call(opener, waits)
        self.assertEqual((waits, len(opener.calls)), ([], 1))

    def test_timeout_retried_once_then_explained(self):
        waits, opener = [], FakeOpener(TimeoutError('t'), {'ok': 1})
        self.assertEqual(call(opener, waits), {'ok': 1})
        self.assertEqual(waits, [])
        opener = FakeOpener(URLError(TimeoutError('t')), TimeoutError('t'), {'ok': 1})
        with self.assertRaisesRegex(RuntimeError, 'yanıt vermedi'):
            call(opener)
        self.assertEqual(len(opener.calls), 2)

    def test_dropped_connection_retried_but_offline_is_not(self):
        waits = []
        self.assertEqual(call(FakeOpener(ConnectionResetError('reset'), URLError(ConnectionAbortedError()), {'ok': 1}), waits), {'ok': 1})
        self.assertEqual(waits, [4, 10])
        opener = FakeOpener(URLError('getaddrinfo failed'))
        with self.assertRaisesRegex(RuntimeError, 'bağlanılamadı'):
            call(opener)
        self.assertEqual(len(opener.calls), 1)

    def test_friendly_messages(self):
        cases = {401: 'anahtarı geçersiz', 403: 'yetkisi yok', 404: 'Model bulunamadı', 529: 'yoğun'}
        for code, text in cases.items():
            with self.subTest(code=code):
                with self.assertRaisesRegex(RuntimeError, text):
                    call(FakeOpener(code, code, code))

    def test_key_never_in_error_text(self):
        detail = json.dumps({'error': {'message': f'Incorrect API key provided: {KEY}. Bearer {KEY}'}}).encode()
        for headers in ({'Authorization': 'Bearer ' + KEY}, {'x-api-key': KEY}, {'x-goog-api-key': KEY}):
            with self.subTest(headers=list(headers)):
                with self.assertRaises(RuntimeError) as ctx:
                    call(FakeOpener(401, detail=detail), headers=headers)
                self.assertNotIn(KEY, str(ctx.exception))
                self.assertNotIn('SuperSecret', str(ctx.exception))
                self.assertIn('Incorrect API key provided', str(ctx.exception))
        # Key-shaped strings are masked even when they are not the configured key.
        other = json.dumps({'error': {'message': 'key AIzaSyA1234567890abcdefghij rejected'}}).encode()
        with self.assertRaises(RuntimeError) as ctx:
            call(FakeOpener(403, detail=other), headers={'x-goog-api-key': 'AIzaDifferent0000000000'})
        self.assertNotIn('AIzaSyA1234567890', str(ctx.exception))
        with self.assertRaises(RuntimeError) as ctx:
            call(FakeOpener(URLError(f'proxy rejected {KEY}')))
        self.assertNotIn(KEY, str(ctx.exception))

    def test_plan_requests_use_long_timeout(self):
        seen = []

        def fake_post(provider, url, body, headers, timeout, **kwargs):
            seen.append(timeout)
            return {'content': [{'type': 'text', 'text': 'ok'}]}
        original = ai_providers.post_json
        ai_providers.post_json = fake_post
        try:
            request_plan('Anthropic', KEY, 'm', 'p', [])
        finally:
            ai_providers.post_json = original
        self.assertEqual(seen, [300])


class WorkerFrameTests(unittest.TestCase):
    def test_labels_unique_across_long_sources(self):
        from akis.ai_workers import frame_label
        self.assertNotEqual(frame_label(0, 1012.5), frame_label(1, 12.5))
        self.assertEqual(frame_label(1, 12.5), 'K1 @ 12.50s')

    def test_frame_counts_cap_and_fairness(self):
        from akis.ai_workers import frame_counts, MAX_FRAMES
        self.assertEqual(frame_counts([60.0]), [24])
        self.assertEqual(frame_counts([3.0, 60.0]), [3, 12])
        self.assertEqual(frame_counts([]), [])
        for n in (8, 9, 10, 13, 31, 32, 33, 40, 100):
            with self.subTest(n=n):
                durations = [30.0 + i for i in range(n)]
                counts = frame_counts(durations)
                self.assertLessEqual(sum(counts), MAX_FRAMES)
                self.assertGreaterEqual(sum(counts), min(MAX_FRAMES, 3 * n))
                if n <= MAX_FRAMES:
                    self.assertGreaterEqual(min(counts), 1)
                    self.assertLessEqual(max(counts) - min(counts), 1)
                else:
                    self.assertEqual(counts.count(1), MAX_FRAMES)
                    self.assertEqual((counts[0], counts[-1]), (1, 1))
        # Every source keeps a fair share; leftovers favour the longer sources.
        counts = frame_counts([2.0] * 6 + [100.0] * 6)
        self.assertEqual(sum(counts), 32)
        self.assertEqual(counts[6:], [3] * 6)
        self.assertTrue(all(2 <= c <= 3 for c in counts[:6]))


class SuggestionParsingTests(unittest.TestCase):
    GOOD = '{"suggestions":[{"trim_start":0,"trim_end":2},{"trim_start":"1","trim_end":"3"}]}'

    def test_fences_prose_and_list(self):
        for text in (self.GOOD, f'İşte plan:\n```json\n{self.GOOD}\n```\nUmarım işe yarar {{', f'Plan: {self.GOOD} — bitti.',
                     '[{"trim_start":0,"trim_end":2},{"trim_start":1,"trim_end":3}]'):
            with self.subTest(text=text[:20]):
                plans = parse_suggestions(text, 4)
                self.assertEqual([(p['trim_start'], p['trim_end']) for p in plans], [(0.0, 2.0), (1.0, 3.0)])

    def test_turkish_errors(self):
        cases = {'yalnızca metin': 'JSON bulunamadı', '{"suggestions": [': 'JSON bulunamadı', '': 'JSON bulunamadı',
                 '{"x": 1}': 'öneri', '[1, 2]': 'öneri',
                 '{"suggestions":[{"trim_start":"abc"}]}': 'kullanılabilir bir öneri',
                 '{"suggestions":[1, 2]}': 'kullanılabilir bir öneri'}
        for text, message in cases.items():
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, message):
                    parse_suggestions(text, 4)

    def test_unusable_suggestions_are_dropped_not_fatal(self):
        # One malformed entry must not discard the usable ones (this made "Öneri al" fail as a whole).
        for bad in ('"abc"', 'true', '[1]'):
            with self.subTest(bad=bad):
                plans = parse_suggestions('{"suggestions":[{"trim_start":%s},{"trim_start":0}]}' % bad, 4)
                self.assertEqual([(p['trim_start'], p['trim_end']) for p in plans], [(0.0, 4.0)])

    def test_null_trim_end_means_whole_video(self):
        plans = parse_suggestions('{"suggestions":[{"trim_start":0,"trim_end":null},{"trim_start":1}]}', 4)
        self.assertEqual(plans[0]['trim_end'], 4.0)


if __name__ == '__main__':
    unittest.main()
