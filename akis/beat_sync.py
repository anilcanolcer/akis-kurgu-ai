"""Put the cuts of the main video on the beat of the music.

The music's beats are found from its low end (kick drum, bass): an onset curve is made from the rise in
loudness, the tempo is the repeat distance that curve agrees with best (60-180 BPM), and the grid is laid
where the strongest onsets fall. Each cut between two main clips then moves to the nearest beat, if one
is close; the clip before it gets a little shorter or longer. The music itself is not touched.
"""
import array
import math
import os
import subprocess
import sys

RATE = 4000             # samples per second read from the music
HOP = 0.01              # seconds per onset value
MIN_BPM, MAX_BPM = 60, 180
MAX_SHIFT = 0.5         # seconds a cut may move to reach a beat
MIN_LENGTH = 0.3        # seconds a shortened clip keeps at least


def onsets_from_pcm(data, rate=RATE, hop=HOP):
    """How sharply the loudness rises in each `hop` (0 where it falls)."""
    samples = array.array('h')
    samples.frombytes(data[:len(data) - len(data) % 2])
    if sys.byteorder != 'little':
        samples.byteswap()
    step = max(1, round(rate * hop))
    energy = [math.sqrt(sum(n * n for n in samples[i:i + step]) / max(1, len(samples[i:i + step])))
              for i in range(0, len(samples), step)]
    return [0.0] + [max(0.0, b - a) for a, b in zip(energy, energy[1:])]


def read_onsets(executable, source, start=0.0, duration=None, runner=subprocess.run):
    """Onset curve of a music file's low end from `start` seconds; [] when it cannot be read."""
    command = [executable, '-v', 'error', '-ss', f'{max(0.0, start):.3f}', '-i', str(source)]
    if duration:
        command += ['-t', f'{duration:.3f}']
    command += ['-vn', '-af', 'lowpass=f=180', '-ac', '1', '-ar', str(RATE), '-f', 's16le', 'pipe:1']
    try:
        result = runner(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=300,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return onsets_from_pcm(result.stdout) if result.returncode == 0 else []


def beats(onsets, hop=HOP):
    """Beat times in seconds from an onset curve; [] when no steady beat can be told."""
    if len(onsets) < 4 / hop or not any(onsets):
        return []
    mean = sum(onsets) / len(onsets)
    curve = [value - mean for value in onsets]
    best, best_lag = 0.0, 0
    for lag in range(round(60 / MAX_BPM / hop), round(60 / MIN_BPM / hop) + 1):
        score = sum(curve[i] * curve[i + lag] for i in range(len(curve) - lag)) / (len(curve) - lag)
        if score > best * 1.02:          # prefer the faster tempo when two agree almost equally well
            best, best_lag = score, lag
    if not best_lag or best <= 0:
        return []
    phase = max(range(best_lag), key=lambda offset: sum(onsets[offset::best_lag]))
    return [index * hop for index in range(phase, len(onsets), best_lag)]


def music_clip(timeline):
    """The first clip on a sounding audio track, or None."""
    for track in timeline.tracks:
        if track.kind == 'audio' and not track.muted and track.clips:
            return min(track.clips, key=lambda clip: clip.start)
    return None


def snap_segments(segments, beat_times, durations, max_shift=MAX_SHIFT, min_length=MIN_LENGTH):
    """Main-cut segments (edit_plan.current_segments) with each cut moved to the nearest beat.

    beat_times: seconds on the timeline. durations: source lengths by source index.
    Returns (new segments, number of cuts moved).
    """
    result, cursor, moved = [], 0.0, 0
    for index, segment in enumerate(segments):
        piece = dict(segment)
        end_at = cursor + piece['end'] - piece['start']
        if index < len(segments) - 1 and beat_times:
            target = min(beat_times, key=lambda beat: abs(beat - end_at))
            shift = target - end_at
            longest = durations[piece['source']] - piece['end']
            shortest = (piece['end'] - piece['start']) - min_length
            shift = max(-shortest, min(longest, shift))
            if abs(target - end_at) <= max_shift and abs(shift) > 1e-3:
                piece['end'] = round(piece['end'] + shift, 4)
                moved += 1
        result.append(piece)
        cursor += piece['end'] - piece['start']
    return result, moved
