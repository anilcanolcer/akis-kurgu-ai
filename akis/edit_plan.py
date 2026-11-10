"""Prompt-driven editing: turn a model's JSON edit plan into real timeline changes.

The model never touches the timeline. It returns a small declarative plan; this
module validates it against the real media and builds a *new* Timeline, so the
previous one can be kept for undo. Everything here is pure and testable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from akis.caption_service import caption_track
from akis.shape_art import COLORS, SHAPES
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TEXT_COLORS, TEXT_SCALE, TRANSITIONS

ASPECTS = ('9:16', '16:9', '1:1', '4:5')
SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
MIN_SEGMENT_SECONDS = 0.2
TRANSITION_SECONDS = 0.35
MARK_TRACKS = 3

INSTRUCTION = (
    'Profesyonel bir video kurgucususun. Kullanıcının isteğini, verilen video analizine '
    'dayanarak uygulanabilir bir kurgu planına çevirirsin. Yalnızca geçerli JSON döndürürsün.'
)

SCHEMA = (
    '{"summary":"yapılan kurgunun bir iki cümlelik Türkçe özeti",'
    '"segments":[{"source":0,"start":0.0,"end":0.0,"transition":"fade"}],'
    '"texts":[{"start":0.0,"end":0.0,"text":"","x":0.5,"y":0.2,"size":"large","color":"yellow"}],'
    '"marks":[{"type":"circle","source":0,"start":0.0,"end":0.0,"x":0.5,"y":0.5,"size":0.3,"color":"red"},'
    '{"type":"arrow","source":0,"start":0.0,"end":0.0,"x":0.5,"y":0.5,"from_x":0.8,"from_y":0.3,"color":"yellow"}],'
    '"captions":false,'
    '"color":{"brightness":0,"contrast":0,"saturation":0},'
    '"speed":1.0,"aspect":"9:16","volume":1.0,'
    '"title":"","caption":"","hashtags":[""]}'
)

RULES = (
    'Kurallar:\n'
    '- "segments": çıktı videosunu SIRASIYLA oluşturan parçalar. "source" kaynak numarası, '
    '"start"/"end" o kaynağın kendi zamanında saniyedir. Listede olmayan her şey kesilir; '
    'sırayı değiştirerek parçaları yeniden dizebilirsin. Kesim istenmiyorsa bu alanı hiç yazma.\n'
    '- Kesimleri mümkünse sessizlik aralıklarına, cümle sonlarına veya sahne değişimlerine denk getir; '
    'bir kelimenin ortasından kesme.\n'
    '- "transition": o parçaya GİRİŞ geçişi; seçenekler: fade, flash, dip, slide_left, slide_right, slide_up, '
    'slide_down. İlk parçaya yazma. Geçiş istenip kesim istenmiyorsa videoyu sahne değişimi anlarında bitişik '
    'parçalara böl (ör. 0-4.2, 4.2-9.0) ve geçişleri bu parçalara yaz; hiçbir bölümü atlama. Geçişleri çeşitlendir '
    'ama abartma.\n'
    '- "texts": ekrana yazılacak başlık/yazılar; zamanlar ÇIKTI videosunun zamanında saniyedir. "x","y" yazının '
    'merkezidir (0-1; 0,0 sol üst). "size": small | medium | large. Kısa yaz (en çok 5-6 kelime). Emoji KULLANMA. '
    'Karelerde zaten yazı olan bölgelerin üstüne yazı koyma.\n'
    '- "marks": elle çizilmiş vurgu işaretleri. "type": circle (x,y = dairenin merkezi, "size" = çap / kare '
    'genişliği) veya arrow (x,y = okun UCU yani gösterdiği nokta; from_x,from_y = okun başladığı yer). Zamanlar '
    'KAYNAK videonun zamanında saniyedir; konumlar o andaki karede 0-1 arasıdır. İşareti yalnızca gördüğün bir '
    'karenin zamanına yakın (en çok 1 sn sonrası) koy, çünkü nesneler hareket eder; 1-2.5 sn ekranda kalsın. '
    'Gerçekten dikkat çekilecek şeyi işaretle (yüz, ürün, komik ayrıntı); mevcut yazıların üstünü kapatma. '
    'Az ve yerinde kullan.\n'
    '- Renkler: red, yellow, white, green, blue, pink.\n'
    '- "captions": true ise konuşma dökümü altyazı olarak eklenir (yalnızca döküm varsa işe yarar).\n'
    '- "color" değerleri -50..50, "speed" 0.5..2.0, "volume" 0..1, "aspect" 9:16 | 16:9 | 1:1 | 4:5.\n'
    '- Kullanıcının istemediği alanları yazma; istenmeyen değişiklik yapma.\n'
    '- "summary" her zaman zorunludur. JSON dışında hiçbir şey yazma.'
)


def _fmt_spans(spans, limit=80):
    return ', '.join(f'{a:.2f}-{b:.2f}' for a, b in spans[:limit]) or 'yok'


def current_segments(timeline, sources):
    """Describe the present cut so follow-up prompts can refine it."""
    fps = timeline.fps_num / timeline.fps_den
    index = {str(item['path']): i for i, item in enumerate(sources)}
    clips = [clip for track in timeline.tracks if track.kind == 'video' and not track.muted for clip in track.clips]
    return [{'source': index[clip.source], 'start': round(clip.source_in / fps, 2),
             'end': round((clip.source_in + clip.length) / fps, 2)}
            for clip in sorted(clips, key=lambda c: c.start) if clip.source in index]


def build_prompt(request, sources, timeline=None):
    """sources: [{'path', 'duration', 'silences', 'scenes', 'transcript'}] in index order."""
    lines = [f'KULLANICI İSTEĞİ:\n{request.strip()}', '', 'VİDEO ANALİZİ:']
    for i, item in enumerate(sources):
        lines.append(f'Kaynak {i}: "{Path(str(item["path"])).name}", süre {item["duration"]:.2f} sn')
        lines.append(f'  Sessizlik aralıkları (sn): {_fmt_spans(item.get("silences") or [])}')
        scenes = item.get('scenes') or []
        lines.append('  Sahne değişimleri (sn): ' + (', '.join(f'{s:.2f}' for s in scenes[:80]) or 'yok'))
        transcript = item.get('transcript') or []
        if transcript:
            lines.append('  Konuşma dökümü:')
            lines += [f'    [{seg["start"]:.2f}-{seg["end"]:.2f}] {seg["text"]}' for seg in transcript]
        else:
            lines.append('  Konuşma dökümü: yok (konuşma içeriğine göre karar verme; kare, sessizlik ve sahne bilgisini kullan)')
    if timeline is not None:
        now = current_segments(timeline, sources)
        if now:
            lines += ['', 'ŞU ANKİ KURGU (segments biçiminde): ' + json.dumps(now)]
    lines += ['', 'Ekteki kareler kaynak numarası ve saniyesiyle etiketlidir.', '', RULES, '', 'Şema: ' + SCHEMA]
    return '\n'.join(lines)


def _number(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Planda geçersiz sayı: {name}') from exc
    if not math.isfinite(number):
        raise ValueError(f'Planda geçersiz sayı: {name}')
    return number


def _clamp(value, low, high):
    return max(low, min(high, value))


def _plain(text):
    """Drop emoji and other glyphs the caption font cannot draw."""
    kept = ''.join(ch for ch in str(text) if ch.isprintable() and (ord(ch) < 0x2000 or ch in '\u2018\u2019\u201c\u201d\u2026\u2013\u2014\u20ba\u20ac'))
    return ' '.join(kept.split())


def parse_plan(text, durations):
    """Extract and validate the plan. durations: seconds per source index."""
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        raise ValueError('AI yanıtında geçerli JSON bulunamadı.')
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError('AI yanıtı kurgu planı olarak okunamadı.') from exc
    if not isinstance(data, dict):
        raise ValueError('AI yanıtı kurgu planı olarak okunamadı.')
    plan = {'summary': str(data.get('summary') or '').strip()}

    if data.get('segments') is not None:
        if not isinstance(data['segments'], list):
            raise ValueError('Planda "segments" bir liste olmalı.')
        segments = []
        for item in data['segments']:
            if not isinstance(item, dict):
                raise ValueError('Planda geçersiz parça.')
            source = int(_number(item.get('source', 0), 'source'))
            if not 0 <= source < len(durations):
                raise ValueError(f'Plan olmayan bir kaynağı kullanıyor: {source}')
            # Models round times; tolerate small overshoot instead of failing the whole edit.
            a = _clamp(_number(item.get('start'), 'start'), 0.0, durations[source])
            b = _clamp(_number(item.get('end'), 'end'), 0.0, durations[source])
            if b - a >= MIN_SEGMENT_SECONDS:
                segment = {'source': source, 'start': a, 'end': b}
                if segments and item.get('transition') in TRANSITIONS:
                    segment['transition'] = item['transition']
                segments.append(segment)
        if not segments:
            raise ValueError('Plan videonun tamamını kesiyor; geçerli parça yok.')
        plan['segments'] = segments

    texts = []
    for item in data.get('texts') or []:
        if not isinstance(item, dict) or not _plain(item.get('text') or ''):
            continue
        a, b = _number(item.get('start', 0), 'text start'), _number(item.get('end', 0), 'text end')
        if b > a >= 0:
            texts.append({'start': a, 'end': b, 'text': _plain(item['text']),
                          'x': _clamp(_number(item.get('x', 0.5), 'text x'), 0.0, 1.0),
                          'y': _clamp(_number(item.get('y', 0.78), 'text y'), 0.0, 1.0),
                          'size': item.get('size') if item.get('size') in TEXT_SCALE else 'medium',
                          'color': item.get('color') if item.get('color') in TEXT_COLORS else 'white'})
    if texts:
        plan['texts'] = sorted(texts, key=lambda t: t['start'])

    marks = []
    for item in data.get('marks') or []:
        if not isinstance(item, dict) or item.get('type') not in SHAPES:
            continue
        source = int(_number(item.get('source', 0), 'mark source'))
        if not 0 <= source < len(durations):
            continue
        a = _clamp(_number(item.get('start', 0), 'mark start'), 0.0, durations[source])
        b = _clamp(_number(item.get('end', a + 1.5), 'mark end'), 0.0, durations[source])
        if b - a < 0.3:
            b = min(durations[source], a + 1.5)
        if b - a < 0.3:
            continue
        mark = {'type': item['type'], 'source': source, 'start': a, 'end': min(b, a + 4.0),
                'x': _clamp(_number(item.get('x', 0.5), 'mark x'), 0.0, 1.0),
                'y': _clamp(_number(item.get('y', 0.5), 'mark y'), 0.0, 1.0),
                'color': item.get('color') if item.get('color') in COLORS else 'red'}
        if item['type'] == 'circle':
            mark['size'] = _clamp(_number(item.get('size', 0.3), 'mark size'), 0.08, 0.9)
        elif item.get('from_x') is not None and item.get('from_y') is not None:
            mark['from_x'] = _clamp(_number(item['from_x'], 'from_x'), 0.0, 1.0)
            mark['from_y'] = _clamp(_number(item['from_y'], 'from_y'), 0.0, 1.0)
        marks.append(mark)
    if marks:
        plan['marks'] = sorted(marks, key=lambda m: m['start'])

    if data.get('captions') is True:
        plan['captions'] = True
    if isinstance(data.get('color'), dict):
        plan['color'] = {name: round(_clamp(_number(data['color'].get(name, 0), name), -50, 50))
                         for name in ('brightness', 'contrast', 'saturation')}
    if data.get('speed') is not None:
        speed = _number(data['speed'], 'speed')
        plan['speed'] = min(SPEEDS, key=lambda s: abs(s - speed))
    if data.get('aspect') is not None:
        aspect = str(data['aspect']).strip()
        if aspect not in ASPECTS:
            raise ValueError(f'Plan desteklenmeyen bir oran istiyor: {aspect}')
        plan['aspect'] = aspect
    if data.get('volume') is not None:
        plan['volume'] = _clamp(_number(data['volume'], 'volume'), 0.0, 1.0)
    for name in ('title', 'caption'):
        if str(data.get(name) or '').strip():
            plan[name] = str(data[name]).strip()
    tags = data.get('hashtags')
    if isinstance(tags, list) and any(str(t).strip() for t in tags):
        plan['hashtags'] = [str(t).strip() for t in tags if str(t).strip()]
    return plan


def _to_canvas(x, y, source_size, canvas):
    """Map a point given as a fraction of the source picture onto the letterboxed canvas."""
    if not source_size or not canvas:
        return x, y, 1.0
    (sw, sh), (cw, ch) = source_size, canvas
    scale = min(cw / sw, ch / sh)
    return ((cw - sw * scale) / 2 + x * sw * scale) / cw, ((ch - sh * scale) / 2 + y * sh * scale) / ch, sw * scale / cw


def _place_marks(result, sources, marks, canvas):
    """Marks are timed on the source; follow each one to wherever that footage now sits."""
    fps = result.fps_num / result.fps_den
    tracks = []
    for mark in marks:
        source = sources[mark['source']]
        first, last = round(mark['start'] * fps), round(mark['end'] * fps)
        x, y, shrink = _to_canvas(mark['x'], mark['y'], source.get('size'), canvas)
        style = {'shape': mark['type'], 'x': round(x, 4), 'y': round(y, 4), 'color': mark['color']}
        if mark['type'] == 'circle':
            style['size'] = round(mark['size'] * shrink, 4)
        elif 'from_x' in mark:
            x2, y2, _ = _to_canvas(mark['from_x'], mark['from_y'], source.get('size'), canvas)
            style.update(x2=round(x2, 4), y2=round(y2, 4))
        for video in [t for t in result.tracks if t.kind == 'video' and not t.muted]:
            for clip in video.clips:
                if clip.source != str(source['path']):
                    continue
                left, right = max(first, clip.source_in), min(last, clip.source_in + clip.length)
                if right - left < 3:
                    continue
                piece = Clip('', clip.start + left - clip.source_in, right - left, style=dict(style))
                for track in tracks:
                    if all(piece.end <= other.start or piece.start >= other.end for other in track.clips):
                        track.add(piece)
                        break
                else:
                    if len(tracks) < MARK_TRACKS:
                        name = 'AI İşaretler' if not tracks else f'AI İşaretler {len(tracks) + 1}'
                        tracks.append(Track('text', name, [piece]))
    result.tracks += tracks


def apply_plan(timeline, sources, plan, canvas=None):
    """Return a new Timeline with the plan applied; the input timeline is untouched.

    sources: [{'path', 'duration', 'transcript', 'size'}] in the index order shown to the model.
    canvas: output (width, height); lets marks drawn on the source picture land correctly when letterboxed.
    """
    result = Timeline.from_dict(timeline.to_dict())
    fps = result.fps_num / result.fps_den

    if 'segments' in plan:
        video_tracks = [track for track in result.tracks if track.kind == 'video']
        if not video_tracks:
            result.tracks.insert(0, Track('video', 'Video'))
            video_tracks = [result.tracks[0]]
        for track in video_tracks:
            track.clips = []
        cursor = 0
        for segment in plan['segments']:
            source = sources[segment['source']]
            source_frames = max(1, round(source['duration'] * fps))
            first = min(round(segment['start'] * fps), source_frames - 1)
            length = min(round(segment['end'] * fps), source_frames) - first
            if length < 1:
                continue
            style = {}
            if cursor and segment.get('transition'):
                style = {'transition': segment['transition'], 'transition_frames': max(2, round(TRANSITION_SECONDS * fps))}
            video_tracks[0].add(Clip(str(source['path']), cursor, length, source_in=first,
                                     source_length=source_frames, style=style))
            cursor += length
        if not cursor:
            raise ValueError('Plan uygulanınca boş bir video oluşuyor.')
        # Old captions/titles were timed against the previous cut; music must not outlast the new one.
        result.tracks = [track for track in result.tracks if track.kind != 'text']
        for track in result.tracks:
            if track.kind in ('audio', 'overlay'):
                track.clips = [clip for clip in track.clips if clip.start < cursor]
                for clip in track.clips:
                    clip.length = min(clip.length, cursor - clip.start)
        result.markers = []

    total = max((clip.end for track in result.tracks if track.kind == 'video' for clip in track.clips), default=0)

    if 'volume' in plan:
        for track in result.tracks:
            if track.kind == 'video':
                for clip in track.clips:
                    clip.volume = plan['volume']

    if plan.get('captions'):
        for source in sources:
            if source.get('transcript'):
                caption_track(result, str(source['path']), source['transcript'])

    if plan.get('texts') and total:
        track = Track('text', 'AI Metin')
        cursor = 0
        for item in plan['texts']:
            first = max(cursor, round(item['start'] * fps))
            last = min(total, round(item['end'] * fps))
            if last > first:
                style = {key: item[key] for key in ('x', 'y', 'size', 'color') if key in item}
                track.add(Clip('', first, last - first, text=item['text'], style=style))
                cursor = last
        if track.clips:
            result.tracks.append(track)

    if plan.get('marks'):
        _place_marks(result, sources, plan['marks'], canvas)
    return result


def describe(plan, timeline):
    """Short human-readable report of what was applied."""
    fps = timeline.fps_num / timeline.fps_den
    total = max((clip.end for track in timeline.tracks for clip in track.clips), default=0) / fps
    lines = [plan.get('summary') or 'Kurgu uygulandı.', '']
    if 'segments' in plan:
        lines.append(f'• {len(plan["segments"])} parça, yeni süre {total:.1f} sn')
        lines += [f'    {i + 1}. kaynak {s["source"]}  {s["start"]:.2f} → {s["end"]:.2f}' for i, s in enumerate(plan['segments'])]
    if plan.get('captions'):
        lines.append('• Altyazı eklendi')
    transitions = [s['transition'] for s in plan.get('segments', []) if s.get('transition')]
    if transitions:
        lines.append(f'• {len(transitions)} geçiş: ' + ', '.join(transitions))
    if plan.get('texts'):
        lines.append(f'• {len(plan["texts"])} ekran yazısı')
    if plan.get('marks'):
        placed = sum(1 for track in timeline.tracks for clip in track.clips if clip.style.get('shape'))
        lines.append(f'• {placed} işaret (ok/daire)')
    if 'color' in plan:
        lines.append('• Renk: ' + ', '.join(f'{k} {v:+d}' for k, v in plan['color'].items()))
    if 'speed' in plan:
        lines.append(f'• Hız: {plan["speed"]:.2f}×')
    if 'aspect' in plan:
        lines.append(f'• Oran: {plan["aspect"]}')
    if 'volume' in plan:
        lines.append(f'• Ses: %{round(plan["volume"] * 100)}')
    return '\n'.join(lines)
