"""Find the liveliest stretches of a long edit, each with the reasons it stands out.

Works from the main video's own sound (no AI, nothing leaves the computer): every candidate stretch of the
chosen length gets a score from how much of it is speech, how often the voice rises sharply (stressed
words, laughter, shouts) and how loud it is compared with the rest. The best ones that do not overlap are
returned, their ends moved to nearby pauses so sentences are not cut.
"""
import statistics

WINDOW = 0.02          # seconds per loudness value (akis.silence_cut)
STEP = 2.0             # seconds between candidate starts
RISE_DB = 9.0
SNAP = 4.0             # seconds an end may move to reach a pause


def timeline_levels(timeline, levels_for, window=WINDOW):
    """One loudness curve for the whole edit: the main track's clips, each its own source's stretch."""
    fps = timeline.fps_num / timeline.fps_den
    main = next((track for track in timeline.tracks if track.kind == 'video'), None)
    clips = sorted(main.clips, key=lambda c: c.start) if main else []
    total = max((clip.end for clip in clips), default=0) / fps
    curve = [-100.0] * int(total / window)
    cache = {}
    for clip in clips:
        if not clip.source:
            continue
        if clip.source not in cache:
            cache[clip.source] = levels_for(clip.source)
        levels = cache[clip.source]
        first, place = clip.source_in / fps / window, int(clip.start / fps / window)
        count, rate = int(clip.length / fps / window), clip.speed
        # One value per timeline window; a clip at its own speed reads its source faster or slower.
        piece = [levels[index] for index in (int(first + i * rate) for i in range(count)) if index < len(levels)]
        curve[place:place + len(piece)] = piece
    return curve


def _rises(levels, back, apart):
    """Indexes where the sound jumps well above the second before it; one per jump, `apart` windows apart."""
    found, last = [], -apart
    for index in range(back, len(levels) - 1):
        if index - last < apart:
            continue
        if levels[index] - statistics.median(levels[index - back:index]) >= RISE_DB:
            found.append(index)
            last = index
    return found


def score(levels, length, window=WINDOW, step=STEP):
    """[(start seconds, score, details)] for every candidate stretch; details: speech share, rises, loudness."""
    size, hop = int(length / window), max(1, int(step / window))
    if len(levels) < size or size <= 0:
        return []
    floor = statistics.median(levels)
    rises = _rises(levels, max(1, int(1.0 / window)), max(1, int(0.5 / window)))
    loud = sorted(levels)[int(len(levels) * 0.9)]
    found = []
    for begin in range(0, len(levels) - size + 1, hop):
        stretch = levels[begin:begin + size]
        speech = sum(1 for level in stretch if level > floor - 3) / size
        count = sum(1 for index in rises if begin <= index < begin + size)
        energy = sum(1 for level in stretch if level >= loud) / size
        value = speech * 2 + min(count, 15) * 0.3 + energy * 3
        found.append((begin * window, value, {'speech': speech, 'rises': count, 'energy': energy}))
    return found


def pick(candidates, length, count):
    """The best `count` candidates that do not overlap, in time order."""
    chosen = []
    for start, value, details in sorted(candidates, key=lambda c: -c[1]):
        if len(chosen) >= count:
            break
        if all(start + length <= other or start >= other + length for other, _, _ in chosen):
            chosen.append((start, value, details))
    return sorted(chosen)


def snap(start, end, pauses, total):
    """Move both ends to the nearest pause within SNAP seconds, keeping the stretch inside 0..total."""
    near = lambda moment: min((p for p in pauses if abs(p - moment) <= SNAP), key=lambda p: abs(p - moment), default=moment)
    new_start, new_end = max(0.0, near(start)), min(total, near(end))
    return (new_start, new_end) if new_end - new_start >= 5 else (max(0.0, start), min(total, end))


def reasons(details, say=str):
    """Plain-language reasons a stretch stands out."""
    found = []
    if details['speech'] >= 0.8:
        found.append(say('neredeyse kesintisiz konuşma'))
    elif details['speech'] >= 0.6:
        found.append(say('yoğun konuşma'))
    if details['rises']:
        found.append(say('sesin yükseldiği {count} an').format(count=details['rises']))
    if details['energy'] >= 0.2:
        found.append(say('videonun en yüksek sesli bölümlerinden'))
    return ', '.join(found) or say('sakin bir bölüm')


def find(timeline, levels_for, length=45, count=5, pauses=()):
    """[(start, end, score, details)] in seconds on the edit, best `count`, in time order."""
    levels = timeline_levels(timeline, levels_for)
    total = len(levels) * WINDOW
    return [(*snap(start, start + length, pauses, total), value, details)
            for start, value, details in pick(score(levels, length), length, count)]
