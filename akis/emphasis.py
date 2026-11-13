"""Punch-in zoom at the moments the speaker gets louder.

Emphasis is found in the main video's own sound: a moment clearly louder than the second before it (a
stressed word, a laugh, a shout), at most one every few seconds. At each, the picture eases in to a slight
zoom, holds it briefly and eases back out.

Zooms are kept in a clip's style as source frames ({'punch': [[source frame, length], …]}), so splitting,
trimming and AI re-cuts carry them along with the picture they belong to.
"""
import statistics

ZOOM = 1.12           # how close the punch-in goes
HOLD = 1.2            # seconds a punch lasts, ramps included
RAMP = 0.2            # seconds to ease in and out
MIN_GAP = 5.0         # seconds between two punches
RISE_DB = 9.0         # louder than the second before by at least this much
LOOKBACK = 1.0        # seconds the "second before" covers
MIN_PER_PUNCH = 6.0   # at most one punch per this many seconds of video on average


def find_moments(levels, window=0.02):
    """Seconds where the sound jumps up, strongest first chosen, MIN_GAP apart, returned in order.

    levels: loudness in dBFS per `window` seconds (akis.silence_cut.measure)."""
    if len(levels) < 3 / window:
        return []
    floor = statistics.median(levels)
    back = max(1, round(LOOKBACK / window))
    candidates = []
    for index in range(back, len(levels) - 1):
        level = levels[index]
        if level < floor + 3 or level < levels[index - 1] or level < levels[index + 1]:
            continue
        before = statistics.median(levels[index - back:index])
        rise = level - before
        if rise >= RISE_DB:
            candidates.append((rise, index * window))
    chosen = []
    allowed = max(1, int(len(levels) * window / MIN_PER_PUNCH))
    for rise, second in sorted(candidates, reverse=True):
        if len(chosen) >= allowed:
            break
        if all(abs(second - other) >= MIN_GAP for other in chosen):
            chosen.append(second)
    return sorted(chosen)


def apply(timeline, moments_by_source):
    """Put punches on every main-track clip over the moments of its source; returns how many were placed.

    moments_by_source: {source path: [seconds in that source]}. Earlier punches are replaced."""
    fps = timeline.fps_num / timeline.fps_den
    hold = max(2, round(HOLD * fps))
    placed = 0
    main = next((track for track in timeline.tracks if track.kind == 'video'), None)
    for clip in main.clips if main else ():
        frames = [round(second * fps) for second in moments_by_source.get(clip.source, ())]
        punches = [[frame, hold] for frame in frames if clip.source_in <= frame < clip.source_in + clip.length]
        style = {key: value for key, value in clip.style.items() if key != 'punch'}
        if punches:
            style['punch'] = punches
            placed += len(punches)
        clip.style = style
    return placed


def clear(timeline):
    """Remove every punch; returns how many there were."""
    removed = 0
    for track in timeline.tracks:
        for clip in track.clips:
            if 'punch' in clip.style:
                removed += len(clip.style['punch'])
                clip.style = {key: value for key, value in clip.style.items() if key != 'punch'}
    return removed


def zoom_filter(clip, fps_num, fps_den, skip, width, height):
    """The zoompan filter for a clip's punches, or '' when it has none.

    The filter sees the clip from `skip` seconds in, starting at time 0; source time is
    source_in + skip + its own input time."""
    punches = clip.style.get('punch') or []
    fps = fps_num / fps_den
    terms = []
    for first, length in punches:
        try:
            start, end = float(first) / fps, (float(first) + float(length)) / fps
        except (TypeError, ValueError):
            continue
        ramp = min(RAMP, (end - start) / 2)
        if ramp <= 0:
            continue
        terms.append(f'clip(min((T-{start:.4f})/{ramp:.4f}\\,({end:.4f}-T)/{ramp:.4f})\\,0\\,1)')
    if not terms:
        return ''
    offset = clip.source_in / fps + skip
    envelope = 'min(1\\,' + '+'.join(terms) + ')' if len(terms) > 1 else terms[0]
    zoom = f'1+{ZOOM - 1:.4f}*{envelope}'.replace('T', f'(it+{offset:.6f})')
    return (f"fps={fps_num}/{fps_den},zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={width}x{height}:fps={fps_num}/{fps_den}")
