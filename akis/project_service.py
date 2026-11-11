"""Versioned project document validation and atomic persistence."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from akis.timeline_model import Timeline

CURRENT_VERSION = 2


def migrate(document):
    if document.get('format') != 'akis-kurgu-project':
        raise ValueError('Unsupported project format')
    version = document.get('version', 1)
    if not isinstance(version, int) or version < 1 or version > CURRENT_VERSION:
        raise ValueError('Unsupported project version')
    result = dict(document)
    if version == 1:
        result['timeline'] = result.get('timeline') or Timeline.from_legacy(result.get('state', {})).to_dict()
    Timeline.from_dict(result['timeline'])
    result['version'] = CURRENT_VERSION
    return result


def load(path):
    with Path(path).open(encoding='utf-8') as stream:
        return migrate(json.load(stream))


def media_paths(document):
    """Every media path the document refers to: the main source first, then clip sources in order."""
    paths = []
    source = document.get('state', {}).get('source', '')
    if source:
        paths.append(source)
    for track in document.get('timeline', {}).get('tracks', []):
        for clip in track.get('clips', []):
            path = clip.get('source', '')
            if path and path not in paths:
                paths.append(path)
    return paths


def relative_media(document, folder):
    """{stored path: path relative to folder} for media inside the project folder or below it.

    Kept beside the absolute paths (in a top-level key older versions ignore) so a project folder moved
    together with its media still opens.
    """
    folder = Path(folder).resolve()
    result = {}
    for path in media_paths(document):
        try:
            relative = Path(path).resolve().relative_to(folder)
        except (ValueError, OSError):
            continue
        result[path] = relative.as_posix()
    return result


def save(path, document):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = migrate(document)
    data['relative_media'] = relative_media(data, target.parent)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def make_document(state, timeline, publish, ai_prompt):
    return {
        'format': 'akis-kurgu-project',
        'version': CURRENT_VERSION,
        'saved_at': datetime.now().astimezone().isoformat(),
        'state': dict(state),
        'timeline': timeline.to_dict(),
        'publish': dict(publish),
        'ai_prompt': ai_prompt,
    }


KEEP_VERSIONS = 20


def versions_folder(path):
    target = Path(path)
    return target.parent / f'{target.name}.versions'


def prune_versions(path, keep=KEEP_VERSIONS):
    """Delete all but the newest `keep` snapshots of a project (names are sortable timestamps)."""
    folder = versions_folder(path)
    if not folder.is_dir():
        return []
    snapshots = sorted(folder.glob('*.json'), key=lambda item: item.name, reverse=True)
    removed = []
    for old in snapshots[max(0, keep):]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            pass  # in use or read-only: try again after the next save
    return removed


def save_with_snapshot(path, document, snapshot=False, keep=KEEP_VERSIONS):
    target = Path(path)
    save(target, document)
    if snapshot:
        versions = versions_folder(target)
        versions.mkdir(exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        save(versions / f'{stamp}.json', document)
        prune_versions(target, keep)


def normalize_project_path(path):
    """`proje` -> `proje.akis.json`, `x.json` -> `x.akis.json`; a name already ending in .akis.json is kept."""
    path = str(path)
    lower = path.lower()
    if lower.endswith('.akis.json'):
        return path
    if lower.endswith('.json'):
        path = path[:-len('.json')]
    return path + '.akis.json'


def resolve_media(path, folder, relative):
    """The existing file a stored media path means: as stored (absolute) first, then relative to folder."""
    stored = Path(path)
    if stored.is_absolute() and stored.exists():
        return str(stored)
    candidates = []
    if path in relative:
        candidates.append(relative[path])
    if not stored.is_absolute():
        candidates.append(path)
    for candidate in candidates:
        try:
            resolved = (Path(folder) / candidate).resolve()
        except (OSError, ValueError):
            continue
        if resolved.exists():
            return str(resolved)
    return None


def load_project(path):
    """(document, main source, missing media) with media paths resolved against the project's folder.

    The main source may be missing when the timeline still has a usable video: that video becomes the
    source. Media that cannot be found are listed instead of failing the open.
    """
    document = load(path)
    folder = Path(path).parent
    relative = document.get('relative_media') or {}
    if not isinstance(relative, dict):
        relative = {}
    resolved, missing = {}, []
    for stored in media_paths(document):
        found = resolve_media(stored, folder, relative)
        if found is None:
            missing.append(stored)
        else:
            resolved[stored] = found
    state = document.setdefault('state', {})
    timeline = document.get('timeline', {})
    for track in timeline.get('tracks', []):
        for clip in track.get('clips', []):
            if clip.get('source') in resolved:
                clip['source'] = resolved[clip['source']]
    source = state.get('source', '')
    if source in resolved:
        state['source'] = resolved[source]
    else:
        usable = next((clip['source'] for track in timeline.get('tracks', []) if track.get('kind') == 'video'
                       for clip in sorted(track.get('clips', []), key=lambda c: c.get('start', 0))
                       if clip.get('source') and clip['source'] in resolved.values()), None)
        if usable is None:
            raise FileNotFoundError('Projede kullanılan kaynak video bulunamadı.')
        state['source'] = usable
    return document, state['source'], missing


def load_with_source(path):
    document, source, _missing = load_project(path)
    return document, source
