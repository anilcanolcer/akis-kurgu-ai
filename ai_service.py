"""Planning validation and optional local transcription services."""
import json
import math


def plan_prompt(goal, platform, tempo, style, focus):
    return f'Hedef: {goal}\nPlatform: {platform}\nTempo: {tempo}\nStil: {style}\nOdak: {focus}'


def parse_suggestions(text, duration):
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        raise ValueError('AI yanıtında geçerli JSON bulunamadı.')
    data = json.loads(text[start:end + 1])
    plans = data.get('suggestions')
    if not isinstance(plans, list) or len(plans) < 2:
        raise ValueError('AI en az iki öneri döndürmelidir.')
    result = []
    for item in plans[:3]:
        if not isinstance(item, dict):
            raise ValueError('Geçersiz öneri.')
        a, b = float(item.get('trim_start', 0)), float(item.get('trim_end', duration))
        if not math.isfinite(a) or not math.isfinite(b) or not 0 <= a < b <= duration:
            raise ValueError('Önerinin zaman aralığı video dışında.')
        result.append(dict(item, trim_start=a, trim_end=b))
    return result


def add_plan_markers(timeline, plan):
    fps = timeline.fps_num / timeline.fps_den
    for label, seconds in [('Başlangıç', plan['trim_start']), ('Bitiş', plan['trim_end'])]:
        timeline.markers.append({'frame': round(seconds * fps), 'label': f"AI: {label} — {plan.get('title', '')}"})


def local_transcribe(path, model_name, *, download=False, model_factory=None):
    if model_factory is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError('Yerel altyazı için faster-whisper kurulmalı: pip install -r requirements-local-ai.txt') from exc
        model_factory = WhisperModel
    model = model_factory(model_name, device='cpu', compute_type='int8', local_files_only=not download)
    segments, _ = model.transcribe(str(path), language='tr', vad_filter=True)
    return ' '.join(segment.text.strip() for segment in segments).strip()
