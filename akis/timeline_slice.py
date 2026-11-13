"""Cut a timeline down to a range of frames, and plan ranges that keep a render's open inputs bounded.

slice_timeline() is shared by Shorts (one part per range) and by long exports, which render the picture
in ranges so ffmpeg never holds hundreds of decoders at once (see TimelineRenderer.export).
"""
from copy import deepcopy

from akis.timeline_model import Timeline, Track


def slice_timeline(timeline, start, end):
    """A new timeline with what lies between frames `start` and `end`, moved to begin at 0."""
    part = Timeline(fps_num=timeline.fps_num, fps_den=timeline.fps_den)
    for track in timeline.tracks:
        kept = Track(track.kind, track.name, muted=track.muted)
        for clip in track.clips:
            a, b = max(clip.start, start), min(clip.end, end)
            if b <= a:
                continue
            piece = deepcopy(clip)
            offset = a - clip.start
            piece.start, piece.length = a - start, b - a
            if piece.source:
                piece.source_in = clip.source_frame(a)
            if offset and piece.keyframes:
                piece.keyframes = {k: [dict(p, frame=p['frame'] - offset) for p in v if p['frame'] >= offset]
                                   for k, v in piece.keyframes.items()}
            if offset:  # the clip's own entrance belongs to its real start, not to this cut
                piece.style = {k: v for k, v in piece.style.items() if not k.startswith('transition')}
            kept.clips.append(piece)
        part.tracks.append(kept)
    part.markers = [dict(m, frame=m['frame'] - start) for m in timeline.markers if start <= m.get('frame', 0) < end]
    return part


def picture_clips(timeline):
    return [clip for track in timeline.tracks if track.kind in ('video', 'overlay') and not track.muted
            for clip in track.clips]


def plan_ranges(timeline, limit, total):
    """[(start, end)] frames covering 0..total, each overlapped by at most `limit` picture clips where
    possible. Ranges start where a picture clip starts without a transition into it, so no transition
    and no clip's own entrance is split between two ranges."""
    clips = picture_clips(timeline)
    if len(clips) <= limit:
        return [(0, total)]
    candidates = sorted({c.start for c in clips if 0 < c.start < total and not c.style.get('transition')})
    count = lambda a, b: sum(1 for c in clips if c.start < b and c.end > a)
    ranges, cursor, last_good = [], 0, None
    for frame in candidates + [total]:
        if count(cursor, frame) <= limit:
            last_good = frame
            continue
        cut = last_good if last_good and last_good > cursor else frame
        if cut >= total:
            break
        ranges.append((cursor, cut))
        cursor, last_good = cut, (frame if frame > cut and count(cut, frame) <= limit else None)
    ranges.append((cursor, total))
    return ranges
