"""Gemini text, image (Nano Banana) and video (Omni Flash, Interactions API) calls over raw HTTP.

Every function takes an injectable ``transport(url, headers, body_dict) -> dict`` so tests never touch the
network; without one, requests go through ``ai_providers.post_json`` (typed errors, key scrubbing).
The API key travels in the ``x-goog-api-key`` header and never appears in a URL or in error text.
"""
import base64
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from akis.ai_providers import (GEMINI_TEXT_FALLBACKS, EmptyResponseError, FreeTierUnavailableError,
                               ProviderHTTPError, ProviderResponseError, ResponseBlockedError,
                               ResponseTruncatedError, _http_detail, _http_hint, _scrub, is_fallback_error,
                               post_json)

PROVIDER = 'Gemini'
API_BASE = 'https://generativelanguage.googleapis.com/v1beta'  # image docs show /v1/: change here only
KEY_IN_QUERY = False  # True would send ?key= like the docs' curl; the header keeps keys out of URLs/logs

TEXT_MODELS = ('gemini-3.8-flash', 'gemini-4-argon', 'gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-4-carbon')
IMAGE_MODELS = ('gemini-nano-banana-2.1', 'gemini-3.1-flash-image', 'gemini-3.1-flash-lite-image', 'gemini-3-pro-image')
VIDEO_MODELS = ('gemini-omni-1.2-flash', 'gemini-omni-1.1-flash')

THINKING_LEVELS = ('low', 'medium', 'high')
MAX_OUTPUT_TOKENS = 32768  # non-streaming per-request cap; includes thinking tokens

ASPECT_RATIOS = ('1:1', '1:4', '1:8', '2:3', '3:2', '3:4', '4:1', '4:3', '4:5', '5:4', '8:1', '9:16', '16:9', '21:9')
IMAGE_SIZES = ('1K', '2K', '4K')
SIZE_512_MODELS = ('gemini-3.1-flash-image',)
MAX_REFERENCES = 14            # documented for nano-banana-2.1 / 3.1-flash-image; assumed for the others
MAX_CHARACTER_REFERENCES = 4
MAX_OBJECT_REFERENCES = 10
MAX_IMAGE_BYTES = 7 * 1024 * 1024     # per inline image (conservative; not from the docs)
MAX_INLINE_TOTAL = 18 * 1024 * 1024   # whole request stays under the ~20 MB inline request limit
IMAGE_MIME_TYPES = ('image/png', 'image/jpeg', 'image/webp')

VIDEO_ASPECTS = ('16:9', '9:16')
VIDEO_RESOLUTIONS = ('360p', '720p', '1080p', '4k')
VIDEO_MIN_SECONDS, VIDEO_MAX_SECONDS, VIDEO_FIRST_LAST_MAX = 3, 15, 10
VIDEO_MAX_IMAGES = 6

TEXT_TIMEOUT = 240            # 3.8 Flash was seen silent for > 90 s under load
TEXT_BACKOFF = (4,)           # one quick retry on 503 per model, then the next model in the chain
IMAGE_TIMEOUT = 300
VIDEO_TIMEOUT = 900            # generation is synchronous and may take minutes
FILE_POLL_SECONDS = 5
FILE_POLL_LIMIT = 600

_BLOCKED = {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'IMAGE_SAFETY',
            'IMAGE_PROHIBITED_CONTENT', 'IMAGE_RECITATION', 'IMAGE_OTHER', 'NO_IMAGE'}


class VideoTimeoutError(ProviderResponseError):
    """The video call timed out; it is never retried automatically (a retry could be billed twice)."""


@dataclass
class TextResult:
    text: str
    model: str                      # the model that actually answered
    usage: dict = field(default_factory=dict)
    finish_reason: str = ''
    truncated: bool = False
    requested_model: str = ''       # what the caller asked for (differs after a fallback)
    fallback_reason: str = ''       # why the requested model was skipped, Turkish, '' when none

    @property
    def fell_back(self):
        return bool(self.requested_model) and self.requested_model != self.model


@dataclass
class ImageInput:
    """An inline image. ``role`` ('character' | 'style' | 'object' | 'pose') and ``label`` describe a
    reference's purpose; they are written into the prompt, the API itself has no such field."""
    data: bytes
    mime_type: str = 'image/png'
    role: str = 'object'
    label: str = ''


@dataclass
class ImageResult:
    data: bytes
    mime_type: str
    model: str
    text: str = ''
    usage: dict = field(default_factory=dict)


@dataclass
class VideoResult:
    data: bytes
    mime_type: str
    model: str
    interaction_id: str = ''


# ---------------------------------------------------------------- helpers

def mime_for(path):
    suffix = Path(path).suffix.lower()
    return {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(suffix, '')


def extension_for(mime_type):
    return {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'video/mp4': '.mp4'}.get(mime_type, '.bin')


def load_image(path, role='object', label=''):
    """Read an image file for use as a reference; validates type and size."""
    path = Path(path)
    mime = mime_for(path)
    if not mime:
        raise ValueError(f'Desteklenmeyen görsel türü: {path.name} (PNG, JPEG ya da WEBP seçin).')
    data = path.read_bytes()
    _check_image(data, mime, path.name)
    return ImageInput(data, mime, role, label or path.stem)


def _check_image(data, mime, name='görsel'):
    if mime not in IMAGE_MIME_TYPES:
        raise ValueError(f'{name}: desteklenmeyen görsel türü ({mime}).')
    if not data:
        raise ValueError(f'{name}: görsel dosyası boş.')
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f'{name}: görsel çok büyük (en fazla {MAX_IMAGE_BYTES // (1024 * 1024)} MB).')


def _check_total(images):
    if sum(len(i.data) for i in images) > MAX_INLINE_TOTAL:
        raise ValueError(f'Referans görsellerin toplamı çok büyük (en fazla {MAX_INLINE_TOTAL // (1024 * 1024)} MB).')


def _endpoint(path, key):
    url = f'{API_BASE}/{path}'
    headers = {'Content-Type': 'application/json'}
    if KEY_IN_QUERY:
        url += ('&' if '?' in url else '?') + 'key=' + quote(key, safe='')
    else:
        headers['x-goog-api-key'] = key
    return url, headers


def _model_url(model, key):
    return _endpoint('models/' + quote(model, safe='') + ':generateContent', key)


def _clean(text, key):
    text = _scrub(str(text), {'x-goog-api-key': key})
    return text.replace(key, '***') if key and len(key) >= 4 else text


def _send(url, headers, body, key, *, transport, opener, timeout, backoff=None, retry_timeout=True, sleep=None):
    """One request; error text never contains the key, whatever the transport raised."""
    try:
        if transport is not None:
            result = transport(url, headers, body)
        else:
            if opener is None:  # a real request: the sidebar lists what leaves the computer
                from akis import privacy_log
                privacy_log.note(PROVIDER, 'story')
            kwargs = {'opener': opener, 'retry_timeout': retry_timeout, 'sleep': sleep}
            if backoff is not None:
                kwargs['backoff'] = backoff
            result = post_json(PROVIDER, url, json.dumps(body).encode('utf-8'), headers, timeout, **kwargs)
    except ResponseTruncatedError as exc:
        raise ResponseTruncatedError(_clean(exc, key), exc.partial) from exc
    except ProviderHTTPError as exc:
        raise type(exc)(_clean(exc, key), exc.code) from exc
    except (ProviderResponseError, ValueError) as exc:
        raise type(exc)(_clean(exc, key)) from exc
    except RuntimeError as exc:
        raise RuntimeError(_clean(exc, key)) from exc
    if not isinstance(result, dict):
        raise ProviderResponseError(f'{PROVIDER} beklenmeyen bir yanıt döndürdü; daha sonra tekrar deneyin.')
    return result


def _usage(result):
    meta = result.get('usageMetadata') or {}
    return {'prompt': int(meta.get('promptTokenCount') or 0),
            'output': int(meta.get('candidatesTokenCount') or 0),
            'thoughts': int(meta.get('thoughtsTokenCount') or 0),
            'cached': int(meta.get('cachedContentTokenCount') or 0),
            'total': int(meta.get('totalTokenCount') or 0)}


def _blocked(why=''):
    return ResponseBlockedError(f'{PROVIDER} bu isteği güvenlik/içerik politikası nedeniyle engelledi'
                                + (f' ({why})' if why else '') + '. İsteği farklı ifade edip tekrar deneyin.')


def _candidate(result):
    feedback = result.get('promptFeedback') or {}
    if feedback.get('blockReason'):
        raise _blocked(feedback['blockReason'])
    candidates = result.get('candidates') or []
    if not candidates or not isinstance(candidates[0], dict):
        raise EmptyResponseError(f'{PROVIDER} boş yanıt döndürdü. Tekrar deneyin ya da başka bir model seçin.')
    candidate = candidates[0]
    parts = [p for p in (candidate.get('content') or {}).get('parts') or [] if isinstance(p, dict) and not p.get('thought')]
    return candidate, parts, candidate.get('finishReason') or ''


# ---------------------------------------------------------------- text

def text_body(prompt, *, system_instruction=None, history=(), thinking_level='medium',
              max_output_tokens=8192, stop_sequences=None):
    """Request body. ``prompt`` is a string or a list of strings (one user turn, several parts: put the
    stable material first so implicit caching can reuse the prefix). ``history``: [(role, text)] before it."""
    if thinking_level not in THINKING_LEVELS:
        raise ValueError(f'Geçersiz düşünme düzeyi: {thinking_level} (low, medium ya da high).')
    if not 1 <= int(max_output_tokens) <= MAX_OUTPUT_TOKENS:
        raise ValueError(f'Çıktı sınırı 1 ile {MAX_OUTPUT_TOKENS} token arasında olmalı.')
    parts = [prompt] if isinstance(prompt, str) else list(prompt)
    parts = [p for p in parts if p]
    if not parts:
        raise ValueError('İstek metni boş olamaz.')
    contents = []
    for role, text in history:
        if role not in ('user', 'model'):
            raise ValueError(f'Geçersiz rol: {role}')
        contents.append({'role': role, 'parts': [{'text': text}]})
    contents.append({'role': 'user', 'parts': [{'text': p} for p in parts]})
    config = {'maxOutputTokens': int(max_output_tokens), 'thinkingConfig': {'thinkingLevel': thinking_level}}
    if stop_sequences:
        config['stopSequences'] = list(stop_sequences)
    body = {}
    if system_instruction:
        body['system_instruction'] = {'parts': [{'text': system_instruction}]}
    body['contents'] = contents
    body['generationConfig'] = config
    return body


def parse_text(result, model=''):
    candidate, parts, finish = _candidate(result)
    text = ''.join(p.get('text', '') for p in parts)
    usage = _usage(result)
    if finish in _BLOCKED:
        raise _blocked(finish)
    if finish == 'MAX_TOKENS':
        raise ResponseTruncatedError(f'{PROVIDER} yanıtı çıktı sınırına takıldı ve yarıda kesildi '
                                     '(düşünme tokenları da bu sınıra dahildir).', text)
    if not text.strip():
        raise EmptyResponseError(f'{PROVIDER} boş yanıt döndürdü. Tekrar deneyin ya da başka bir model seçin.')
    return TextResult(text, model, usage, finish)


def fallback_chain(model, fallbacks=None):
    """[model, *fallbacks] without duplicates; ``fallbacks=None`` uses GEMINI_TEXT_FALLBACKS, () disables."""
    extra = GEMINI_TEXT_FALLBACKS.get(model, ()) if fallbacks is None else fallbacks
    chain = [model]
    for item in extra:
        if item and item not in chain:
            chain.append(item)
    return chain


def _fallback_reason(model, exc):
    if isinstance(exc, FreeTierUnavailableError):
        why = 'ücretsiz katmanda kullanılamıyor'
    elif isinstance(exc, ProviderHTTPError):
        why = {404: 'bulunamadı', 429: 'istek sınırına takıldı'}.get(exc.code, f'yoğun (HTTP {exc.code})')
    else:
        why = 'zamanında yanıt vermedi'
    return f'{model} {why}'


def _with_tried(exc, reasons):
    """The same error type with the skipped models appended to its message."""
    message = f'{exc}\n(Önce denenen: {"; ".join(reasons)})'
    try:
        if isinstance(exc, ProviderHTTPError):
            return type(exc)(message, exc.code)
        if isinstance(exc, ResponseTruncatedError):
            return type(exc)(message, exc.partial)
        return type(exc)(message)
    except TypeError:
        return exc


def generate_text(key, model, prompt, *, system_instruction=None, history=(), thinking_level='medium',
                  max_output_tokens=8192, stop_sequences=None, fallbacks=None, transport=None, opener=None,
                  sleep=None, timeout=TEXT_TIMEOUT):
    """generateContent for text. No temperature/top_p/top_k (ignored and deprecated on Gemini 3.6+/4).

    When the model is overloaded (5xx/429), missing (404), timed out or not on this tier, the next model of
    ``fallback_chain`` is tried; ``TextResult.model`` names the model that answered and ``fallback_reason``
    says why others were skipped. Blocked/truncated/empty answers and 400/401/403 never fall back.
    Raises ResponseBlockedError / ResponseTruncatedError (``partial``) / EmptyResponseError / RuntimeError."""
    if not key or not model:
        raise ValueError('API anahtarı ve model gereklidir.')
    body = text_body(prompt, system_instruction=system_instruction, history=history, thinking_level=thinking_level,
                     max_output_tokens=max_output_tokens, stop_sequences=stop_sequences)
    chain = fallback_chain(model, fallbacks)
    reasons = []
    for index, candidate in enumerate(chain):
        last = index == len(chain) - 1
        url, headers = _model_url(candidate, key)
        try:
            # With a next model waiting, a timeout moves on at once instead of waiting a second time.
            result = _send(url, headers, body, key, transport=transport, opener=opener, timeout=timeout,
                           backoff=TEXT_BACKOFF, retry_timeout=last, sleep=sleep)
        except Exception as exc:
            if last or not is_fallback_error(exc):
                if reasons:
                    raise _with_tried(exc, reasons) from exc
                raise
            reasons.append(_fallback_reason(candidate, exc))
            continue
        parsed = parse_text(result, candidate)
        parsed.requested_model = model
        parsed.fallback_reason = '; '.join(reasons)
        return parsed


def list_models(key, *, getter=None, timeout=30):
    """Model ids this key can see (GET /models, names are "models/<id>"), following nextPageToken."""
    if not key:
        raise ValueError('API anahtarı gereklidir.')
    getter = getter or _http_get
    found, token = [], ''
    for _ in range(20):
        url, headers = _endpoint('models?pageSize=200' + (f'&pageToken={quote(token, safe="")}' if token else ''), key)
        headers.pop('Content-Type', None)
        try:
            payload = json.loads(getter(url, headers, timeout).decode('utf-8'))
        except HTTPError as exc:
            detail = _clean(_http_detail(exc), key)
            hint = _http_hint(PROVIDER, exc.code, detail)
            if exc.code == 400 and 'api key' in detail.lower():  # Google answers a bad key with 400
                hint = _http_hint(PROVIDER, 401, detail)
            message = f'{PROVIDER} model listesi alınamadı: HTTP {exc.code}' + (f' — {detail}' if detail else '')
            raise ProviderHTTPError(message + (f'\n{hint}' if hint else ''), exc.code) from exc
        except (URLError, OSError, ValueError) as exc:
            raise RuntimeError(_clean(f'{PROVIDER} model listesi alınamadı: {exc}', key)) from exc
        for item in payload.get('models') or []:
            name = str(item.get('name') or '') if isinstance(item, dict) else ''
            if name:
                found.append(name.removeprefix('models/'))
        token = payload.get('nextPageToken') or ''
        if not token:
            break
    return found


# ---------------------------------------------------------------- image

def describe_references(references):
    """English lines stating each reference image's purpose, in the order the images are sent."""
    purpose = {'character': 'character identity reference (keep face, hair, build and outfit consistent)',
               'style': 'style reference (match palette, rendering and mood only, not its content)',
               'pose': 'pose and composition reference',
               'object': 'object/setting reference'}
    lines = []
    for index, ref in enumerate(references, 1):
        text = purpose.get(ref.role, purpose['object'])
        lines.append(f'Image {index}: {text}' + (f' for "{ref.label}"' if ref.label else '') + '.')
    return 'Reference images, in order:\n' + '\n'.join(lines) if lines else ''


def validate_image_request(model, prompt, references, aspect_ratio, image_size):
    if not (prompt or '').strip():
        raise ValueError('Görsel istemi boş olamaz.')
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(f'Geçersiz en-boy oranı: {aspect_ratio}. Geçerli değerler: {", ".join(ASPECT_RATIOS)}.')
    if image_size == '512':
        if model not in SIZE_512_MODELS:
            raise ValueError('"512" boyutu yalnızca gemini-3.1-flash-image modelinde kullanılabilir.')
    elif image_size not in IMAGE_SIZES:
        raise ValueError(f'Geçersiz görsel boyutu: {image_size} (1K, 2K ya da 4K; büyük K harfiyle).')
    references = list(references or ())
    if len(references) > MAX_REFERENCES:
        raise ValueError(f'En fazla {MAX_REFERENCES} referans görsel gönderilebilir.')
    characters = sum(1 for r in references if r.role == 'character')
    if characters > MAX_CHARACTER_REFERENCES:
        raise ValueError(f'En fazla {MAX_CHARACTER_REFERENCES} karakter referansı gönderilebilir.')
    if len(references) - characters > MAX_OBJECT_REFERENCES:
        raise ValueError(f'En fazla {MAX_OBJECT_REFERENCES} nesne/stil referansı gönderilebilir.')
    for index, ref in enumerate(references, 1):
        _check_image(ref.data, ref.mime_type, f'{index}. referans')
    _check_total(references)
    return references


def image_body(prompt, references=(), *, aspect_ratio='16:9', image_size='1K', annotate_references=True):
    text = prompt.strip()
    note = describe_references(references) if annotate_references else ''
    if note:
        text += '\n\n' + note
    parts = [{'text': text}]
    for ref in references:
        parts.append({'inline_data': {'mime_type': ref.mime_type, 'data': base64.b64encode(ref.data).decode('ascii')}})
    return {'contents': [{'parts': parts}],
            'generationConfig': {'responseModalities': ['IMAGE'],
                                 'imageConfig': {'aspectRatio': aspect_ratio, 'imageSize': image_size}}}


def parse_image(result, model=''):
    candidate, parts, finish = _candidate(result)
    images, texts = [], []
    for part in parts:
        inline = part.get('inlineData') or part.get('inline_data')
        if isinstance(inline, dict) and inline.get('data'):
            mime = inline.get('mimeType') or inline.get('mime_type') or 'image/png'
            try:
                images.append((base64.b64decode(inline['data']), mime))
            except (ValueError, TypeError) as exc:
                raise ProviderResponseError(f'{PROVIDER} bozuk görsel verisi döndürdü.') from exc
        elif part.get('text'):
            texts.append(part['text'])
    note = ' '.join(texts).strip()[:200]
    if not images:
        if finish in _BLOCKED:
            raise _blocked(finish)
        if finish == 'MAX_TOKENS':
            raise ResponseTruncatedError(f'{PROVIDER} görseli tamamlayamadı (çıktı sınırı).', note)
        raise EmptyResponseError(f'{PROVIDER} görsel döndürmedi' + (f' (finishReason: {finish})' if finish else '')
                                 + (f': {note}' if note else '') + '. İstemi değiştirip tekrar deneyin.')
    data, mime = images[0]
    return ImageResult(data, mime, model, note, _usage(result))


def generate_image(key, model, prompt, *, references=(), aspect_ratio='16:9', image_size='1K',
                   annotate_references=True, transport=None, opener=None, timeout=IMAGE_TIMEOUT):
    """Nano Banana image generation: text part first, then the reference images in order.
    Busy (429/5xx) answers are retried by post_json; a timed-out request is not (it could be billed twice)."""
    if not key or not model:
        raise ValueError('API anahtarı ve model gereklidir.')
    references = validate_image_request(model, prompt, references, aspect_ratio, image_size)
    body = image_body(prompt, references, aspect_ratio=aspect_ratio, image_size=image_size,
                      annotate_references=annotate_references)
    url, headers = _model_url(model, key)
    try:
        result = _send(url, headers, body, key, transport=transport, opener=opener, timeout=timeout,
                       retry_timeout=False)
    except RuntimeError as exc:
        if _timed_out(exc):
            raise ProviderResponseError(f'{PROVIDER} {timeout} saniyede görsel döndürmedi. Tekrar denemeden önce '
                                        'birkaç dakika bekleyin.') from exc
        raise
    return parse_image(result, model)


# ---------------------------------------------------------------- video

def _timed_out(exc):
    seen = exc
    while seen is not None:
        if isinstance(seen, (TimeoutError,)) or isinstance(getattr(seen, 'reason', None), TimeoutError):
            return True
        seen = seen.__cause__
    return False


def validate_video_request(prompt, images, aspect_ratio, resolution, duration, first_last):
    if not (prompt or '').strip():
        raise ValueError('Video istemi boş olamaz.')
    if aspect_ratio not in VIDEO_ASPECTS:
        raise ValueError('Video için en-boy oranı 16:9 ya da 9:16 olmalı.')
    if resolution not in VIDEO_RESOLUTIONS:
        raise ValueError(f'Geçersiz çözünürlük: {resolution} ({", ".join(VIDEO_RESOLUTIONS)}).')
    if isinstance(duration, bool) or not isinstance(duration, int) or not VIDEO_MIN_SECONDS <= duration <= VIDEO_MAX_SECONDS:
        raise ValueError(f'Video süresi {VIDEO_MIN_SECONDS}–{VIDEO_MAX_SECONDS} arası tam saniye olmalı.')
    images = list(images or ())
    if len(images) > VIDEO_MAX_IMAGES:
        raise ValueError(f'Videoya en fazla {VIDEO_MAX_IMAGES} görsel eklenebilir.')
    if first_last:
        if len(images) != 2:
            raise ValueError('İlk ve son kare modu tam iki görsel ister.')
        if duration > VIDEO_FIRST_LAST_MAX:
            raise ValueError(f'İlk/son kare modunda süre en fazla {VIDEO_FIRST_LAST_MAX} saniye olabilir.')
    for index, image in enumerate(images, 1):
        _check_image(image.data, image.mime_type, f'{index}. görsel')
    _check_total(images)
    return images


def video_body(prompt, images=(), *, model=VIDEO_MODELS[0], aspect_ratio='16:9', resolution='720p',
               duration=8, delivery='inline'):
    if images:
        payload = [{'type': 'image', 'data': base64.b64encode(i.data).decode('ascii'), 'mime_type': i.mime_type}
                   for i in images]
        payload.append({'type': 'text', 'text': prompt.strip()})
    else:
        payload = prompt.strip()
    response_format = {'type': 'video', 'aspect_ratio': aspect_ratio, 'resolution': resolution, 'duration': f'{duration}s'}
    if delivery == 'uri':
        response_format['delivery'] = 'uri'
    return {'model': model, 'input': payload, 'response_format': response_format}


def _video_parts(result):
    for step in result.get('steps') or []:
        if isinstance(step, dict) and step.get('type') == 'model_output':
            for item in step.get('content') or []:
                if isinstance(item, dict):
                    yield item


def parse_video(result, model=''):
    """Returns (VideoResult | None, uri | None)."""
    status = result.get('status') or ''
    if status in ('failed', 'cancelled', 'incomplete'):
        error = result.get('error') or {}
        message = str(error.get('message', '') if isinstance(error, dict) else error)[:300]
        if re.search(r'safety|policy|blocked|prohibited', message, re.I):
            raise _blocked(message)
        raise ProviderResponseError(f'{PROVIDER} video üretemedi ({status})' + (f': {message}' if message else '') + '.')
    texts = []
    for item in _video_parts(result):
        if item.get('type') == 'video':
            mime = item.get('mime_type') or item.get('mimeType') or 'video/mp4'
            if item.get('data'):
                try:
                    data = base64.b64decode(item['data'])
                except (ValueError, TypeError) as exc:
                    raise ProviderResponseError(f'{PROVIDER} bozuk video verisi döndürdü.') from exc
                return VideoResult(data, mime, model, str(result.get('id') or '')), None
            if item.get('uri'):
                return None, str(item['uri'])
        elif item.get('type') == 'text' and item.get('text'):
            texts.append(item['text'])
    note = ' '.join(texts).strip()[:200]
    raise ResponseBlockedError(f'{PROVIDER} video döndürmedi' + (f' ({note})' if note else '') + '. Bu genellikle içerik '
                               'engeli ya da bölgesel kısıtlama demektir; istemi değiştirip tekrar deneyin.')


def _http_get(url, headers, timeout):
    with urlopen(Request(url, headers=headers, method='GET'), timeout=timeout) as response:
        return response.read()


def _download_file(uri, key, *, getter, sleep, timeout, poll_seconds=FILE_POLL_SECONDS, poll_limit=FILE_POLL_LIMIT):
    """URI delivery (unverified against the live API): wait for the file to be ACTIVE, then download it."""
    found = re.search(r'files/([A-Za-z0-9_\-]+)', uri)
    if not found:
        raise ProviderResponseError(f'{PROVIDER} tanınmayan bir video adresi döndürdü.')
    file_id = found.group(1)
    status_url, headers = _endpoint(f'files/{file_id}', key)
    headers.pop('Content-Type', None)
    waited = 0
    try:
        while True:
            info = json.loads(getter(status_url, headers, timeout).decode('utf-8'))
            state = str(info.get('state') or '')
            if state == 'ACTIVE':
                break
            if state == 'FAILED':
                raise ProviderResponseError(f'{PROVIDER} video dosyasını hazırlayamadı.')
            if waited >= poll_limit:
                raise ProviderResponseError(f'{PROVIDER} video dosyası {poll_limit} saniyede hazır olmadı.')
            sleep(poll_seconds)
            waited += poll_seconds
        download_url, headers = _endpoint(f'files/{file_id}:download?alt=media', key)
        headers.pop('Content-Type', None)
        return getter(download_url, headers, timeout)
    except ProviderResponseError:
        raise
    except HTTPError as exc:
        raise RuntimeError(f'{PROVIDER} video dosyası indirilemedi: HTTP {exc.code}') from exc
    except (URLError, OSError, ValueError) as exc:
        raise RuntimeError(_clean(f'{PROVIDER} video dosyası indirilemedi: {exc}', key)) from exc


def generate_video(key, prompt, *, model=VIDEO_MODELS[0], images=(), first_last=False, aspect_ratio='16:9',
                   resolution='720p', duration=8, delivery='inline', transport=None, opener=None,
                   getter=None, sleep=None, timeout=VIDEO_TIMEOUT):
    """Gemini Omni Flash via the Interactions API. ``images`` go first (one image: image-to-video; two with
    ``first_last``: first and last frame). Never retried: not on busy answers, not on timeouts."""
    if not key or not model:
        raise ValueError('API anahtarı ve model gereklidir.')
    if delivery not in ('inline', 'uri'):
        raise ValueError('delivery "inline" ya da "uri" olmalı.')
    images = validate_video_request(prompt, images, aspect_ratio, resolution, duration, first_last)
    body = video_body(prompt, images, model=model, aspect_ratio=aspect_ratio, resolution=resolution,
                      duration=duration, delivery=delivery)
    url, headers = _endpoint('interactions', key)
    try:
        result = _send(url, headers, body, key, transport=transport, opener=opener, timeout=timeout, backoff=())
    except RuntimeError as exc:
        if _timed_out(exc):
            raise VideoTimeoutError(f'Video {timeout} saniyede tamamlanmadı. Ücretlendirilmiş olabileceği için otomatik '
                                    'olarak tekrar denenmedi; Google AI Studio kullanımınızı kontrol edip sonra tekrar deneyin.') from exc
        raise
    video, uri = parse_video(result, model)
    if video is not None:
        return video
    data = _download_file(uri, key, getter=getter or _http_get, sleep=sleep or time.sleep, timeout=min(timeout, 300))
    if not data:
        raise EmptyResponseError(f'{PROVIDER} boş video dosyası döndürdü.')
    return VideoResult(data, 'video/mp4', model, str(result.get('id') or ''))
