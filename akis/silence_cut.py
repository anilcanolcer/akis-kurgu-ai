"""Remove silences from the main cut without an AI call.

The audio is measured once into a loudness curve (one value per WINDOW seconds). Every setting the user
then changes (threshold, shortest silence, margin) only re-reads that curve, so the result updates at once.
The outcome is a list of segments in the shape edit_plan.apply_plan() already takes, so the cut itself,
the other tracks and the markers are handled by the code the AI edit uses.
"""
import array
import math
import os
import subprocess
import sys

SAMPLE_RATE = 2000        # speech energy sits well below 1 kHz; enough to tell speech from silence
WINDOW = 0.02             # seconds per loudness value
FLOOR_DB = -100.0
MAX_SECONDS = 4 * 3600
DEFAULT_THRESHOLD_DB = -35
DEFAULT_MIN_SILENCE = 0.5
DEFAULT_MARGIN = 0.2      # speech kept on both sides of a cut, so word starts and ends are not clipped
MIN_KEEP = 0.25           # a kept piece shorter than this would only flicker by; it is cut with the silence


def levels_from_pcm(data, rate=SAMPLE_RATE, window=WINDOW):
    """Loudness in dBFS (RMS) for each window of 16-bit mono PCM."""
    samples = array.array('h')
    samples.frombytes(data[:len(data) - len(data) % 2])
    if sys.byteorder != 'little':
        samples.byteswap()
    step = max(1, round(rate * window))
    levels = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        mean = sum(n * n for n in chunk) / len(chunk)
        levels.append(max(FLOOR_DB, 10 * math.log10(mean / (32768.0 * 32768.0))) if mean else FLOOR_DB)
    return levels


def measure(executable, source, runner=subprocess.run):
    """The loudness curve of a media file's audio; [] when it has none or cannot be read."""
    command = [executable, '-v', 'error', '-i', str(source), '-t', str(MAX_SECONDS), '-vn', '-ac', '1',
               '-ar', str(SAMPLE_RATE), '-f', 's16le', 'pipe:1']
    try:
        result = runner(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=600,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return levels_from_pcm(result.stdout) if result.returncode == 0 else []


def silent_spans(levels, threshold_db=DEFAULT_THRESHOLD_DB, min_silence=DEFAULT_MIN_SILENCE, window=WINDOW):
    """(start, end) seconds of every stretch quieter than the threshold for at least min_silence."""
    spans, start = [], None
    for i, level in enumerate(levels):
        if level < threshold_db:
            if start is None:
                start = i
        elif start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(levels)))
    need = min_silence - 1e-9
    return [(a * window, b * window) for a, b in spans if (b - a) * window >= need]


def keep_segments(segments, silences, margin=DEFAULT_MARGIN, min_keep=MIN_KEEP):
    """Cut the silences out of the main cut.

    segments: edit_plan.current_segments() ([{'source', 'start', 'end', 'transition'?}], seconds in the source).
    silences: {source index: [(start, end)]} in source seconds.
    Returns (new segments, cuts) where cuts lists every removed range as (segment number, start, end),
    the segment number counting the given segments from 0.
    A silence keeps `margin` seconds on each side that touches speech; one at the very start or end of a
    segment is removed up to the edge. A segment that is silent throughout is left alone: emptying the
    video is never what "remove the pauses" means.
    """
    result, cuts = [], []
    for number, segment in enumerate(segments):
        source, first, last = segment['source'], segment['start'], segment['end']
        removed = []
        for a, b in sorted(silences.get(source, ())):
            lo = first if a <= first else a + margin
            hi = last if b >= last else b - margin
            lo, hi = max(lo, first), min(hi, last)
            if hi - lo > 1e-6:
                removed.append((lo, hi))
        kept, cursor = [], first
        for lo, hi in removed:
            if lo > cursor:
                kept.append([cursor, lo])
            cursor = max(cursor, hi)
        if last > cursor:
            kept.append([cursor, last])
        # A sliver of sound between two silences (a click, a breath) goes with them instead of flickering by.
        merged = [piece for piece in kept if piece[1] - piece[0] >= min_keep]
        if not merged:
            result.append(dict(segment))
            continue
        cursor = first
        for n, (a, b) in enumerate(merged):
            if a > cursor:
                cuts.append((number, cursor, a))
            piece = {'source': source, 'start': round(a, 3), 'end': round(b, 3)}
            if not n and segment.get('transition'):
                piece['transition'] = segment['transition']
            result.append(piece)
            cursor = b
        if last > cursor:
            cuts.append((number, cursor, last))
    return result, cuts


def duration(segments):
    return sum(segment['end'] - segment['start'] for segment in segments)


def clock(seconds):
    """1:07 or 1:02:07 for a length in seconds."""
    seconds = max(0, round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f'{hours}:{minutes:02d}:{secs:02d}' if hours else f'{minutes}:{secs:02d}'


NOTHING = 'Bu ayarlarla kesilecek sessizlik bulunamadı.'
SUMMARY = '{count} sessiz yer kesilecek · {before} → {after} ({saved} sn kısalır)'


def summary(before, after, cuts, say=str):
    """One sentence for the dialog. `say` translates a Turkish template (the default leaves it Turkish)."""
    if not cuts:
        return say(NOTHING)
    saved = duration(before) - duration(after)
    return say(SUMMARY).format(count=len(cuts), before=clock(duration(before)), after=clock(duration(after)),
                               saved=f'{saved:.1f}')
