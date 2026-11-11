"""Provider-specific multimodal planning and credential storage."""
import base64
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROVIDERS = {
    'OpenAI': ('gpt-4o', 'gpt-5'),
    'Anthropic': ('claude-sonnet-5-5', 'claude-opus-5-5'),
    'xAI': ('grok-4.7', 'grok-4.6'),
    'Gemini': ('gemini-3.6-flash', 'gemini-flash-latest'),
}
TRANSCRIPTION_MODELS = {'OpenAI': ('gpt-4o-mini-transcribe', 'gpt-4o-transcribe', 'whisper-1'), 'xAI': ('grok-voice-transcribe-2.0', 'grok-voice-transcribe-1.0'), 'Gemini': ('gemini-2.5-flash', 'gemini-2.5-pro')}

def post_json(provider, url, body, headers, timeout, *, opener=None, sleep=None):
    """POST and decode JSON. Busy providers are retried; failures carry the provider's own explanation."""
    import time
    opener, sleep = opener or urlopen, sleep or time.sleep
    for wait in (4, 10, None):
        try:
            with opener(Request(url, data=body, headers=headers, method='POST'), timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code in (429, 500, 503) and wait is not None:
                sleep(wait)
                continue
            detail = ''
            try:
                payload = json.loads(exc.read().decode('utf-8', 'replace'))
                error = payload.get('error', payload) if isinstance(payload, dict) else {}
                detail = str(error.get('message', '') if isinstance(error, dict) else error)[:300]
            except Exception:
                pass
            raise RuntimeError(f'{provider} API hatası: HTTP {exc.code}' + (f' — {detail}' if detail else '')) from exc
        except TimeoutError as exc:
            raise RuntimeError(f'{provider} {timeout} saniyede yanıt vermedi. Başka bir model deneyin veya tekrar deneyin.') from exc
        except URLError as exc:  # DNS, proxy, firewall or no connection at all
            if isinstance(exc.reason, TimeoutError):
                raise RuntimeError(f'{provider} {timeout} saniyede yanıt vermedi. Başka bir model deneyin veya tekrar deneyin.') from exc
            raise RuntimeError(f'{provider} sunucusuna bağlanılamadı. İnternet bağlantınızı kontrol edin. ({exc.reason})') from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f'{provider} beklenmeyen bir yanıt döndürdü; daha sonra tekrar deneyin.') from exc


def save_key(service, provider, key):
    import keyring
    keyring.set_password(service, provider.lower() + '_api_key', key)

def load_key(service, provider):
    import keyring
    return keyring.get_password(service, provider.lower() + '_api_key') or ''

def request_plan(provider, key, model, prompt, frames, transport=None, instruction=None):
    """Send ordered JPEG frames to the selected provider. transport enables isolated tests."""
    if provider not in PROVIDERS or not key or not model:
        raise ValueError('Sağlayıcı, API anahtarı ve model gereklidir.')
    encoded = [(at, base64.b64encode(data).decode('ascii')) for at, data in frames]
    instruction = instruction or 'Kısa video kurgusunda uzman, ölçülü ve pratik bir Türkçe kreatif direktörsün.'
    headers = {'Content-Type': 'application/json'}
    if provider == 'OpenAI':
        url = 'https://api.openai.com/v1/responses'
        headers['Authorization'] = 'Bearer ' + key
        content = [{'type': 'input_text', 'text': prompt}]
        for at, img in encoded:
            content.extend([{'type': 'input_text', 'text': f'{at:.2f}. saniye'}, {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + img}])
        body = {'model': model, 'instructions': instruction, 'input': [{'role': 'user', 'content': content}]}
    elif provider == 'Anthropic':
        url = 'https://api.anthropic.com/v1/messages'
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
        content = [{'type': 'text', 'text': prompt}]
        for at, img in encoded:
            content.extend([{'type': 'text', 'text': f'{at:.2f}. saniye'}, {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': img}}])
        body = {'model': model, 'max_tokens': 8192, 'system': instruction, 'messages': [{'role': 'user', 'content': content}]}
    elif provider == 'xAI':
        url = 'https://api.x.ai/v1/chat/completions'
        headers['Authorization'] = 'Bearer ' + key
        content = [{'type': 'text', 'text': prompt}]
        for at, img in encoded:
            content.extend([{'type': 'text', 'text': f'{at:.2f}. saniye'}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + img}}])
        body = {'model': model, 'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': content}]}
    else:
        from urllib.parse import quote
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(model, safe='') + ':generateContent'
        headers['x-goog-api-key'] = key
        parts = [{'text': instruction + '\n' + prompt}]
        for at, img in encoded:
            parts.extend([{'text': f'{at:.2f}. saniye'}, {'inline_data': {'mime_type': 'image/jpeg', 'data': img}}])
        body = {'contents': [{'parts': parts}]}
    if transport:
        result = transport(url, headers, body)
    else:
        result = post_json(provider, url, json.dumps(body).encode(), headers, 120)
    if provider == 'OpenAI':
        return ''.join(part.get('text', '') for item in result.get('output', []) for part in item.get('content', []) if part.get('type') == 'output_text')
    if provider == 'Anthropic':
        return ''.join(p.get('text', '') for p in result['content'] if p.get('type') == 'text')
    if provider == 'xAI':
        return result['choices'][0]['message']['content']
    return ''.join(p.get('text', '') for p in result['candidates'][0]['content']['parts'])


def transcribe(provider, key, model, audio):
    if provider == 'OpenAI':
        from openai import OpenAI
        with open(audio, 'rb') as handle:
            return OpenAI(api_key=key).audio.transcriptions.create(model=model, file=handle, language='tr').text
    data = audio.read_bytes()
    if provider == 'Gemini':
        from urllib.parse import quote
        if len(data) > 14_000_000:
            raise ValueError('Gemini için ses dosyası çok büyük (en fazla 14 MB).')
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(model, safe='') + ':generateContent'
        body = json.dumps({'contents': [{'parts': [{'text': 'Türkçe konuşmayı aynen metne çevir; sadece metni döndür.'}, {'inline_data': {'mime_type': 'audio/mp3', 'data': base64.b64encode(data).decode('ascii')}}]}]}).encode()
        headers = {'Content-Type': 'application/json', 'x-goog-api-key': key}
    elif provider == 'xAI':
        import uuid
        boundary = 'akis' + uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\ntr\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        headers = {'Content-Type': 'multipart/form-data; boundary=' + boundary, 'Authorization': 'Bearer ' + key}
        url = 'https://api.x.ai/v1/stt'
    else:
        raise ValueError('Bu sağlayıcı için transkripsiyon desteklenmiyor.')
    result = post_json(provider, url, body, headers, 180)
    if provider == 'xAI':
        return result['text']
    return ''.join(part.get('text', '') for part in result['candidates'][0]['content']['parts'])
