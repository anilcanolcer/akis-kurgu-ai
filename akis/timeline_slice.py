"""Cut a timeline down to a range of frames, and plan ranges that keep a render's open inputs bounded.

slice_timeline() is shared by Shorts (one part per range) and by long exports, which render the picture
in ranges so ffmpeg never holds hundreds of decoders at once (see TimelineRenderer.export).
"""
from copy import deepcopy
from uuid import uuid4

from akis.timeline_model import Timeline, Track, cut_words, with_phase

FREEZE = '_freeze'                          # style: show the clip's source_in frame for its whole length
TRANSITION_ELAPSED = '_transition_elapsed'  # style: frames of the transition already shown before this piece


def _held_picture(track, clip, frames):
    """The outgoing clip's last picture, frozen for `frames` frames from 0: what the incoming clip's
    transition is drawn over when a range starts inside (or right at) that transition."""
    before = next((c for c in track.clips if c.end == clip.start and c.source), None)
    if before is None or frames < 1:
        return None
    held = deepcopy(before)
    held.id = uuid4().hex
    last = before.source_frame(before.end - 1)
    held.start, held.length, held.source_in, held.keyframes = 0, frames, last, {}
    held.style = {k: v for k, v in before.style.items()
                  if not k.startswith('transition') and k not in ('speed', 'source_phase', 'punch', 'words')}
    held.style[FREEZE] = True
    return held


def slice_timeline(timeline, start, end):
    """A new timeline with what lies between frames `start` and `end`, moved to begin at 0.

    The part lasts end - start frames even where nothing lies at its end: a Short cut from an edit with a
    gap keeps its planned length (black and quiet where the edit is). A cut inside a transition keeps the
    transition at the point it has reached, drawn over the outgoing clip's held last picture, so the part
    shows the same frames as the whole edit."""
    from akis.timeline_render import transition_of
    part = Timeline(fps_num=timeline.fps_num, fps_den=timeline.fps_den)
    part.length_floor = max(0, end - start)
    for track in timeline.tracks:
        kept = Track(track.kind, track.name, muted=track.muted)
        held_track = None
        for clip in track.clips:
            a, b = max(clip.start, start), min(clip.end, end)
            if b <= a:
                continue
            piece = deepcopy(clip)
            offset = a - clip.start
            if piece.style.get('shape'):
                piece.style = dict(piece.style,
                                   _shape_offset=piece.style.get('_shape_offset', 0) + offset,
                                   _shape_length=piece.style.get('_shape_length', clip.length))
            piece.start, piece.length = a - start, b - a
            if piece.source:   # where the cut falls in the source, between two frames at a fractional speed
                piece.source_in, phase = clip.source_at(a)
                piece.style = with_phase(piece.style, phase)
            if offset and piece.keyframes:
                piece.keyframes = {k: [dict(p, frame=p['frame'] - offset) for p in v if p['frame'] >= offset]
                                   for k, v in piece.keyframes.items()}
            transition = transition_of(track, clip)
            if transition and offset < transition[1]:
                if offset or min(int(clip.style.get('transition_frames', 10)), piece.length // 2) != transition[1]:
                    # Pinned: the transition runs at its full length, `offset` frames of it already shown.
                    piece.style = dict(piece.style, transition_frames=transition[1], **{TRANSITION_ELAPSED: offset})
                if a == start and not track.muted:
                    held = _held_picture(track, clip, min(transition[1] - offset, piece.length))
                    if held is not None:
                        held_track = held_track or Track('overlay', track.name)
                        held_track.clips.append(held)
            elif offset:  # the clip's own entrance belongs to its real start, not to this cut
                piece.style = {k: v for k, v in piece.style.items() if not k.startswith('transition')}
            piece.style = cut_words(piece.style, offset, piece.length)
            kept.clips.append(piece)
        if held_track:
            part.tracks.append(held_track)   # drawn first: under the incoming picture
        part.tracks.append(kept)
    part.markers = [dict(m, frame=m['frame'] - start) for m in timeline.markers if start <= m.get('frame', 0) < end]
    return part


def picture_clips(timeline):
    return [clip for track in timeline.tracks if track.kind in ('video', 'overlay') and not track.muted
            for clip in track.clips]


def transition_intervals(timeline):
    """Sorted transition intervals, including the time the outgoing picture is held."""
    from akis.timeline_render import transition_of
    spans = []
    for track in timeline.tracks:
        if track.muted:
            continue
        for clip in track.clips:
            found = transition_of(track, clip)
            if found:
                spans.append((clip.start, clip.start + found[1]))
    return sorted(spans)


def plan_ranges(timeline, limit, total):
    """[(start, end)] frames covering 0..total, each overlapped by at most `limit` picture clips where
    possible. Ranges start where a picture clip starts without a transition into it, so no transition
    and no clip's own entrance is split between two ranges."""
    clips = picture_clips(timeline)
    if len(clips) <= limit:
        return [(0, total)]
    entrances = transition_intervals(timeline)
    candidates = sorted({c.start for c in clips if 0 < c.start < total
                         and not any(a <= c.start < b for a, b in entrances)})
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
