"""Templates the user saves from their own projects, kept next to the eight built-in ones.

A saved template holds what a built-in one sets (named tracks, aspect ratio, title text) plus the exact
colour values, speed and sound switches of the project it was taken from, so "do the next video like
this one" is a single choice. Media and cuts are not part of a template.
Stored as one JSON file in the per-user data folder; a damaged file is treated as empty, never deleted.
"""
import json
import os
from pathlib import Path

from akis import audio_polish
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
    except (KeyError, TypeError, ValueError):
        return None


def load(folder):
    """Saved templates, oldest first; [] when there are none or the file cannot be read."""
    try:
        data = json.loads((Path(folder) / FILE_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in map(_valid, (entry for entry in data if isinstance(entry, dict))) if item][:MAX_TEMPLATES]


def _write(folder, items):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / (FILE_NAME + '.tmp')
    partial.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(partial, folder / FILE_NAME)  # a crash mid-write leaves the previous list intact


def add(folder, item):
    """Save the template, replacing one of the same name; returns the new list."""
    item = _valid(item)
    if item is None:
        raise ValueError('Şablon kaydedilemedi: geçersiz içerik.')
    items = [existing for existing in load(folder) if existing['name'].casefold() != item['name'].casefold()]
    if len(items) >= MAX_TEMPLATES:
        raise ValueError(f'En çok {MAX_TEMPLATES} şablon saklanabilir; önce birini silin.')
    items.append(item)
    _write(folder, items)
    return items


def remove(folder, name):
    items = [existing for existing in load(folder) if existing['name'] != name]
    _write(folder, items)
    return items


def apply(timeline, item):
    """Add the template's missing named tracks and, when it has one, its title; existing clips stay."""
    # Like the built-in templates: new video and audio tracks go below the first text track, so they do
    # not cover titles that are already there.
    for kind, name in item['tracks']:
        if not any(track.kind == kind and track.name == name for track in timeline.tracks):
            first_text = next((i for i, track in enumerate(timeline.tracks) if track.kind == 'text'), len(timeline.tracks))
            timeline.tracks.insert(len(timeline.tracks) if kind == 'text' else first_text, Track(kind, name))
    if item['title']:
        target = next((track for track in timeline.tracks if track.kind == 'text'
                       and [track.kind, track.name] in item['tracks']), None)
        if target is not None:
            start = max((clip.end for clip in target.clips), default=0)
            target.add(Clip(source='', start=start, length=round(3 * timeline.fps_num / timeline.fps_den),
                            text=item['title']))
    return timeline


def describe(item):
    """Two lines for the template list's detail area."""
    b, c, s = item['color']
    sound = {'level': 'ses eşitleme', 'denoise': 'gürültü azaltma', 'duck': 'müzik kısma'}
    extras = ', '.join(sound[option] for option in item['audio']) or 'yok'
    framing = {'fit': 'sığdır', 'fill': 'doldur', 'blur': 'bulanık arka plan'}.get(item.get('framing'))
    return ('İzler: ' + ' / '.join(name for _, name in item['tracks']) +
            f'\nOran: {item["aspect"] or "—"} · Hız: {item["speed"]:.2f}× · Renk: {b:+d} / {c:+d} / {s:+d} · Ses: {extras}'
            + (f' · Kadraj: {framing}' if framing else '')
            + (f'\nBaşlık: {item["title"]}' if item['title'] else ''))
