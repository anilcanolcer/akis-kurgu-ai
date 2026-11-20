"""Remembers what was already worked out about a media file, for as long as the app runs.

An AI edit analyses every source first: silences, scene changes, sample frames, optionally the speech.
Follow-up requests on the same video ("now make it shorter") used to repeat all of it. Results are kept
here per file, and a file that changes on disk (size or modification time) is analysed afresh.
In memory only: nothing is written to disk, and closing the app forgets everything.
"""
import os
import sys
import threading

MAX_BYTES = 96 * 1024 * 1024   # sample frames are the only large entries; oldest files go first
_lock = threading.Lock()
_files = {}                    # file key -> {entry name: value}; insertion order = age
_sizes = {}                    # file key -> bytes held by its entries


def file_key(path):
    """Identity of a file's current content, or None when it cannot be read (then nothing is cached)."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return os.path.normcase(os.path.abspath(path)), stat.st_size, stat.st_mtime_ns


def _weight(value):
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        return size + sum(_weight(k) + _weight(v) for k, v in value.items())
    if isinstance(value, (tuple, list)):
        return size + sum(map(_weight, value))
    return size


def remember(path, name, compute, *, keep=lambda value: True):
    """compute() once per file and entry name; later calls return the stored value.

    keep(value) decides whether a result is worth storing: a failed step should run again next time.
    """
    key = file_key(path)
    if key is not None:
        with _lock:
            entries = _files.get(key)
            if entries is not None and name in entries:
                return entries[name]
    value = compute()
    if key is not None and keep(value):
        weight = _weight(value)
        with _lock:
            if weight > MAX_BYTES or file_key(path) != key:
                return value
            if name in _files.get(key, {}):
                return _files[key][name]
            stale = [other for other in _files if other[0] == key[0] and other != key]
            for other in stale:              # the file changed on disk: its old results are useless
                _files.pop(other, None)
                _sizes.pop(other, None)
            _files.setdefault(key, {})[name] = value
            _sizes[key] = _sizes.get(key, 0) + weight
            while sum(_sizes.values()) > MAX_BYTES:
                oldest = next(iter(_files))
                _files.pop(oldest)
                _sizes.pop(oldest, None)
    return value


def clear():
    with _lock:
        _files.clear()
        _sizes.clear()


def held_bytes():
    with _lock:
        return sum(_sizes.values())
