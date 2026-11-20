"""Versioned project document validation and atomic persistence."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

from akis.timeline_model import Timeline

CURRENT_VERSION = 2
REPLACE_RETRY_DELAYS = (0.05, 0.1, 0.2)


def _is_transient_delete_share_lock(target):
    """On Windows, os.replace may report access denied for a temporary no-delete-share handle.

    Probe the target with DELETE access so a real sharing conflict (32/33) can be retried while
    an ACL/access denial (5) still fails immediately.
    """
    if os.name != 'nt':
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        create_file.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = create_file(str(target), 0x00010000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
        invalid_handle = ctypes.c_void_p(-1).value
        if handle is None or handle == invalid_handle:
            return ctypes.get_last_error() in (32, 33)
        close_handle(handle)
        return False
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _replace_with_retry(source, target):
    """Retry short Windows sharing locks without changing the atomic-save guarantee."""
    delays = REPLACE_RETRY_DELAYS
    for attempt in range(len(delays) + 1):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            code = getattr(exc, 'winerror', None)
            sharing_violation = (code in (32, 33) or
                                 (os.name == 'nt' and exc.errno in (32, 33)) or
                                 (os.name == 'nt' and code == 5 and _is_transient_delete_share_lock(target)))
            if not sharing_violation or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


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


STILL_IMAGE = 'still_image'  # same key as timeline_service.STILL_IMAGE (kept import-free here)


def still_images(document):
    """{clip source: photo path} for clips converted from a photo (＋ Medya), in timeline order."""
    found = {}
    for track in document.get('timeline', {}).get('tracks', []):
        for clip in track.get('clips', []):
            style = clip.get('style') or {}
            image = style.get(STILL_IMAGE) if isinstance(style, dict) else None
            if clip.get('source') and isinstance(image, str) and image:
                found.setdefault(clip['source'], image)
    return found


def relative_media(document, folder, *, media_root=None):
    """{stored path: path relative to folder} for media inside the project folder or below it.

    Kept beside the absolute paths (in a top-level key older versions ignore) so a project folder moved
    together with its media still opens. A snapshot is written inside a versions subfolder, but its
    media root stays the original project folder; only media within that root get relative references.
    """
    folder = Path(folder).resolve()
    root = Path(media_root).resolve() if media_root is not None else folder
    result = {}
    for path in media_paths(document) + [image for image in still_images(document).values()]:
        try:
            stored = Path(path)
            source = (stored if stored.is_absolute() else root / stored).resolve()
            source.relative_to(root)
            relative = Path(os.path.relpath(source, folder))
        except (ValueError, OSError):
            continue
        result[path] = relative.as_posix()
    return result


def save(path, document, *, media_root=None):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = migrate(document)
    data['relative_media'] = relative_media(data, target.parent, media_root=media_root)
    name = None
    try:
        # A short temporary name in the same folder (the replace stays atomic): built from the target's name,
        # a valid long project name (Windows allows 255 characters) became an invalid one (errno 22).
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix='.akis-', suffix='.tmp', delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_with_retry(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@dataclass(frozen=True)
class SaveResult:
    """The project itself is saved when this is returned; the version copy is best-effort."""
    snapshot_saved: bool | None = None
    snapshot_error: OSError | None = None


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
# The name save_with_snapshot gives a version: 20261120-091500-123456.json. Pruning deletes only these, so a
# note or any other JSON file someone put in the versions folder is left alone.
SNAPSHOT_NAME = re.compile(r'\d{8}-\d{6}-\d{6}\.json')


def versions_folder(path):
    target = Path(path)
    return target.parent / f'{target.name}.versions'


def prune_versions(path, keep=KEEP_VERSIONS):
    """Delete all but the newest `keep` snapshots of a project (names are sortable timestamps)."""
    folder = versions_folder(path)
    if not folder.is_dir():
        return []
    snapshots = sorted((item for item in folder.glob('*.json') if SNAPSHOT_NAME.fullmatch(item.name)),
                       key=lambda item: item.name, reverse=True)
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
    if not snapshot:
        return SaveResult()
    try:
        versions = versions_folder(target)
        versions.mkdir(exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        save(versions / f'{stamp}.json', document, media_root=target.parent)
        prune_versions(target, keep)
    except OSError as exc:
        # The main project is already committed atomically. A protected/unwritable versions folder must
        # not make the UI report that the project failed to save or leave the editor marked dirty.
        return SaveResult(snapshot_saved=False, snapshot_error=exc)
    return SaveResult(snapshot_saved=True)


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


def missing_media(path):
    """The media paths of the project file at `path` that cannot be found (as stored, in order)."""
    document = load(path)
    folder = Path(path).parent
    relative = document.get('relative_media') or {}
    if not isinstance(relative, dict):
        relative = {}
    return [stored for stored in media_paths(document) if resolve_media(stored, folder, relative) is None]


def media_name(stored):
    """The file name of a stored media path, whichever separator the saving computer used."""
    return PureWindowsPath(str(stored)).name


def find_moved(missing, located_from, located_to, taken=()):
    """{stored: file now} for missing media, worked out from one file the user located.

    `located_from` is where the project said that file was, `located_to` where it is now. Their folders
    share a tail (…/Proje/A on both sides); the media that lived under the old folders are looked for at
    the same place under the new ones, deepest first, so Proje/B/take.mp4 is found in the moved Proje/B.
    A file of the same name next to the located one is the last resort. No file is ever given to two
    different sources, and none that is already in `taken`: two takes called take.mp4 in different
    folders must not both become the one the user pointed at; one that cannot be told apart stays
    missing, so the user is asked about it on its own.
    """
    old_file, new_file = PureWindowsPath(str(located_from)), Path(located_to)
    levels = [(old_file.parent, new_file.parent)]
    old_dir, new_dir = old_file.parent, new_file.parent
    while (old_dir.name and new_dir.name and old_dir.name.casefold() == new_dir.name.casefold()
           and old_dir.parent != old_dir and new_dir.parent != new_dir):
        old_dir, new_dir = old_dir.parent, new_dir.parent
        levels.append((old_dir, new_dir))
    used = {os.path.normcase(os.path.abspath(str(path))) for path in taken}
    used.add(os.path.normcase(os.path.abspath(str(new_file))))
    found = {}
    for stored in missing:
        if str(stored) == str(located_from):
            continue
        place = PureWindowsPath(str(stored))
        candidates = []
        for old_root, new_root in levels:
            try:
                candidates.append(new_root / place.relative_to(old_root))
            except ValueError:
                continue
        candidates.append(new_file.parent / place.name)
        for candidate in candidates:
            key = os.path.normcase(os.path.abspath(str(candidate)))
            if key not in used and candidate.is_file():
                found[stored] = str(candidate)
                used.add(key)
                break
    return found


def load_project(path, replacements=None):
    """(document, main source, missing media) with media paths resolved against the project's folder.

    The main source may be missing when the timeline still has a usable video: that video becomes the
    source. Media that cannot be found are listed instead of failing the open. `replacements` maps a
    stored path to the file the user located for it (a moved or renamed file); it wins over the stored
    path, and the document then refers to the new file.
    """
    document = load(path)
    folder = Path(path).parent
    relative = document.get('relative_media') or {}
    if not isinstance(relative, dict):
        relative = {}
    replacements = {stored: str(new) for stored, new in (replacements or {}).items() if Path(new).is_file()}
    resolved, missing = {}, []
    for stored in media_paths(document):
        found = replacements.get(stored) or resolve_media(stored, folder, relative)
        if found is None:
            missing.append(stored)
        else:
            resolved[stored] = found
    state = document.setdefault('state', {})
    timeline = document.get('timeline', {})
    for track in timeline.get('tracks', []):
        for clip in track.get('clips', []):
            style = clip.get('style') if isinstance(clip.get('style'), dict) else {}
            image = style.get(STILL_IMAGE)
            if isinstance(image, str) and image:
                located = resolve_media(image, folder, relative)
                if located:
                    style[STILL_IMAGE] = located
            if clip.get('source') in resolved:
                clip['source'] = resolved[clip['source']]
    source = state.get('source', '')
    if source in resolved:
        state['source'] = resolved[source]
    else:
        usable = next((clip['source'] for track in timeline.get('tracks', []) if track.get('kind') == 'video'
                       for clip in sorted(track.get('clips', []), key=lambda c: c.get('start', 0))
                       if clip.get('source') and clip['source'] in resolved.values()), None)
        if usable is None and not source:
            return document, '', missing  # work saved before any video was added (audio, text, ...)
        if usable is None:
            raise FileNotFoundError('Projede kullanılan kaynak video bulunamadı.')
        state['source'] = usable
    return document, state['source'], missing


def load_with_source(path):
    document, source, _missing = load_project(path)
    return document, source
