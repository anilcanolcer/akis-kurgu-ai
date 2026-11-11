"""Gemini text / image / video request shapes and response handling (fake transports only)."""
import base64
import io
import json
import unittest
from email.message import Message
from urllib.error import HTTPError, URLError

from akis import ai_providers, gemini_api as g
from akis.ai_providers import (EmptyResponseError, FreeTierUnavailableError, ProviderHTTPError, ProviderResponseError,
                               ResponseBlockedError, ResponseTruncatedError)

KEY = 'AIzaSyFakeKeyForTests_1234567890abcd'
PNG = b'\x89PNG\r\n\x1a\nfake-png'


def ok_text(text='Merhaba', **extra):
    result = {'candidates': [{'content': {'parts': [{'text': text}]}, 'finishReason': 'STOP'}],
              'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 20, 'thoughtsTokenCount': 300,
                                'totalTokenCount': 420, 'serviceTier': 'standard'}}
    result.update(extra)
    return result


class Recorder:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        step = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(step, BaseException):
            raise step
        return step


class FakeOpener:
    """Plays HTTP outcomes: a dict (JSON body), (status, detail_dict) or an exception instance."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, tuple):
            code, detail = step
            raise HTTPError(request.full_url, code, 'err', Message(), io.BytesIO(json.dumps(detail).encode()))
        return io.BytesIO(json.dumps(step).encode())


def no_sleep(_):
    pass


def dumped(body):
    return json.dumps(body, ensure_ascii=False)


class TextTests(unittest.TestCase):
    def test_body_shape_has_thinking_level_and_no_sampling_params(self):
        rec = Recorder(ok_text())
        result = g.generate_text(KEY, 'gemini-3.8-flash', ['REHBER', 'GÖREV'], system_instruction='SİSTEM',
                                 thinking_level='low', max_output_tokens=9000, stop_sequences=['###'], transport=rec)
        url, headers, body = rec.calls[0]
        self.assertEqual(url, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent')
        self.assertEqual(headers['x-goog-api-key'], KEY)
        self.assertNotIn(KEY, url)
        self.assertEqual(body['system_instruction'], {'parts': [{'text': 'SİSTEM'}]})
        self.assertEqual(body['contents'], [{'role': 'user', 'parts': [{'text': 'REHBER'}, {'text': 'GÖREV'}]}])
        config = body['generationConfig']
        self.assertEqual(config['thinkingConfig'], {'thinkingLevel': 'low'})
        self.assertEqual(config['maxOutputTokens'], 9000)
        self.assertEqual(config['stopSequences'], ['###'])
        for banned in ('temperature', 'topP', 'topK', 'top_p', 'top_k', 'thinkingBudget'):
            self.assertNotIn(banned, dumped(body))
        self.assertEqual(result.text, 'Merhaba')
        self.assertEqual(result.usage['thoughts'], 300)
        self.assertFalse(result.fell_back)

    def test_history_and_validation(self):
        body = g.text_body('soru', history=[('user', 'a'), ('model', 'b')])
        self.assertEqual([c['role'] for c in body['contents']], ['user', 'model', 'user'])
        with self.assertRaisesRegex(ValueError, 'düşünme'):
            g.text_body('x', thinking_level='minimal')
        with self.assertRaises(ValueError):
            g.text_body('x', max_output_tokens=40000)
        with self.assertRaises(ValueError):
            g.text_body('')
        with self.assertRaises(ValueError):
            g.generate_text('', 'gemini-3.8-flash', 'x', transport=Recorder(ok_text()))

    def test_thought_parts_skipped(self):
        result = g.parse_text({'candidates': [{'content': {'parts': [{'text': 'plan…', 'thought': True},
                                                                     {'text': 'Sahne.'}]}}]})
        self.assertEqual(result.text, 'Sahne.')

    def test_blocked_truncated_empty(self):
        with self.assertRaisesRegex(ResponseBlockedError, 'SAFETY'):
            g.parse_text({'candidates': [{'finishReason': 'SAFETY'}]})
        with self.assertRaisesRegex(ResponseBlockedError, 'PROHIBITED_CONTENT'):
            g.parse_text({'promptFeedback': {'blockReason': 'PROHIBITED_CONTENT'}})
        with self.assertRaises(ResponseTruncatedError) as ctx:
            g.parse_text({'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'yarım'}]}}]})
        self.assertEqual(ctx.exception.partial, 'yarım')
        with self.assertRaises(EmptyResponseError):
            g.parse_text({'candidates': []})
        with self.assertRaises(EmptyResponseError):
            g.parse_text({'candidates': [{'content': {'parts': [{'text': 'x', 'thought': True}]}}]})

    def test_fallback_on_overload_reports_model(self):
        rec = Recorder(ProviderHTTPError('Gemini API hatası: HTTP 503 — high demand', 503), ok_text('ok'))
        result = g.generate_text(KEY, 'gemini-3.8-flash', 'x', transport=rec)
        self.assertEqual([c[0].split('/')[-1] for c in rec.calls],
                         ['gemini-3.8-flash:generateContent', 'gemini-3.6-flash:generateContent'])
        self.assertEqual((result.model, result.requested_model), ('gemini-3.6-flash', 'gemini-3.8-flash'))
        self.assertTrue(result.fell_back)
        self.assertIn('gemini-3.8-flash', result.fallback_reason)

    def test_argon_chain_and_free_tier_fallback(self):
        self.assertEqual(g.fallback_chain('gemini-4-argon'), ['gemini-4-argon', 'gemini-3.8-flash', 'gemini-3.6-flash'])
        rec = Recorder(FreeTierUnavailableError('ücretsiz katman', 429), ProviderHTTPError('HTTP 503', 503), ok_text())
        result = g.generate_text(KEY, 'gemini-4-argon', 'x', transport=rec)
        self.assertEqual(result.model, 'gemini-3.6-flash')
        self.assertIn('ücretsiz', result.fallback_reason)

    def test_no_fallback_for_blocked_or_auth_or_when_disabled(self):
        rec = Recorder({'candidates': [{'finishReason': 'SAFETY'}]})
        with self.assertRaises(ResponseBlockedError):
            g.generate_text(KEY, 'gemini-3.8-flash', 'x', transport=rec)
        self.assertEqual(len(rec.calls), 1)
        rec = Recorder(ProviderHTTPError('HTTP 401', 401))
        with self.assertRaises(ProviderHTTPError):
            g.generate_text(KEY, 'gemini-3.8-flash', 'x', transport=rec)
        self.assertEqual(len(rec.calls), 1)
        rec = Recorder(ProviderHTTPError('HTTP 503', 503))
        with self.assertRaises(ProviderHTTPError):
            g.generate_text(KEY, 'gemini-3.8-flash', 'x', fallbacks=(), transport=rec)
        self.assertEqual(len(rec.calls), 1)

    def test_last_error_names_skipped_models(self):
        rec = Recorder(ProviderHTTPError('HTTP 503', 503), ProviderHTTPError('HTTP 500', 500))
        with self.assertRaises(ProviderHTTPError) as ctx:
            g.generate_text(KEY, 'gemini-3.8-flash', 'x', transport=rec, sleep=no_sleep)
        self.assertIn('gemini-3.8-flash', str(ctx.exception))
        self.assertEqual(ctx.exception.code, 500)

    def test_timeout_moves_to_next_model_without_waiting_twice(self):
        opener = FakeOpener(TimeoutError(), ok_text('yedek'))
        result = g.generate_text(KEY, 'gemini-3.8-flash', 'x', opener=opener, sleep=no_sleep)
        self.assertEqual(result.model, 'gemini-3.6-flash')
        self.assertEqual(len(opener.calls), 2)
        self.assertGreaterEqual(opener.calls[0][1], 180)

    def test_overload_retried_once_then_fallback(self):
        busy = (503, {'error': {'message': 'This model is currently experiencing high demand'}})
        opener = FakeOpener(busy, busy, ok_text())
        result = g.generate_text(KEY, 'gemini-3.8-flash', 'x', opener=opener, sleep=no_sleep)
        self.assertEqual(len(opener.calls), 3)
        self.assertEqual(result.model, 'gemini-3.6-flash')

    def test_key_never_in_error_text(self):
        rec = Recorder(RuntimeError(f'connection failed for key={KEY}'))
        with self.assertRaises(RuntimeError) as ctx:
            g.generate_text(KEY, 'gemini-3.6-flash', 'x', transport=rec)
        self.assertNotIn(KEY, str(ctx.exception))
        opener = FakeOpener((400, {'error': {'message': f'API key {KEY} not valid'}}))
        with self.assertRaises(ProviderHTTPError) as ctx:
            g.generate_text(KEY, 'gemini-3.6-flash', 'x', opener=opener, sleep=no_sleep)
        self.assertNotIn(KEY, str(ctx.exception))
        self.assertNotIn(KEY, opener.calls[0][0].full_url)

    def test_list_models_paginates(self):
        pages = [{'models': [{'name': 'models/gemini-3.8-flash'}], 'nextPageToken': 'p2'},
                 {'models': [{'name': 'models/gemini-omni-1.2-flash'}]}]
        seen = []

        def getter(url, headers, timeout):
            seen.append((url, headers))
            return json.dumps(pages.pop(0)).encode()
        self.assertEqual(g.list_models(KEY, getter=getter), ['gemini-3.8-flash', 'gemini-omni-1.2-flash'])
        self.assertTrue(seen[0][0].endswith('/v1beta/models?pageSize=200'))
        self.assertIn('pageToken=p2', seen[1][0])
        self.assertTrue(all(KEY not in url and h['x-goog-api-key'] == KEY for url, h in seen))


class FreeTierTests(unittest.TestCase):
    IMAGE_429 = (429, {'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED', 'message':
                 'Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, '
                 'limit: 0, model: gemini-nano-banana-2.1'}})
    VIDEO_429 = (429, {'error': {'message': 'Rate limit exceeded for model gemini-omni-1.2-flash (limit: 0 requests '
                 'per day on Free Tier). Please upgrade your tier at https://ai.dev/rate-limit.',
                 'code': 'too_many_requests'}})

    def test_image_free_tier_not_retried(self):
        opener = FakeOpener(self.IMAGE_429, ok_text())
        with self.assertRaises(FreeTierUnavailableError) as ctx:
            g.generate_image(KEY, 'gemini-nano-banana-2.1', 'a cat', opener=opener)
        self.assertEqual(len(opener.calls), 1)
        self.assertIn('ücretsiz katmanda kullanılamıyor', str(ctx.exception))
        self.assertIn('faturalandırmayı', str(ctx.exception))

    def test_video_free_tier_with_string_code(self):
        opener = FakeOpener(self.VIDEO_429)
        with self.assertRaises(FreeTierUnavailableError) as ctx:
            g.generate_video(KEY, 'waves', opener=opener)
        self.assertEqual(len(opener.calls), 1)
        self.assertNotIn(KEY, str(ctx.exception))

    def test_ordinary_429_still_retried(self):
        opener = FakeOpener((429, {'error': {'message': 'slow down'}}), {'ok': True})
        self.assertEqual(ai_providers.post_json('Gemini', 'https://x', b'{}', {}, 5, opener=opener, sleep=no_sleep),
                         {'ok': True})
        self.assertFalse(ai_providers.is_free_tier_zero('limit: 10, free tier'))


class ImageTests(unittest.TestCase):
    def refs(self):
        return [g.ImageInput(PNG, 'image/png', 'character', 'Elif'), g.ImageInput(b'\xff\xd8jpeg', 'image/jpeg', 'style')]

    def image_response(self, key='inlineData', mime='mimeType'):
        return {'candidates': [{'content': {'parts': [
            {'text': 'thinking', 'thought': True},
            {key: {mime: 'image/png', 'data': base64.b64encode(b'draft').decode()}, 'thought': True},
            {'text': 'Here is your image'},
            {key: {mime: 'image/png', 'data': base64.b64encode(PNG).decode()}}]}, 'finishReason': 'STOP'}]}

    def test_body_shape_and_reference_order(self):
        rec = Recorder(self.image_response())
        result = g.generate_image(KEY, 'gemini-nano-banana-2.1', 'Elif at the pier', references=self.refs(),
                                  aspect_ratio='21:9', image_size='2K', transport=rec)
        url, headers, body = rec.calls[0]
        self.assertTrue(url.endswith('/v1beta/models/gemini-nano-banana-2.1:generateContent'))
        self.assertEqual(headers['x-goog-api-key'], KEY)
        parts = body['contents'][0]['parts']
        self.assertIn('Elif at the pier', parts[0]['text'])
        self.assertIn('Image 1: character identity', parts[0]['text'])
        self.assertIn('Image 2: style reference', parts[0]['text'])
        self.assertEqual(parts[1]['inline_data']['mime_type'], 'image/png')
        self.assertEqual(base64.b64decode(parts[1]['inline_data']['data']), PNG)
        self.assertEqual(parts[2]['inline_data']['mime_type'], 'image/jpeg')
        self.assertEqual(body['generationConfig'], {'responseModalities': ['IMAGE'],
                                                    'imageConfig': {'aspectRatio': '21:9', 'imageSize': '2K'}})
        self.assertNotIn('temperature', dumped(body))
        self.assertEqual(result.data, PNG)  # the thought image was skipped
        self.assertEqual(result.text, 'Here is your image')

    def test_snake_case_response_accepted(self):
        result = g.parse_image(self.image_response('inline_data', 'mime_type'))
        self.assertEqual((result.data, result.mime_type), (PNG, 'image/png'))

    def test_blocked_and_empty(self):
        with self.assertRaisesRegex(ResponseBlockedError, 'IMAGE_SAFETY'):
            g.parse_image({'candidates': [{'finishReason': 'IMAGE_SAFETY', 'content': {'parts': []}}]})
        with self.assertRaisesRegex(ResponseBlockedError, 'PROHIBITED_CONTENT'):
            g.parse_image({'candidates': [{'finishReason': 'PROHIBITED_CONTENT'}]})
        with self.assertRaisesRegex(EmptyResponseError, 'görsel döndürmedi.*Sorry'):
            g.parse_image({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Sorry'}]}}]})

    def test_validation(self):
        model = 'gemini-nano-banana-2.1'
        with self.assertRaisesRegex(ValueError, 'en-boy'):
            g.validate_image_request(model, 'x', [], '7:5', '1K')
        with self.assertRaisesRegex(ValueError, 'büyük K'):
            g.validate_image_request(model, 'x', [], '1:1', '2k')
        with self.assertRaisesRegex(ValueError, '512'):
            g.validate_image_request(model, 'x', [], '1:1', '512')
        g.validate_image_request('gemini-3.1-flash-image', 'x', [], '1:1', '512')
        with self.assertRaisesRegex(ValueError, 'boş'):
            g.validate_image_request(model, '  ', [], '1:1', '1K')
        many = [g.ImageInput(PNG, 'image/png', 'object') for _ in range(15)]
        with self.assertRaisesRegex(ValueError, '14'):
            g.validate_image_request(model, 'x', many, '1:1', '1K')
        chars = [g.ImageInput(PNG, 'image/png', 'character') for _ in range(5)]
        with self.assertRaisesRegex(ValueError, 'karakter'):
            g.validate_image_request(model, 'x', chars, '1:1', '1K')
        objects = [g.ImageInput(PNG, 'image/png', 'object') for _ in range(11)]
        with self.assertRaisesRegex(ValueError, '10'):
            g.validate_image_request(model, 'x', objects, '1:1', '1K')
        with self.assertRaisesRegex(ValueError, 'çok büyük'):
            g.validate_image_request(model, 'x', [g.ImageInput(b'x' * (g.MAX_IMAGE_BYTES + 1))], '1:1', '1K')
        with self.assertRaisesRegex(ValueError, 'desteklenmeyen'):
            g.validate_image_request(model, 'x', [g.ImageInput(PNG, 'image/gif')], '1:1', '1K')

    def test_image_timeout_not_retried(self):
        opener = FakeOpener(TimeoutError(), ok_text())
        with self.assertRaisesRegex(ProviderResponseError, 'görsel döndürmedi'):
            g.generate_image(KEY, 'gemini-nano-banana-2.1', 'x', opener=opener)
        self.assertEqual(len(opener.calls), 1)


class VideoTests(unittest.TestCase):
    def video_response(self, data=b'mp4-bytes'):
        return {'id': 'int-1', 'status': 'completed', 'steps': [
            {'type': 'thought'},
            {'type': 'model_output', 'content': [{'type': 'video', 'mime_type': 'video/mp4',
                                                  'data': base64.b64encode(data).decode()}]}]}

    def test_text_to_video_body(self):
        rec = Recorder(self.video_response())
        result = g.generate_video(KEY, 'A lighthouse at dusk, waves', aspect_ratio='9:16', resolution='1080p',
                                  duration=8, transport=rec)
        url, headers, body = rec.calls[0]
        self.assertEqual(url, 'https://generativelanguage.googleapis.com/v1beta/interactions')
        self.assertEqual(headers['x-goog-api-key'], KEY)
        self.assertEqual(body, {'model': 'gemini-omni-1.2-flash', 'input': 'A lighthouse at dusk, waves',
                                'response_format': {'type': 'video', 'aspect_ratio': '9:16', 'resolution': '1080p',
                                                    'duration': '8s'}})
        self.assertEqual((result.data, result.mime_type, result.interaction_id), (b'mp4-bytes', 'video/mp4', 'int-1'))

    def test_image_to_video_body_image_first(self):
        rec = Recorder(self.video_response())
        g.generate_video(KEY, 'slow push-in', images=[g.ImageInput(PNG, 'image/png')], duration=5, transport=rec)
        body = rec.calls[0][2]
        self.assertEqual(body['input'][0], {'type': 'image', 'data': base64.b64encode(PNG).decode(), 'mime_type': 'image/png'})
        self.assertEqual(body['input'][1], {'type': 'text', 'text': 'slow push-in'})
        self.assertEqual(body['response_format']['duration'], '5s')
        self.assertEqual(body['response_format']['resolution'], '720p')

    def test_first_last_frame_and_validation(self):
        two = [g.ImageInput(PNG), g.ImageInput(PNG)]
        rec = Recorder(self.video_response())
        g.generate_video(KEY, 'morph', images=two, first_last=True, duration=10, transport=rec)
        self.assertEqual([p['type'] for p in rec.calls[0][2]['input']], ['image', 'image', 'text'])
        with self.assertRaisesRegex(ValueError, '10'):
            g.validate_video_request('x', two, '16:9', '720p', 11, True)
        with self.assertRaisesRegex(ValueError, 'iki görsel'):
            g.validate_video_request('x', two[:1], '16:9', '720p', 5, True)
        for duration in (2, 16, 8.0, True):
            with self.assertRaisesRegex(ValueError, 'tam saniye'):
                g.validate_video_request('x', [], '16:9', '720p', duration, False)
        with self.assertRaisesRegex(ValueError, '16:9'):
            g.validate_video_request('x', [], '1:1', '720p', 5, False)
        with self.assertRaisesRegex(ValueError, 'çözünürlük'):
            g.validate_video_request('x', [], '16:9', '480p', 5, False)
        with self.assertRaisesRegex(ValueError, '6'):
            g.validate_video_request('x', [g.ImageInput(PNG)] * 7, '16:9', '720p', 5, False)

    def test_no_video_means_block_or_region(self):
        with self.assertRaisesRegex(ResponseBlockedError, 'bölgesel'):
            g.parse_video({'id': 'x', 'status': 'completed', 'steps': [{'type': 'model_output', 'content': []}]})
        with self.assertRaisesRegex(ProviderResponseError, 'failed'):
            g.parse_video({'status': 'failed', 'error': {'message': 'internal'}})
        with self.assertRaises(ResponseBlockedError):
            g.parse_video({'status': 'failed', 'error': {'message': 'blocked by safety policy'}})

    def test_video_never_retried(self):
        opener = FakeOpener(TimeoutError(), self.video_response())
        with self.assertRaises(g.VideoTimeoutError) as ctx:
            g.generate_video(KEY, 'x', opener=opener, timeout=900)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0][1], 900)
        self.assertIn('otomatik', str(ctx.exception))
        opener = FakeOpener((503, {'error': {'message': 'busy'}}), self.video_response())
        with self.assertRaises(ProviderHTTPError):
            g.generate_video(KEY, 'x', opener=opener)
        self.assertEqual(len(opener.calls), 1)
        opener = FakeOpener(URLError(ConnectionResetError()), self.video_response())
        with self.assertRaises(RuntimeError):
            g.generate_video(KEY, 'x', opener=opener)
        self.assertEqual(len(opener.calls), 1)

    def test_uri_delivery_polls_and_downloads(self):
        response = {'id': 'i', 'status': 'completed', 'steps': [{'type': 'model_output', 'content': [
            {'type': 'video', 'mime_type': 'video/mp4', 'uri': 'https://generativelanguage.googleapis.com/v1beta/files/abc-123'}]}]}
        rec = Recorder(response)
        answers = [b'{"state": "PROCESSING"}', b'{"state": "ACTIVE"}', b'VIDEO']
        seen, waits = [], []

        def getter(url, headers, timeout):
            seen.append((url, headers))
            return answers.pop(0)
        result = g.generate_video(KEY, 'x', delivery='uri', transport=rec, getter=getter, sleep=waits.append)
        self.assertEqual(rec.calls[0][2]['response_format']['delivery'], 'uri')
        self.assertEqual(result.data, b'VIDEO')
        self.assertEqual([u for u, _ in seen], [g.API_BASE + '/files/abc-123'] * 2 + [g.API_BASE + '/files/abc-123:download?alt=media'])
        self.assertEqual(len(waits), 1)
        self.assertTrue(all(KEY not in u and h['x-goog-api-key'] == KEY for u, h in seen))


class RequestPlanTests(unittest.TestCase):
    def test_gemini_plan_sends_thinking_level_and_no_temperature(self):
        rec = Recorder(ok_text('{"plan": 1}'))
        self.assertEqual(ai_providers.request_plan('Gemini', KEY, 'gemini-3.8-flash', 'p', [(0, b'j')], rec), '{"plan": 1}')
        body = rec.calls[0][2]
        self.assertEqual(body['generationConfig']['thinkingConfig'], {'thinkingLevel': ai_providers.GEMINI_PLAN_THINKING})
        self.assertGreaterEqual(body['generationConfig']['maxOutputTokens'], 16384)
        self.assertNotIn('temperature', dumped(body))
        self.assertEqual(ai_providers.PROVIDERS['Gemini'][:2], ('gemini-3.8-flash', 'gemini-4-argon'))

    def test_gemini_plan_falls_back(self):
        rec = Recorder(ProviderHTTPError('HTTP 503', 503), ok_text('ok'))
        self.assertEqual(ai_providers.request_plan('Gemini', KEY, 'gemini-3.8-flash', 'p', [(0, b'j')], rec), 'ok')
        self.assertIn('gemini-3.6-flash', rec.calls[1][0])
        rec = Recorder({'candidates': [{'finishReason': 'SAFETY'}]})
        with self.assertRaises(ResponseBlockedError):
            ai_providers.request_plan('Gemini', KEY, 'gemini-3.8-flash', 'p', [(0, b'j')], rec)
        self.assertEqual(len(rec.calls), 1)


if __name__ == '__main__':
    unittest.main()
