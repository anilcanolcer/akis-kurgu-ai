"""Provider-specific multimodal planning and credential storage."""
import base64
import json
import random
import re
import time
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROVIDERS = {
    'OpenAI': ('gpt-4o', 'gpt-5'),
    'Anthropic': ('claude-sonnet-5-5', 'claude-opus-5-5'),
    'xAI': ('grok-4.7', 'grok-4.6'),
    'Gemini': ('gemini-3.8-flash', 'gemini-4-argon', 'gemini-3.6-flash', 'gemini-flash-latest'),
    # Workers AI. Planning sends video frames, so only image-capable chat models are offered; any other
    # model id from the Cloudflare catalogue can be typed in.
    # These four answered a request with a video frame on the free plan (checked 2026-11-11).
    'Cloudflare': ('@cf/meta/llama-4-scout-17b-16e-instruct', '@cf/mistralai/mistral-small-3.1-24b-instruct',
                   '@cf/qwen/qwen3.8-27b', '@cf/google/gemma-4-26b-a4b-it'),
}
CLOUDFLARE_KEY_HINT = 'HESAP_KİMLİĞİ:API_ANAHTARI'
CLOUDFLARE_MAX_TOKENS = 8192


def cloudflare_credentials(key):
    """Split the Cloudflare key field into (account id, API token).

    Workers AI addresses every call to an account, and a Workers AI token usually cannot list accounts,
    so the 32-character account id is entered together with the token as ACCOUNT_ID:TOKEN.
    """
    account, separator, token = str(key or '').strip().partition(':')
    account, token = account.strip(), token.strip()
    if not separator or not token or not re.fullmatch(r'[0-9a-fA-F]{32}', account):
        raise ValueError('Cloudflare için anahtarı "Hesap Kimliği:API anahtarı" biçiminde girin. Hesap kimliği '
                         '(Account ID) Cloudflare panelinde Workers AI sayfasında yazan 32 karakterlik değerdir.')
    return account.lower(), token
# Text models tried in order when the chosen one is overloaded, missing, timed out or not on this tier.
# Never used for image or video (each attempt there costs money).
GEMINI_TEXT_FALLBACKS = {
    'gemini-4-argon': ('gemini-3.8-flash', 'gemini-3.6-flash'),
    'gemini-4-carbon': ('gemini-3.8-flash', 'gemini-3.6-flash'),
    'gemini-3.8-flash': ('gemini-3.6-flash',),
}
GEMINI_PLAN_THINKING = 'medium'   # planning needs real reasoning about timing, but not the slowest level
GEMINI_PLAN_MAX_TOKENS = 32768    # includes thinking tokens; the non-streaming cap
TRANSCRIPTION_MODELS = {'OpenAI': ('gpt-4o-mini-transcribe', 'gpt-4o-transcribe', 'whisper-1'), 'xAI': ('grok-voice-transcribe-2.0', 'grok-voice-transcribe-1.0'), 'Gemini': ('gemini-2.5-flash', 'gemini-2.5-pro')}

PLAN_TIMEOUT = 300           # image-heavy planning calls can take minutes
PLAN_DEADLINE = 2 * PLAN_TIMEOUT  # whole plan request, Gemini fallback chain and retries included
TRANSCRIBE_TIMEOUT = 180
ANTHROPIC_MAX_TOKENS = 16384
RETRY_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
BACKOFF = (4, 10)            # base waits between attempts; len + 1 attempts in total
MAX_WAIT = 60                # never wait longer than this for one retry (Retry-After included)


class ProviderResponseError(RuntimeError):
    """The provider answered, but not with usable text."""


class ResponseBlockedError(ProviderResponseError):
    """The request or the answer was blocked/refused by the provider's safety system."""


class ResponseTruncatedError(ProviderResponseError):
    """The answer hit the output token limit; ``partial`` holds what arrived."""

    def __init__(self, message, partial=''):
        super().__init__(message)
        self.partial = partial


class EmptyResponseError(ProviderResponseError):
    """The provider returned no text at all."""


class ProviderHTTPError(RuntimeError):
    """An HTTP failure after retries; ``code`` is the HTTP status."""

    def __init__(self, message, code=0):
        super().__init__(message)
        self.code = code


class FreeTierUnavailableError(ProviderHTTPError):
    """The model has a quota of 0 on this (free) tier: retrying is pointless."""


_FREE_TIER_ZERO = re.compile(r'limit:\s*0\b', re.I)
_FREE_TIER = re.compile(r'free[\s_-]*tier', re.I)


def is_free_tier_zero(detail):
    return bool(detail and _FREE_TIER_ZERO.search(detail) and _FREE_TIER.search(detail))


def is_fallback_error(exc):
    """Worth trying another text model: overloaded/busy, model missing, timed out, or not on this tier."""
    if isinstance(exc, FreeTierUnavailableError):
        return True
    if isinstance(exc, ProviderHTTPError):
        return exc.code in (404, 429, 500, 502, 503, 504, 529)
    seen = exc
    while seen is not None:
        if isinstance(seen, TimeoutError) or isinstance(getattr(seen, 'reason', None), TimeoutError):
            return True
        seen = seen.__cause__
    return False


_SECRET_HEADERS = ('authorization', 'x-api-key', 'x-goog-api-key', 'api-key')
_KEY_PATTERN = re.compile(r'(sk-[A-Za-z0-9_\-*]{6,}|xai-[A-Za-z0-9_\-*]{6,}|AIza[A-Za-z0-9_\-]{10,})')


def _scrub(text, headers):
    """Remove anything that looks like a credential from text shown to the user."""
    for name, value in (headers or {}).items():
        if name.lower() in _SECRET_HEADERS and value:
            secret = str(value)
            for part in {secret, secret.removeprefix('Bearer ').strip()}:
                if len(part) >= 4:
                    text = text.replace(part, '***')
    return _KEY_PATTERN.sub('***', text)


def _retry_after(headers):
    """Seconds requested by Retry-After / retry-after-ms, or None."""
    if not headers:
        return None
    try:
        found = {str(k).lower(): v for k, v in headers.items()}
        value = found.get('retry-after-ms')
        if value is not None:
            return max(0.0, float(value) / 1000)
        value = found.get('retry-after')
        if value is None:
            return None
        value = str(value).strip()
        try:
            return max(0.0, float(value))
        except ValueError:
            moment = parsedate_to_datetime(value)
            return max(0.0, moment.timestamp() - time.time())
    except Exception:
        return None


def _http_detail(exc):
    try:
        payload = json.loads(exc.read().decode('utf-8', 'replace'))
        error = payload.get('error', payload) if isinstance(payload, dict) else {}
        if isinstance(payload, dict) and isinstance(payload.get('errors'), list) and payload['errors']:
            error = payload['errors'][0]  # Cloudflare: {"errors": [{"message": ..., "code": ...}]}
        return str(error.get('message', '') if isinstance(error, dict) else error)[:300]
    except Exception:
        return ''


def _http_hint(provider, code, detail=''):
    if provider == 'Cloudflare' and code == 403 and 'plan' in detail.lower():
        return ('Bu model Cloudflare hesabınızın planında kullanılamıyor. Listeden başka bir model seçin ya da '
                'Cloudflare panelinden planınızı yükseltin.')
    if provider == 'Cloudflare' and code == 403:
        return ('Cloudflare bu modeli bu anahtarla çalıştırmadı: model planınızda olmayabilir, lisans onayı '
                'gerektirebilir ya da anahtarın Workers AI izni yoktur. Listeden başka bir model deneyin.')
    if code in (401, 403):
        return f'{provider} API anahtarı geçersiz ya da bu işlem için yetkisi yok. Ayarlardan anahtarı kontrol edin.'
    if code == 404:
        return f'Model bulunamadı ya da bu anahtarla kullanılamıyor. Listeden başka bir {provider} modeli seçin.'
    if code == 429:
        return 'İstek sınırına veya kotaya ulaşıldı. Birkaç dakika bekleyip tekrar deneyin ya da hesabınızın kota/ödeme durumunu kontrol edin.'
    if code in (500, 502, 503, 504, 529):
        return f'{provider} şu anda yoğun ya da geçici olarak hizmet veremiyor. Biraz sonra tekrar deneyin.'
    if code == 413:
        return 'İstek çok büyük; daha kısa ya da daha az video ile deneyin.'
    return ''


def _is_transient_connection_error(exc):
    reason = exc.reason if isinstance(exc, URLError) else exc
    return isinstance(reason, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError))


def _deadline_error(provider):
    return RuntimeError(f'{provider} izin verilen toplam sürede yanıt vermedi. Başka bir model deneyin veya tekrar deneyin.')


def post_json(provider, url, body, headers, timeout, *, opener=None, sleep=None, rand=None, backoff=BACKOFF,
              max_wait=MAX_WAIT, retry_timeout=True, deadline=None, clock=None):
    """POST and decode JSON.

    Busy/transient failures (408, 409, 429, 5xx, 529, dropped connections) are retried with exponential
    backoff and jitter, honouring Retry-After up to ``max_wait``; a timed-out attempt is retried once
    immediately unless ``retry_timeout`` is False. A 429 saying the model's free-tier limit is 0 is never
    retried (FreeTierUnavailableError). Failures carry a Turkish explanation and the provider's own message,
    never the key. ``sleep``/``rand`` are injectable; an injected ``sleep`` without ``rand`` means no jitter.
    ``deadline`` (a ``clock()`` / time.monotonic value) bounds all attempts and waits together: each attempt's
    timeout is cut to what is left, and a retry that would not fit is not started.
    """
    opener = opener or urlopen
    if rand is None:
        rand = random.random if sleep is None else (lambda: 0.0)
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    waits = list(backoff)
    timed_out = False

    def left():
        return None if deadline is None else deadline - clock()

    def wait(delay):
        remaining = left()
        if remaining is not None and delay >= remaining:
            return False
        sleep(delay)
        return True

    while True:
        remaining = left()
        if remaining is not None and remaining <= 0:
            raise _deadline_error(provider)
        attempt_timeout = timeout if remaining is None else max(1.0, min(timeout, remaining))
        try:
            with opener(Request(url, data=body, headers=headers, method='POST'), timeout=attempt_timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            raw_detail = _http_detail(exc) if exc.code == 429 else None
            if raw_detail is not None and is_free_tier_zero(raw_detail):
                detail = _scrub(raw_detail, headers)
                hint = ("Bu model ücretsiz katmanda kullanılamıyor; Google AI Studio'da faturalandırmayı etkinleştirin."
                        if provider == 'Gemini' else 'Bu model hesabınızın katmanında kullanılamıyor.')
                raise FreeTierUnavailableError(f'{hint}\n({provider} HTTP 429 — {detail})', 429) from exc
            if exc.code in RETRY_STATUS and waits:
                requested = _retry_after(exc.headers)
                base = waits.pop(0)
                if requested is None:
                    delay = min(max_wait, base + base * 0.25 * rand())
                elif requested <= max_wait:
                    delay = requested + 0.5 * rand()
                else:
                    delay = None  # Provider asks for a long pause (quota); report it instead of hanging.
                if delay is not None and wait(delay):
                    continue
            detail = _scrub(raw_detail if raw_detail is not None else _http_detail(exc), headers)
            hint = _http_hint(provider, exc.code, detail)
            message = f'{provider} API hatası: HTTP {exc.code}' + (f' — {detail}' if detail else '')
            raise ProviderHTTPError(message + (f'\n{hint}' if hint else ''), exc.code) from exc
        except (TimeoutError, URLError, ConnectionError) as exc:
            is_timeout = isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError)
            if is_timeout:
                if retry_timeout and not timed_out and waits:
                    timed_out = True  # The timeout itself was the wait; try once more straight away.
                    waits.pop(0)
                    continue
                seconds = attempt_timeout if deadline is None else round(attempt_timeout)
                raise RuntimeError(f'{provider} {seconds} saniyede yanıt vermedi. Başka bir model deneyin veya tekrar deneyin.') from exc
            if _is_transient_connection_error(exc) and waits:
                base = waits.pop(0)
                if wait(min(max_wait, base + base * 0.25 * rand())):
                    continue
            reason = _scrub(str(getattr(exc, 'reason', exc)), headers)
            raise RuntimeError(f'{provider} sunucusuna bağlanılamadı. İnternet bağlantınızı kontrol edin. ({reason})') from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError(f'{provider} beklenmeyen bir yanıt döndürdü; daha sonra tekrar deneyin.') from exc


def save_key(service, provider, key):
    import keyring
    keyring.set_password(service, provider.lower() + '_api_key', key)

def load_key(service, provider):
    import keyring
    return keyring.get_password(service, provider.lower() + '_api_key') or ''

def delete_key(service, provider):
    """Remove the stored key; a key that was never stored is not an error."""
    import keyring
    from keyring.errors import PasswordDeleteError
    try:
        keyring.delete_password(service, provider.lower() + '_api_key')
    except PasswordDeleteError:
        pass


def _label(at):
    """Frame label: callers may pass their own text (e.g. 'K1 @ 12.50s') or a plain second."""
    return at if isinstance(at, str) else f'{at:.2f}. saniye'


def _blocked(provider, why=''):
    return ResponseBlockedError(f'{provider} bu isteği güvenlik/içerik politikası nedeniyle engelledi veya yanıtlamayı reddetti'
                                + (f' ({why})' if why else '') + '. İsteği farklı ifade edip tekrar deneyin.')


def _truncated(provider, partial):
    return ResponseTruncatedError(f'{provider} yanıtı çıktı sınırına takıldı ve yarıda kesildi. '
                                  'Daha kısa bir istekle, daha az videoyla ya da başka bir modelle tekrar deneyin.', partial)


def _empty(provider, why=''):
    return EmptyResponseError(f'{provider} boş yanıt döndürdü' + (f' ({why})' if why else '') + '. Tekrar deneyin ya da başka bir model seçin.')


def _done(provider, text):
    if not text.strip():
        raise _empty(provider)
    return text


def _openai_text(provider, result):
    status = result.get('status')
    if status == 'failed':
        error = result.get('error') or {}
        raise ProviderResponseError(f'{provider} yanıt üretemedi: {error.get("message", "bilinmeyen hata") if isinstance(error, dict) else error}')
    texts, refusals = [], []
    for item in result.get('output') or []:
        for part in (item.get('content') or []) if isinstance(item, dict) else []:
            if part.get('type') == 'output_text':
                texts.append(part.get('text') or '')
            elif part.get('type') == 'refusal':
                refusals.append(part.get('refusal') or '')
    text = ''.join(texts)
    if status == 'incomplete':
        reason = (result.get('incomplete_details') or {}).get('reason', '')
        if reason == 'content_filter':
            raise _blocked(provider, 'içerik filtresi')
        raise _truncated(provider, text)
    if refusals and not text.strip():
        raise _blocked(provider, refusals[0][:200])
    return _done(provider, text)


def _anthropic_text(provider, result):
    text = ''.join(p.get('text', '') for p in result.get('content') or [] if isinstance(p, dict) and p.get('type') == 'text')
    stop = result.get('stop_reason')
    if stop == 'refusal':
        raise _blocked(provider)
    if stop == 'max_tokens':
        raise _truncated(provider, text)
    return _done(provider, text)


def _chat_text(provider, result):
    choices = result.get('choices') or []
    if not choices:
        raise _empty(provider)
    choice = choices[0] or {}
    message = choice.get('message') or {}
    content = message.get('content')
    if isinstance(content, list):  # some compatible APIs return content parts
        content = ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    content = content or ''
    finish = choice.get('finish_reason')
    if finish == 'content_filter':
        raise _blocked(provider, 'içerik filtresi')
    if message.get('refusal') and not content.strip():
        raise _blocked(provider, str(message['refusal'])[:200])
    if finish == 'length':
        raise _truncated(provider, content)
    return _done(provider, content)


_GEMINI_BLOCKED = {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'IMAGE_SAFETY'}


def _gemini_text(provider, result):
    feedback = result.get('promptFeedback') or {}
    if feedback.get('blockReason'):
        raise _blocked(provider, feedback['blockReason'])
    candidates = result.get('candidates') or []
    if not candidates:
        raise _empty(provider)
    candidate = candidates[0] or {}
    parts = (candidate.get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts if isinstance(p, dict) and not p.get('thought'))
    finish = candidate.get('finishReason')
    if finish in _GEMINI_BLOCKED:
        raise _blocked(provider, finish)
    if finish == 'MAX_TOKENS':
        raise _truncated(provider, text)
    return _done(provider, text)


def _read_text(reader, provider, result):
    """Run a response reader; an answer of an unexpected shape becomes a ProviderResponseError."""
    if not isinstance(result, dict):
        raise ProviderResponseError(f'{provider} beklenmeyen bir yanıt döndürdü; daha sonra tekrar deneyin.')
    try:
        return reader(provider, result)
    except ProviderResponseError:
        raise
    except (AttributeError, TypeError, KeyError, IndexError) as exc:
        raise ProviderResponseError(f'{provider} beklenmeyen biçimde bir yanıt döndürdü (yanıt okunamadı); '
                                    'daha sonra tekrar deneyin ya da başka bir model seçin.') from exc


class PlanText(str):
    """request_plan's answer: a plain str that also names the model that answered.

    ``requested_model`` is what the caller asked for; ``fallback_reason`` (Turkish) says why it was skipped
    when a Gemini fallback model answered instead, '' otherwise.
    """
    model = ''
    requested_model = ''
    fallback_reason = ''

    @property
    def fell_back(self):
        return bool(self.requested_model) and self.model != self.requested_model


def _plan_text(text, model, requested, reasons=()):
    out = PlanText(text)
    out.model, out.requested_model, out.fallback_reason = model, requested, '; '.join(reasons)
    return out


def fallback_note(text):
    """Turkish sentence saying a fallback model answered instead of the selected one, or ''."""
    if not getattr(text, 'fell_back', False):
        return ''
    why = f' ({text.fallback_reason})' if getattr(text, 'fallback_reason', '') else ''
    return f'Seçilen model {text.requested_model} yanıt vermediği için yedek model {text.model} kullanıldı{why}.'


def _skip_reason(model, exc):
    if isinstance(exc, FreeTierUnavailableError):
        why = 'ücretsiz katmanda kullanılamıyor'
    elif isinstance(exc, ProviderHTTPError):
        why = {404: 'bulunamadı', 429: 'istek sınırına takıldı'}.get(exc.code, f'yoğun (HTTP {exc.code})')
    else:
        why = 'zamanında yanıt vermedi'
    return f'{model} {why}'


def request_plan(provider, key, model, prompt, frames, transport=None, instruction=None, *, timeout=PLAN_TIMEOUT,
                 deadline=PLAN_DEADLINE):
    """Send ordered JPEG frames to the selected provider. transport enables isolated tests.

    frames: [(label, jpeg_bytes)] where label is a number of seconds or a ready-made text label.
    A timed-out plan request is not retried automatically (it would double the wait and maybe the cost);
    ``deadline`` seconds bound the whole call, Gemini's fallback chain and retries included.
    Returns a PlanText (a str; ``.model`` names the model that answered, see fallback_note).
    Raises ResponseBlockedError / ResponseTruncatedError / EmptyResponseError (all RuntimeError).
    """
    ends = None if deadline is None else time.monotonic() + deadline
    if provider not in PROVIDERS or not key or not model:
        raise ValueError('Sağlayıcı, API anahtarı ve model gereklidir.')
    if transport is None:  # a real request: the sidebar lists what leaves the computer
        from akis import privacy_log
        privacy_log.note(provider, 'frames' if frames else 'text')
    encoded = [(_label(at), base64.b64encode(data).decode('ascii')) for at, data in frames]
    instruction = instruction or 'Kısa video kurgusunda uzman, ölçülü ve pratik bir Türkçe kreatif direktörsün.'
    headers = {'Content-Type': 'application/json'}
    if provider == 'OpenAI':
        url = 'https://api.openai.com/v1/responses'
        headers['Authorization'] = 'Bearer ' + key
        content = [{'type': 'input_text', 'text': prompt}]
        for label, img in encoded:
            content.extend([{'type': 'input_text', 'text': label}, {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + img}])
        body = {'model': model, 'instructions': instruction, 'input': [{'role': 'user', 'content': content}]}
    elif provider == 'Anthropic':
        url = 'https://api.anthropic.com/v1/messages'
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
        content = [{'type': 'text', 'text': prompt}]
        for label, img in encoded:
            content.extend([{'type': 'text', 'text': label}, {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': img}}])
        body = {'model': model, 'max_tokens': ANTHROPIC_MAX_TOKENS, 'system': instruction, 'messages': [{'role': 'user', 'content': content}]}
    elif provider == 'xAI':
        url = 'https://api.x.ai/v1/chat/completions'
        headers['Authorization'] = 'Bearer ' + key
        content = [{'type': 'text', 'text': prompt}]
        for label, img in encoded:
            content.extend([{'type': 'text', 'text': label}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + img}}])
        body = {'model': model, 'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': content}]}
    elif provider == 'Cloudflare':
        account, token = cloudflare_credentials(key)
        # The OpenAI-compatible Workers AI endpoint; the model id (@cf/...) goes in the body.
        url = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions'
        headers['Authorization'] = 'Bearer ' + token
        content = [{'type': 'text', 'text': prompt}]
        for label, img in encoded:
            content.extend([{'type': 'text', 'text': label}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + img}}])
        body = {'model': model, 'max_tokens': CLOUDFLARE_MAX_TOKENS,
                'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': content}]}
    else:
        from urllib.parse import quote
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(model, safe='') + ':generateContent'
        headers['x-goog-api-key'] = key
        parts = [{'text': prompt}]
        for label, img in encoded:
            parts.extend([{'text': label}, {'inline_data': {'mime_type': 'image/jpeg', 'data': img}}])
        # No temperature/top_p/top_k: Gemini 3.6+/4 ignore them and warn. Thinking level is explicit
        # (the default spends many tokens) and the output cap leaves room for thinking + the JSON plan.
        body = {'systemInstruction': {'parts': [{'text': instruction}]}, 'contents': [{'role': 'user', 'parts': parts}],
                'generationConfig': {'maxOutputTokens': GEMINI_PLAN_MAX_TOKENS,
                                     'thinkingConfig': {'thinkingLevel': GEMINI_PLAN_THINKING}}}
        if model.startswith('gemini-2'):  # older models know thinkingBudget only
            del body['generationConfig']['thinkingConfig']
        chain = [model] + [m for m in GEMINI_TEXT_FALLBACKS.get(model, ()) if m != model]
        reasons = []
        for index, candidate in enumerate(chain):
            last = index == len(chain) - 1
            url = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(candidate, safe='') + ':generateContent'
            try:
                if ends is not None and time.monotonic() >= ends:
                    raise _deadline_error(provider)
                if transport:
                    result = transport(url, headers, body)
                else:
                    result = post_json(provider, url, json.dumps(body).encode(), headers, timeout,
                                       retry_timeout=False, deadline=ends)
                break
            except Exception as exc:
                if last or not is_fallback_error(exc) or (ends is not None and time.monotonic() >= ends):
                    raise
                reasons.append(_skip_reason(candidate, exc))
        return _plan_text(_read_text(_gemini_text, provider, result), candidate, model, reasons)
    if transport:
        result = transport(url, headers, body)
    else:
        result = post_json(provider, url, json.dumps(body).encode(), headers, timeout, retry_timeout=False,
                           deadline=ends)
    reader = {'OpenAI': _openai_text, 'Anthropic': _anthropic_text, 'xAI': _chat_text,
              'Cloudflare': _chat_text}.get(provider, _gemini_text)
    return _plan_text(_read_text(reader, provider, result), model, model)


def transcribe(provider, key, model, audio, *, language=None, vocabulary=None):
    """language / vocabulary default to the editor's speech settings (akis.speech_settings)."""
    from akis import speech_settings
    language, vocabulary = speech_settings.language(language), speech_settings.vocabulary(vocabulary)
    from akis import privacy_log
    privacy_log.note(provider, 'audio')
    if provider == 'OpenAI':
        return _openai_transcribe(key, model, audio, language=language, prompt=vocabulary)
    data = audio.read_bytes()
    if provider == 'Gemini':
        from urllib.parse import quote
        if len(data) > 14_000_000:
            raise ValueError('Gemini için ses dosyası çok büyük (en fazla 14 MB).')
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(model, safe='') + ':generateContent'
        body = json.dumps({'contents': [{'parts': [{'text': speech_settings.instruction(language, vocabulary)}, {'inline_data': {'mime_type': 'audio/mp3', 'data': base64.b64encode(data).decode('ascii')}}]}]}).encode()
        headers = {'Content-Type': 'application/json', 'x-goog-api-key': key}
    elif provider == 'xAI':
        import uuid
        boundary = 'akis' + uuid.uuid4().hex
        spoken = f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{language}\r\n' if language else ''
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'
                f'{spoken}'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        headers = {'Content-Type': 'multipart/form-data; boundary=' + boundary, 'Authorization': 'Bearer ' + key}
        url = 'https://api.x.ai/v1/stt'
    else:
        raise ValueError('Bu sağlayıcı için transkripsiyon desteklenmiyor.')
    result = post_json(provider, url, body, headers, TRANSCRIBE_TIMEOUT)
    if provider == 'xAI':
        return _read_text(_stt_text, provider, result)
    return _read_text(_gemini_text, provider, result)


class Transcript(str):
    """The recognised text; `segments` holds [{'start', 'end', 'text'}] in seconds when the service gave
    timings (None otherwise), so a cloud transcript can make captions like the local one."""

    def __new__(cls, text, segments=None):
        made = super().__new__(cls, text)
        made.segments = segments or None
        return made


def group_words(words, gap=0.7, longest=6.0, most=14):
    """Caption-sized segments from timed words: a new one after a sentence end, a pause, or when long."""
    segments, current = [], []
    for word in words or ():
        try:
            text, start = str(word['text']).strip(), float(word['start'])
            end = float(word.get('end', start))
        except (KeyError, TypeError, ValueError):
            continue
        if not text:
            continue
        if current and (start - current[-1][2] > gap or current[-1][0][-1:] in '.?!…'
                        or end - current[0][1] > longest or len(current) >= most):
            segments.append({'start': current[0][1], 'end': current[-1][2], 'text': ' '.join(w[0] for w in current)})
            current = []
        current.append((text, start, max(end, start)))
    if current:
        segments.append({'start': current[0][1], 'end': current[-1][2], 'text': ' '.join(w[0] for w in current)})
    return segments


def _stt_text(provider, result):
    text = result.get('text')
    if not isinstance(text, str) or not text.strip():
        raise _empty(provider, 'konuşma metni yok')
    return Transcript(text, group_words(result.get('words')))


def _openai_transcribe(key, model, audio, client_factory=None, *, language='tr', prompt=''):
    """OpenAI speech-to-text through the SDK, with the same timeout, retry limit and error texts as the
    raw-HTTP paths (the SDK's own default is 600 s and 2 retries, and its messages may quote the request)."""
    provider = 'OpenAI'
    import openai
    factory = client_factory or openai.OpenAI
    headers = {'Authorization': 'Bearer ' + key}
    try:
        client = factory(api_key=key, timeout=TRANSCRIBE_TIMEOUT, max_retries=1)
        with open(audio, 'rb') as handle:
            # A language left out lets the model detect it; the prompt lists names and terms to expect.
            options = {name: value for name, value in (('language', language), ('prompt', prompt)) if value}
            if model == 'whisper-1':  # the only OpenAI transcription model that gives timings
                options.update(response_format='verbose_json', timestamp_granularities=['segment'])
            result = client.audio.transcriptions.create(model=model, file=handle, **options)
    except openai.APITimeoutError as exc:
        raise RuntimeError(f'{provider} {TRANSCRIBE_TIMEOUT} saniyede yanıt vermedi. '
                           'Başka bir model deneyin veya tekrar deneyin.') from exc
    except openai.APIConnectionError as exc:
        raise RuntimeError(f'{provider} sunucusuna bağlanılamadı. İnternet bağlantınızı kontrol edin.') from exc
    except openai.APIStatusError as exc:
        code = getattr(exc, 'status_code', 0) or 0
        body = getattr(exc, 'body', None)
        error = body.get('error', body) if isinstance(body, dict) else body
        detail = str(error.get('message', '') if isinstance(error, dict) else (error or ''))[:300]
        detail = _scrub(detail, headers)
        hint = _http_hint(provider, code, detail)
        message = f'{provider} API hatası: HTTP {code}' + (f' — {detail}' if detail else '')
        raise ProviderHTTPError(message + (f'\n{hint}' if hint else ''), code) from exc
    except openai.OpenAIError as exc:
        raise RuntimeError(_scrub(f'{provider} transkripsiyon hatası: {exc}', headers)) from exc
    text = getattr(result, 'text', None)
    if not isinstance(text, str):
        raise ProviderResponseError(f'{provider} beklenmeyen bir yanıt döndürdü; daha sonra tekrar deneyin.')
    segments = []
    for segment in getattr(result, 'segments', None) or ():
        get = segment.get if isinstance(segment, dict) else (lambda name, s=segment: getattr(s, name, None))
        try:
            start, end, said = float(get('start')), float(get('end')), str(get('text') or '').strip()
        except (TypeError, ValueError):
            continue
        if said and end > start:
            segments.append({'start': start, 'end': end, 'text': said})
    return Transcript(text, segments)
