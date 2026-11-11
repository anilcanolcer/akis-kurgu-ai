"""Remove render scratch folders that a crash or forced exit left in the system temp directory."""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

STALE_PREFIXES = ('akis_render_', 'akis_proxy_', 'akis_speed_', 'akis_preview_')
MAX_AGE_SECONDS = 24 * 3600


def cleanup_stale_temp_dirs(root=None, *, max_age=MAX_AGE_SECONDS, now=None):
    """Delete our scratch folders older than max_age seconds; returns the names removed.

    Never raises: a folder in use by another running instance or locked by a scanner is skipped.
    """
    removed = []
    try:
        root = Path(root or tempfile.gettempdir())
        now = time.time() if now is None else now
        entries = list(root.iterdir())
    except OSError:
        return removed
    for entry in entries:
        try:
            if not entry.name.startswith(STALE_PREFIXES) or not entry.is_dir() or entry.is_symlink():
                continue
            if now - entry.stat().st_mtime < max_age:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            if not entry.exists():
                removed.append(entry.name)
        except OSError:
            continue
    return removed
