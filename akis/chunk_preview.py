"""The playback copy in pieces: only the pieces an edit changed are drawn again.

The smooth-playback copy (ProxyPlayback) used to be one render of the whole edit, so trimming one clip at
the end of a ten-minute video meant waiting for all ten minutes again. Here the picture is drawn in pieces
of about CHUNK_SECONDS; each piece is stored under the signature of what it shows, so a piece that did not
change is reused as it is. The sound (cheap: no picture is decoded) is mixed in one pass, so it has no
seams, and pieces and sound are joined without re-encoding.

Piece edges avoid transitions: an edge inside a clip's entrance moves to where the entrance has ended, so
no fade or slide is cut in two.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from akis.shape_art import drawing_seed
from akis.timeline_slice import picture_clips, plan_ranges, slice_timeline, transition_intervals

CHUNK_SECONDS = 8.0      # shorter pieces redraw less after an edit, longer ones draw faster the first time
KEEP_UNUSED = 40          # stored pieces no longer in the edit, kept for undo; older ones are deleted


def chunk_bounds(timeline, total, limit, seconds=None):
    """[(start, end)] frames covering 0..total in pieces of about `seconds`, none starting inside an
    entrance, and none holding more than `limit` picture clips (those are cut finer, as an export is)."""
    fps = timeline.fps_num / timeline.fps_den
    step = max(1, round((seconds or CHUNK_SECONDS) * fps))
    entrances = transition_intervals(timeline)
    edges, frame = [0], step
    while frame < total:
        for a, b in entrances:
            if a <= frame < b:
                frame = b
        if edges[-1] < frame < total:
            edges.append(frame)
        frame = max(frame, edges[-1]) + step
    edges.append(total)
    bounds = []
    for a, b in zip(edges, edges[1:]):
        part = slice_timeline(timeline, a, b)
        if len(picture_clips(part)) > limit:
            bounds += [(a + x, a + y) for x, y in plan_ranges(part, limit, b - a)]
        else:
            bounds.append((a, b))
    return bounds


def source_stamps(timeline, kinds=None):
    """{source path: (size, modification time ns)} of the media a timeline uses; None for a missing file.

    The edit itself names files only by path. A file replaced at the same path (re-exported from another
    program, a different take saved under the old name) must not reuse previews drawn from the old one.
    """
    stamps = {}
    for track in timeline.tracks:
        if kinds is not None and track.kind not in kinds:
            continue
        for clip in track.clips:
            for path in (clip.source, clip.style.get('still_image') if isinstance(clip.style, dict) else None):
                if path and path not in stamps:
                    try:
                        stat = os.stat(path)
                        stamps[path] = (stat.st_size, stat.st_mtime_ns)
                    except OSError:
                        stamps[path] = None
    return stamps


def piece_key(part, size, settings):
    """What a piece shows: its sliced timeline's picture, the canvas, the look settings and the state of the
    media files it draws from. Clip ids matter only when they seed the appearance of a drawing."""
    data = part.to_dict()
    # Only the picture: sound tracks and clip volumes do not change a piece (the sound is mixed separately).
    data['tracks'] = [track for track in data['tracks'] if track['kind'] != 'audio']
    for track in data['tracks']:
        for clip in track['clips']:
            clip_id = clip.pop('id')
            clip.pop('volume', None)
            if clip['style'].get('shape') in ('circle', 'arrow'):
                clip['drawing_seed'] = drawing_seed(clip_id, clip['style'])
                clip['style'].pop('_shape_seed_id', None)
    files = sorted(source_stamps(part, kinds={'video', 'overlay', 'text'}).items())
    payload = json.dumps([data, list(size), sorted(settings.items()), files], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


def tidy(folder, used):
    """Delete stored pieces beyond the KEEP_UNUSED most recent ones that the current edit does not use."""
    unused = sorted((p for p in Path(folder).glob('*.mp4') if p.stem not in used),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in unused[KEEP_UNUSED:]:
        try:
            stale.unlink()
        except OSError:
            pass


def store(rendered, target):
    """Move a finished piece into the store (atomically, so a half-written piece is never reused)."""
    os.replace(rendered, target)
