"""Planning validation and optional local transcription services."""
import json
import math
import re


def plan_prompt(goal, platform, tempo, style, focus):
    return f'Hedef: {goal}\nPlatform: {platform}\nTempo: {tempo}\nStil: {style}\nOdak: {focus}'


def _json_values(text):
    """Yield JSON objects/arrays found in text: the whole text first, then each embedded value (code fences and prose allowed)."""
    text = (text or '').strip()
    fenced = re.findall(r'```(?:json|JSON)?\s*(.*?)```', text, re.DOTALL)
    candidates = [*fenced, text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            yield json.loads(candidate)
            continue
        except ValueError:
            pass
        for match in re.finditer(r'[{\[]', candidate):
            try:
                value, _ = decoder.raw_decode(candidate, match.start())
            except ValueError:
                continue
            if isinstance(value, (dict, list)):
                yield value


def _seconds(item, name, default):
    value = item.get(name, default)
    if value is None:
        value = default
    if isinstance(value, bool):
        raise ValueError(f'Önerideki "{name}" değeri sayı değil.')
    try:
        return float(str(value).strip().removesuffix('s').strip().replace(',', '.')) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        raise ValueError(f'Önerideki "{name}" değeri sayı değil: {str(value)[:40]}') from None


MIN_SUGGESTION_SECONDS = 0.5
FILTERS = ('natural', 'vivid', 'cinematic')


def _text(value):
    return value.strip() if isinstance(value, str) else ('' if value is None else str(value).strip())


def _text_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r'[\n,;]+', value) if value.strip() else []
    if not isinstance(value, (list, tuple)):
        value = [value]
    return [text for text in (_text(v) for v in value if not isinstance(v, (dict, list))) if text]


def _hashtags(value):
    seen, result = set(), []
    for raw in _text_list(value):
        for part in raw.split():
            tag = part.lstrip('#').strip()
            if tag and tag.casefold() not in seen:
                seen.add(tag.casefold())
                result.append(tag)
    return result


def _normalise_suggestion(item, duration):
    """One tolerant, normalised suggestion or None when unusable."""
    if not isinstance(item, dict):
        return None
    try:
        a = _seconds(item, 'trim_start', 0)
        b = _seconds(item, 'trim_end', duration)
    except ValueError:
        return None
    if not math.isfinite(a):
        return None
    if not math.isfinite(b) or b <= 0:
        b = duration
    a = min(max(a, 0.0), duration)
    b = min(max(b, 0.0), duration)
    if b < a:
        a, b = b, a
    if b - a < MIN_SUGGESTION_SECONDS:
        return None
    filter_name = _text(item.get('filter')).casefold()
    return dict(item, trim_start=a, trim_end=b,
                title=_text(item.get('title')), summary=_text(item.get('summary')),
                caption=_text(item.get('caption')), pacing=_text(item.get('pacing')),
                hashtags=_hashtags(item.get('hashtags')), notes=_text_list(item.get('notes')),
                filter=filter_name if filter_name in FILTERS else 'natural')


def parse_suggestions(text, duration):
    """Tolerantly read the 'suggestions' answer (code fences, prose and a top-level list allowed).

    Each suggestion is clamped into the video; unusable ones are dropped. Fails only when none is usable."""
    plans = found = None
    for data in _json_values(text if isinstance(text, str) else ''):
        found = True
        if isinstance(data, dict) and isinstance(data.get('suggestions'), list):
            plans = data['suggestions']
        elif isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
            plans = data
        if plans is not None:
            break
    if not found:
        raise ValueError('AI yanıtında geçerli JSON bulunamadı.')
    result = [] if not isinstance(plans, list) else [p for p in (_normalise_suggestion(i, duration) for i in plans) if p]
    if not result:
        raise ValueError('AI kullanılabilir bir öneri döndürmedi; lütfen tekrar deneyin.')
    return result[:3]


def _clock(seconds):
    total = int(round(seconds))
    return f'{total // 60}:{total % 60:02d}'


def format_suggestion(plan):
    """Readable Turkish summary of one suggestion."""
    start, end = float(plan.get('trim_start', 0)), float(plan.get('trim_end', 0))
    lines = []
    title = _text(plan.get('title'))
    if title:
        lines += [title, '']
    if _text(plan.get('summary')):
        lines += [_text(plan.get('summary')), '']
    lines.append(f'Kesim: {_clock(start)} – {_clock(end)} ({round(end - start)} sn)')
    if _text(plan.get('pacing')):
        lines.append(f'Tempo: {_text(plan.get("pacing"))}')
    if _text(plan.get('filter')):
        lines.append(f'Filtre: {_text(plan.get("filter"))}')
    if _text(plan.get('caption')):
        lines += ['', 'Açıklama:', _text(plan.get('caption'))]
    tags = _hashtags(plan.get('hashtags'))
    if tags:
        lines += ['', 'Etiketler: ' + ' '.join('#' + t for t in tags)]
    notes = _text_list(plan.get('notes'))
    if notes:
        lines += ['', 'Notlar:'] + [f'• {n}' for n in notes]
    return '\n'.join(lines).strip()


def add_plan_markers(timeline, plan):
    fps = timeline.fps_num / timeline.fps_den
    for label, seconds in [('Başlangıç', plan['trim_start']), ('Bitiş', plan['trim_end'])]:
        timeline.markers.append({'frame': round(seconds * fps), 'label': f"AI: {label} — {plan.get('title', '')}"})


def local_transcribe(path, model_name, *, download=False, model_factory=None, timed=False,
                     language=None, vocabulary=None):
    """language / vocabulary default to the editor's speech settings (akis.speech_settings)."""
    from akis import speech_settings
    if model_factory is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError('Yerel altyazı için faster-whisper kurulmalı: pip install -r requirements-local-ai.txt') from exc
        model_factory = WhisperModel
    try:
        model = model_factory(model_name, device='cpu', compute_type='int8', local_files_only=not download)
    except FileNotFoundError as exc:
        if not download:
            raise RuntimeError(f'Yerel Whisper modeli ({model_name}) bulunamadı. İlk kullanımda internet bağlantısıyla “Modeli indir” seçeneğini işaretleyin. Ayrıntı: {exc}') from exc
        raise
    # initial_prompt is how Whisper is told which names and terms to expect; None leaves it out.
    segments, _ = model.transcribe(str(path), language=speech_settings.language(language), vad_filter=True,
                                   initial_prompt=speech_settings.vocabulary(vocabulary) or None)
    items = [{'start': segment.start, 'end': segment.end, 'text': segment.text.strip()} for segment in segments if segment.text.strip()]
    return items if timed else ' '.join(item['text'] for item in items)
