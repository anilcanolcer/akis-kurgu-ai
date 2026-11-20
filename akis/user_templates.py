"""Templates the user saves from their own projects, kept next to the eight built-in ones.

A saved template holds what a built-in one sets (named tracks, aspect ratio, title text) plus the exact
colour values, speed and sound switches of the project it was taken from, so "do the next video like
this one" is a single choice. Media and cuts are not part of a template.
Stored as one JSON file in the per-user data folder; a damaged file is treated as empty, never deleted.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path

from PySide6.QtCore import QLockFile

from akis import audio_polish, clip_fit, i18n
from akis.timeline_model import Clip, Track

FILE_NAME = 'templates.json'
MAX_NAME = 60
MAX_TEMPLATES = 100
KINDS = ('video', 'audio', 'text', 'overlay')
FRAMINGS = ('fit', 'fill', 'blur')   # akis.clip_fit; optional


def clean_name(name):
    return ' '.join(str(name or '').split())[:MAX_NAME]


def capture(name, timeline, *, aspect, color, speed, audio=()):
    """A template of the project as it stands. `aspect` is the editor's aspect key (stored as given)."""
    name = clean_name(name)
    if not name:
        raise ValueError('Şablona bir ad verin.')
    title = next((clip.text for track in timeline.tracks if track.kind == 'text'
                  for clip in sorted(track.clips, key=lambda c: c.start) if clip.text and not clip.style.get('shape')), '')
    return {'name': name, 'aspect': str(aspect), 'tracks': [[track.kind, track.name] for track in timeline.tracks],
            'title': title[:200], 'color': [int(value) for value in color], 'speed': float(speed),
            'audio': list(audio_polish.clean(audio))}


def _valid(item):
    """The item with every field checked, or None when it cannot be used."""
    try:
        name = clean_name(item['name'])
        tracks = [[str(kind), str(track_name)[:80]] for kind, track_name in item['tracks'] if kind in KINDS]
        color = [max(-50, min(50, int(value))) for value in item.get('color', (0, 0, 0))]
        speed = float(item.get('speed', 1.0))
        audio = [option for option in item.get('audio', ()) if option in audio_polish.OPTIONS]
        if not name or len(color) != 3 or not 0.5 <= speed <= 2.0:
            return None
        found = {'name': name, 'aspect': str(item.get('aspect', '')), 'tracks': tracks,
                 'title': str(item.get('title', ''))[:200], 'color': color, 'speed': speed, 'audio': sorted(audio)}
        if item.get('framing') in FRAMINGS:      # taken from a sample video (akis.style_sample)
            found['framing'] = item['framing']
        return found
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _read(folder, *, for_update=False):
    path = Path(folder) / FILE_NAME
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError
        items = [_valid(entry) if isinstance(entry, dict) else None for entry in data]
        if for_update and (None in items or len(items) > MAX_TEMPLATES):
            raise ValueError
        return [item for item in items if item is not None][:MAX_TEMPLATES]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        if for_update:
            raise OSError('Şablon dosyası okunamadığı için değişiklik kaydedilemedi.') from exc
        return []


def load(folder):
    """Return the readable templates, even if another entry is damaged."""
    return _read(folder)


@contextmanager
def _update(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(folder / (FILE_NAME + '.lock')))
    if not lock.tryLock(1000):
        raise OSError('Şablon dosyası yazma için kilitlenemedi.')
    partial = folder / (FILE_NAME + '.tmp')
    try:
        items = _read(folder, for_update=True)
        yield items
        partial.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(partial, folder / FILE_NAME)
    finally:
        try:
            partial.unlink(missing_ok=True)
        finally:
            lock.unlock()


def add(folder, item):
    """Save the template, replacing one of the same name; returns the new list."""
    item = _valid(item)
    if item is None:
        raise ValueError('Şablon kaydedilemedi: geçersiz içerik.')
    with _update(folder) as items:
        items[:] = [existing for existing in items if existing['name'].casefold() != item['name'].casefold()]
        if len(items) >= MAX_TEMPLATES:
            raise ValueError(f'En çok {MAX_TEMPLATES} şablon saklanabilir; önce birini silin.')
        items.append(item)
    return items


def remove(folder, name):
    with _update(folder) as items:
        items[:] = [existing for existing in items if existing['name'] != name]
    return items


def apply(timeline, item):
    """Add the template's missing named tracks and, when it has one, its title; existing clips stay."""
    # Like the built-in templates: new video and audio tracks go below the first text track, so they do
    # not cover titles that are already there.
    for kind, name in item['tracks']:
        if not any(track.kind == kind and track.name == name for track in timeline.tracks):
            first_text = next((i for i, track in enumerate(timeline.tracks) if track.kind == 'text'), len(timeline.tracks))
            timeline.tracks.insert(len(timeline.tracks) if kind == 'text' else first_text, Track(kind, name))
    if item.get('framing'):
        for track in timeline.tracks:
            if track.kind == 'video':
                for clip in track.clips:
                    clip_fit.apply(clip, item['framing'])
    if item['title']:
        target = next((track for track in timeline.tracks if track.kind == 'text'
                       and [track.kind, track.name] in item['tracks']), None)
        if target is not None:
            start = max((clip.end for clip in target.clips), default=0)
            target.add(Clip(source='', start=start, length=round(3 * timeline.fps_num / timeline.fps_den),
                            text=item['title']))
    return timeline


def describe(item, language='tr'):
    def say(text):
        return i18n.translate(text, language)

    b, c, s = item['color']
    sound = {'level': 'ses eşitleme', 'denoise': 'gürültü azaltma', 'duck': 'müzik kısma'}
    extras = ', '.join(say(sound[option]) for option in item['audio']) or say('yok')
    framing = {'fit': 'sığdır', 'fill': 'doldur', 'blur': 'bulanık arka plan'}.get(item.get('framing'))
    names = ' / '.join(i18n.track_label(name, language) for _, name in item['tracks'])
    lines = [say('İzler: {tracks}').format(tracks=names),
             say('Oran: {aspect} · Hız: {speed}× · Renk: {color} · Ses: {sound}').format(
                 aspect=say(item['aspect']) or '—', speed=f"{item['speed']:.2f}",
                 color=f'{b:+d} / {c:+d} / {s:+d}', sound=extras)]
    if framing:
        lines[-1] += say(' · Kadraj: {framing}').format(framing=say(framing))
    if item['title']:
        lines.append(say('Başlık: {title}').format(title=item['title']))
    return '\n'.join(lines)
