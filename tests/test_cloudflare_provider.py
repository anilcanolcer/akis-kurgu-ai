"""Cloudflare Workers AI as a planning provider (OpenAI-compatible chat endpoint, account-scoped)."""
import unittest

from akis import ai_providers
from akis.ai_providers import (CLOUDFLARE_MAX_TOKENS, PROVIDERS, cloudflare_credentials, request_plan,
                               ResponseTruncatedError)

ACCOUNT = '0123456789abcdef0123456789ABCDEF'
TOKEN = 'cfut_secret-token-value'
KEY = f'{ACCOUNT}:{TOKEN}'
MODEL = PROVIDERS['Cloudflare'][0]


class CloudflareProviderTests(unittest.TestCase):
    def test_key_field_holds_account_id_and_token(self):
        self.assertEqual(cloudflare_credentials(f'  {ACCOUNT} : {TOKEN}  '), (ACCOUNT.lower(), TOKEN))
        for bad in ('', TOKEN, f'{ACCOUNT}:', f'kisa:{TOKEN}', f'{ACCOUNT[:-1]}z:{TOKEN}'):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, 'Hesap Kimliği'):
                    cloudflare_credentials(bad)

    def test_request_goes_to_the_account_endpoint_with_frames(self):
        seen = {}

        def transport(url, headers, body):
            seen.update(url=url, headers=headers, body=body)
            return {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"summary": "tamam"}'}}]}

        text = request_plan('Cloudflare', KEY, MODEL, 'İstek', [('K0 @ 1.50s', b'jpeg-bytes')],
                            transport=transport, instruction='Talimat')
        self.assertEqual(text, '{"summary": "tamam"}')
        self.assertEqual(seen['url'], f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT.lower()}/ai/v1/chat/completions')
        self.assertEqual(seen['headers']['Authorization'], 'Bearer ' + TOKEN)
        self.assertNotIn(TOKEN, seen['url'])
        body = seen['body']
        self.assertEqual((body['model'], body['max_tokens']), (MODEL, CLOUDFLARE_MAX_TOKENS))
        self.assertEqual(body['messages'][0], {'role': 'system', 'content': 'Talimat'})
        parts = body['messages'][1]['content']
        self.assertEqual([part['type'] for part in parts], ['text', 'text', 'image_url'])
        self.assertEqual(parts[1]['text'], 'K0 @ 1.50s')
        self.assertTrue(parts[2]['image_url']['url'].startswith('data:image/jpeg;base64,'))

    def test_malformed_key_is_rejected_before_any_request(self):
        calls = []
        with self.assertRaisesRegex(ValueError, 'Hesap Kimliği'):
            request_plan('Cloudflare', TOKEN, MODEL, 'İstek', [], transport=lambda *a: calls.append(a))
        self.assertEqual(calls, [])

    def test_truncated_answer_is_reported(self):
        answer = {'choices': [{'finish_reason': 'length', 'message': {'content': '{"summary": "yar'}}]}
        with self.assertRaises(ResponseTruncatedError):
            request_plan('Cloudflare', KEY, MODEL, 'İstek', [], transport=lambda *a: answer)

    def test_token_never_appears_in_http_errors(self):
        import io
        from urllib.error import HTTPError

        def opener(request, timeout=None):
            raise HTTPError(request.full_url, 401, 'Unauthorized', {}, io.BytesIO(
                ('{"errors":[{"message":"Invalid token %s"}]}' % TOKEN).encode()))

        account, token = cloudflare_credentials(KEY)
        with self.assertRaises(RuntimeError) as caught:
            ai_providers.post_json('Cloudflare', f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions',
                                   b'{}', {'Authorization': 'Bearer ' + token}, 5, opener=opener, sleep=lambda s: None)
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_model_outside_the_plan_gets_a_clear_hint(self):
        import io
        from urllib.error import HTTPError

        def opener(request, timeout=None):
            raise HTTPError(request.full_url, 403, 'Forbidden', {}, io.BytesIO(
                b'{"errors":[{"message":"AiError: Model @cf/x/y is not available on the Workers Free plan"}],"success":false}'))

        with self.assertRaises(RuntimeError) as caught:
            ai_providers.post_json('Cloudflare', 'https://api.cloudflare.com/client/v4/accounts/a/ai/v1/chat/completions',
                                   b'{}', {'Authorization': 'Bearer ' + TOKEN}, 5, opener=opener, sleep=lambda s: None)
        message = str(caught.exception)
        self.assertIn('Workers Free plan', message)       # Cloudflare's own reason is shown
        self.assertIn('planında kullanılamıyor', message)  # with a Turkish explanation
        self.assertNotIn('anahtarı geçersiz', message)


if __name__ == '__main__':
    unittest.main()
