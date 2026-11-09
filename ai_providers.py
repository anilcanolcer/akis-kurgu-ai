"""Provider-specific multimodal planning and credential storage."""
import base64
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

PROVIDERS = {
    'OpenAI': ('gpt-4o', 'gpt-5'),
    'Anthropic': ('claude-sonnet-4-6', 'claude-opus-4-6'),
    'xAI': ('grok-4.7', 'grok-4.6'),
    'Gemini': ('gemini-2.5-flash', 'gemini-2.5-pro'),
}
TRANSCRIPTION_MODELS = {'OpenAI': ('gpt-4o-mini-transcribe', 'gpt-4o-transcribe', 'whisper-1'), 'xAI': ('grok-voice-transcribe-2.0', 'grok-voice-transcribe-1.0'), 'Gemini': ('gemini-2.5-flash', 'gemini-2.5-pro')}

def save_key(service, provider, key):
    import keyring
    keyring.set_password(service, provider.lower() + '_api_key', key)

def load_key(service, provider):
    import keyring
    return keyring.get_password(service, provider.lower() + '_api_key') or ''

def request_plan(provider, key, model, prompt, frames, transport=None):
    """Send ordered JPEG frames to the selected provider. transport enables isolated tests."""
    if provider not in PROVIDERS or not key or not model:
        raise ValueError('Sağlayıcı, API anahtarı ve model gereklidir.')
    encoded = [(at, base64.b64encode(data).decode('ascii')) for at, data in frames]
    instruction = 'Kısa video kurgusunda uzman, ölçülü ve pratik bir Türkçe kreatif direktörsün.'
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
        body = {'model': model, 'max_tokens': 2048, 'system': instruction, 'messages': [{'role': 'user', 'content': content}]}
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
        try:
            with urlopen(Request(url, data=json.dumps(body).encode(), headers=headers, method='POST'), timeout=120) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f'{provider} API hatası: HTTP {exc.code}') from exc
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
    try:
        with urlopen(Request(url, data=body, headers=headers, method='POST'), timeout=180) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'{provider} API hatası: HTTP {exc.code}') from exc
    if provider == 'xAI':
        return result['text']
    return ''.join(part.get('text', '') for part in result['candidates'][0]['content']['parts'])
