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


def parse_suggestions(text, duration):
    """Validate the older 'suggestions' answer. Tolerates code fences, surrounding prose and a top-level list."""
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
    if not isinstance(plans, list) or len(plans) < 2:
        raise ValueError('AI en az iki öneri döndürmelidir.')
    result = []
    for item in plans[:3]:
        if not isinstance(item, dict):
            raise ValueError('Geçersiz öneri.')
        a, b = _seconds(item, 'trim_start', 0), _seconds(item, 'trim_end', duration)
        if not math.isfinite(a) or not math.isfinite(b) or not 0 <= a < b <= duration:
            raise ValueError('Önerinin zaman aralığı video dışında.')
        result.append(dict(item, trim_start=a, trim_end=b))
    return result


def add_plan_markers(timeline, plan):
    fps = timeline.fps_num / timeline.fps_den
    for label, seconds in [('Başlangıç', plan['trim_start']), ('Bitiş', plan['trim_end'])]:
        timeline.markers.append({'frame': round(seconds * fps), 'label': f"AI: {label} — {plan.get('title', '')}"})


def local_transcribe(path, model_name, *, download=False, model_factory=None, timed=False):
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
    segments, _ = model.transcribe(str(path), language='tr', vad_filter=True)
    items = [{'start': segment.start, 'end': segment.end, 'text': segment.text.strip()} for segment in segments if segment.text.strip()]
    return items if timed else ' '.join(item['text'] for item in items)
