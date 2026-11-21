"""Random edits exported by FFmpeg, the sound read back and compared with the timeline model.

Every source frame's sound is a tone of its own pitch (16 pitches in a band that names the file), so the
pitch heard in an output frame says which file and which source moment is playing. For random projects
(speed, split, trim, delete, local cut, slice, clip volume, muted tracks, a music track) each output
frame must carry the sound of every clip the model says is heard there, from the right source moment
(within the tempo filter's window), at the clip's volume, and nothing from clips that should be silent.

Usage: python scripts/media-audit/audio_fuzz.py <project root> [runs] [first seed]
"""
import json
import math
import random
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()))

from akis import edit_plan, silence_cut, timeline_service  # noqa: E402
from akis.media_service import MediaService  # noqa: E402
from akis.timeline_model import CLIP_SPEEDS, Clip, Timeline, Track  # noqa: E402
from akis.timeline_render import TimelineRenderer, duration_frames  # noqa: E402
from akis.timeline_slice import FREEZE, slice_timeline  # noqa: E402

RATE = 48000
BANDS = {'a': 500, 'b': 2600, 'm': 4900}      # lowest pitch of each file's band; 16 steps of 125 Hz
STEP = 125
PITCHES = 16
LEVEL = 0.08                                  # each tone's amplitude: a few summed stay far below the limiter
FPS_OF = {'a': (30, 1), 'b': (25, 1), 'm': (30, 1)}
SECONDS = 14
W, H = 32, 18
MEDIA = MediaService(shutil.which('ffmpeg'))
EXPORT_LIMIT = 180        # seconds; an export here takes well under one, so a stuck FFmpeg is reported, not waited on


def ff(args):
    done = MEDIA.run(['-v', 'error', *args], timeout=EXPORT_LIMIT)   # TimeoutExpired names the stuck command
    if done.returncode:
        raise RuntimeError(done.stderr)
    return done.stdout


def tones(name):
    """The file's sound: source frame i (at its own frame rate) is a tone of pitch i % 16 in its band."""
    num, den = FPS_OF[name]
    rate = num / den
    t = np.arange(int(SECONDS * RATE)) / RATE
    index = np.floor(t * rate + 1e-9).astype(int) % PITCHES
    frequency = BANDS[name] + index * STEP
    phase = 2 * np.pi * np.cumsum(frequency) / RATE
    return (LEVEL * np.sin(phase)).astype(np.float32)


def make_source(folder, name):
    wav = folder / f'{name}.f32'
    wav.write_bytes(tones(name).tobytes())
    num, den = FPS_OF[name]
    if name == 'm':
        out = folder / 'm.wav'
        ff(['-y', '-f', 'f32le', '-ar', str(RATE), '-ac', '1', '-i', str(wav), '-c:a', 'pcm_s16le', str(out)])
    else:
        out = folder / f'{name}.mp4'
        ff(['-y', '-f', 'lavfi', '-i', f'color=c=gray:size={W}x{H}:rate={num}/{den}:d={SECONDS}',
            '-f', 'f32le', '-ar', str(RATE), '-ac', '1', '-i', str(wav),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', '-shortest', str(out).replace('.mp4', '.mov')])
        out = Path(str(out).replace('.mp4', '.mov'))
    return str(out)


def read_sound(path):
    data = ff(['-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-'])
    return np.frombuffer(data, dtype=np.float32)


def heard(sound, start, end):
    """{file: (pitch index, amplitude)} for every band with sound in samples [start, end)."""
    piece = sound[start:end]
    if len(piece) < 256:
        return {}
    window = np.hanning(len(piece))
    spectrum = np.abs(np.fft.rfft(piece * window)) * 2 / window.sum()
    freqs = np.fft.rfftfreq(len(piece), 1 / RATE)
    found = {}
    for name, low in BANDS.items():
        band = (freqs >= low - STEP / 2) & (freqs < low + (PITCHES - 0.5) * STEP)
        if not band.any():
            continue
        peak = np.argmax(spectrum * band)
        # Level from the band's whole energy: at a high speed several pitches play one after another in
        # one frame, each for part of it. A Hann window spreads a tone over 1.5 bins' worth of energy.
        amplitude = float(np.sqrt(np.sum((spectrum * band) ** 2) / 1.5))
        if amplitude > LEVEL * 0.05:
            found[name] = (int(round((freqs[peak] - low) / STEP)) % PITCHES, float(amplitude))
    return found


def expected(timeline, frame, paths):
    """{file: (set of possible pitch indexes, volume)} of the clips heard at `frame`."""
    fps = timeline.fps_num / timeline.fps_den
    want = {}
    for track in timeline.tracks:
        if track.muted or track.kind not in ('video', 'audio'):
            continue
        for clip in track.clips:
            if not clip.start <= frame < clip.end or not clip.source or clip.style.get(FREEZE):
                continue
            name = paths[clip.source]
            num, den = FPS_OF[name]
            rate = num / den
            first = (clip.source_in + clip.source_phase + (frame - clip.start) * clip.speed) / fps
            last = first + clip.speed / fps
            indexes = set(range(int(first * rate) - 2, int(last * rate) + 3))      # tempo filter window
            pitches, volume = want.get(name, (set(), 0.0))
            want[name] = (pitches | {i % PITCHES for i in indexes}, volume + clip.volume)
    return want


def edges(timeline):
    """Frames next to a clip's start or end, where the sound fades in or out over a few milliseconds. A
    slowed-down clip's last ~60 ms fade out too: time stretching blends its last window with silence."""
    fps = timeline.fps_num / timeline.fps_den
    near = set()
    for track in timeline.tracks:
        for clip in track.clips:
            tail = max(2, math.ceil(0.07 * fps)) if clip.speed < 1 else 2
            near.update(range(clip.start - 2, clip.start + 2))
            near.update(range(clip.end - tail, clip.end + 2))
    return near


def random_project(rng, sources):
    num, den = rng.choice([(30, 1), (25, 1), (24, 1), (60, 1)])
    fps = num / den
    clips, cursor = [], rng.choice([0, 0, 6])
    for _ in range(rng.randint(2, 4)):
        path = rng.choice([sources['a'], sources['b']])
        speed = rng.choice(CLIP_SPEEDS + (1.0,) * 3)
        length = rng.randint(int(fps * 0.4), int(fps * 1.5))
        style = {} if speed == 1 else {'speed': speed}
        source_frames = int((SECONDS - 1) * fps)
        clip = Clip(path, cursor, length, source_in=rng.randint(0, int(fps * 3)), source_length=source_frames,
                    volume=rng.choice([1.0, 1.0, 0.5, 0.0]), style=style)
        if clip.source_end > source_frames:
            continue
        clips.append(clip)
        cursor = clip.end + rng.choice([0, 0, int(fps * 0.3)])
    tracks = [Track('video', 'Video', clips)]
    if rng.random() < .6:
        music_speed = rng.choice([1.0, 1.0, 1.5, 0.75])
        style = {} if music_speed == 1 else {'speed': music_speed}
        tracks.append(Track('audio', 'Müzik', [Clip(sources['m'], rng.randint(0, 10), max(2, cursor - 10),
                                                    source_in=rng.randint(0, 20), volume=rng.choice([1.0, 0.5]),
                                                    style=style)], muted=rng.random() < .35))
    return Timeline(num, den, tracks)


def random_edits(rng, timeline, names):
    steps = []
    for _ in range(rng.randint(1, 4)):
        what = rng.choice(['split', 'trim_start', 'trim_end', 'speed', 'delete', 'cut', 'volume'])
        main = timeline.tracks[0]
        if not main.clips:
            break
        clip = rng.choice(main.clips)
        try:
            if what == 'split' and clip.length > 2:
                main.split(clip.id, rng.randint(clip.start + 1, clip.end - 1))
            elif what == 'trim_start' and clip.length > 2:
                main.trim_start(clip.id, rng.randint(clip.start + 1, clip.end - 1))
            elif what == 'trim_end' and clip.length > 2:
                main.trim_end(clip.id, rng.randint(clip.start + 1, clip.end - 1))
            elif what == 'speed':
                timeline_service.set_clip_speed(timeline, (0, clip.id), rng.choice(CLIP_SPEEDS))
            elif what == 'volume':
                timeline_service.set_clip_volume(timeline, (0, clip.id), rng.choice([0.0, 0.3, 1.0]))
            elif what == 'delete':
                total = duration_frames(timeline)
                a = rng.randint(0, max(0, total - 3))
                timeline_service.delete_range(timeline, a, min(total, a + rng.randint(1, 12)))
            elif what == 'cut' and clip.length > 4:
                fps = timeline.fps_num / timeline.fps_den
                sources = [{'path': p, 'duration': float(SECONDS)} for p in names]
                first = rng.randint(clip.start + 1, clip.end - 2)
                a = (clip.source_in + clip.source_phase + (first - clip.start) * clip.speed) / fps
                b = a + rng.randint(2, 10) / fps
                segments = edit_plan.current_segments(timeline, sources, keep=True)
                new, cuts = silence_cut.keep_segments(segments, {names.index(clip.source): [(a, b)]}, margin=0, min_keep=0)
                if cuts:
                    result = edit_plan.apply_plan(timeline, sources, {'segments': new})
                    timeline.tracks, timeline.markers = result.tracks, result.markers
            else:
                continue
            steps.append(what)
        except ValueError:
            continue
    if rng.random() < .3:
        total = duration_frames(timeline)
        if total > 10:
            a = rng.randint(0, total // 2)
            timeline = slice_timeline(timeline, a, rng.randint(a + 6, total))
            steps.append('slice')
    return timeline, steps


def check(timeline, sound, paths):
    fps = timeline.fps_num / timeline.fps_den
    total = duration_frames(timeline)
    near = edges(timeline)
    wrong = []
    expected_samples = round(total / fps * RATE)
    if abs(len(sound) - expected_samples) > RATE * 0.05:
        wrong.append(f'ses uzunluğu {len(sound) / RATE:.3f} sn · beklenen {total / fps:.3f} sn')
    for frame in range(total):
        if frame in near:
            continue
        a, b = round(frame / fps * RATE), round((frame + 1) / fps * RATE)
        middle, span = (a + b) // 2, max(1200, b - a)          # at least 25 ms, centred on the frame
        got = heard(sound, middle - span // 2, middle + span // 2)
        want = expected(timeline, frame, paths)
        for name, (pitches, volume) in want.items():
            if volume < 0.05:
                if name in got and got[name][1] > LEVEL * 0.2:
                    wrong.append(f'kare {frame}: {name} sessiz olmalıydı, düzey {got[name][1] / LEVEL:.2f}')
                continue
            if name not in got:
                wrong.append(f'kare {frame}: {name} duyulmuyor (beklenen düzey {volume:.2f})')
                continue
            pitch, amplitude = got[name]
            if pitch not in pitches:
                wrong.append(f'kare {frame}: {name} kaynak anı yanlış (perde {pitch}, beklenen {sorted(pitches)})')
            ratio = amplitude / (LEVEL * min(volume, 1.0))
            if not 0.5 < ratio < 1.6:
                wrong.append(f'kare {frame}: {name} düzeyi {ratio:.2f}× beklenen')
        for name, (pitch, amplitude) in got.items():
            if name not in want and amplitude > LEVEL * 0.2:
                wrong.append(f'kare {frame}: {name} duyulmamalıydı (düzey {amplitude / LEVEL:.2f})')
    return wrong


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    failures = []
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        print('audio_fuzz: making the tone sources', file=sys.stderr, flush=True)
        sources = {name: make_source(root, name) for name in BANDS}
        paths = {path: name for name, path in sources.items()}
        renderer = TimelineRenderer(MEDIA, (W, H))
        for seed in range(first, first + runs):
            rng = random.Random(seed)
            timeline = random_project(rng, sources)
            timeline, steps = random_edits(rng, timeline, [sources['a'], sources['b']])
            if duration_frames(timeline) < 4:
                continue
            out = root / f'out{seed}.mp4'
            print(f'audio_fuzz: seed {seed}', file=sys.stderr, flush=True)   # the CI log shows where a run stops
            stuck = []

            def unstick():
                process = MEDIA._process
                if process is not None:
                    stuck.append(' '.join(map(str, process.args))[-1500:])
                    process.kill()
            watchdog = threading.Timer(EXPORT_LIMIT, unstick)
            watchdog.start()
            try:
                renderer.export(timeline, out)
            except Exception as error:   # noqa: BLE001
                problem = f'dışa aktarma {EXPORT_LIMIT} saniyede bitmedi (FFmpeg takıldı): {stuck[0]}' if stuck \
                    else f'dışa aktarma hatası: {error}'[:300]
                failures.append({'seed': seed, 'steps': steps, 'problem': [problem]})
                continue
            finally:
                watchdog.cancel()
            if stuck:
                failures.append({'seed': seed, 'steps': steps, 'problem': [f'FFmpeg takıldı: {stuck[0]}']})
                continue
            try:
                heard = read_sound(out)
            except Exception as error:   # noqa: BLE001   (a stuck read names its command)
                failures.append({'seed': seed, 'steps': steps, 'problem': [f'ses okunamadı: {error}'[:600]]})
                continue
            wrong = check(timeline, heard, paths)
            if wrong:
                failures.append({'seed': seed, 'steps': steps, 'fps': [timeline.fps_num, timeline.fps_den],
                                 'clips': [[t.kind, t.muted, [(c.start, c.length, paths.get(c.source), c.source_in, c.speed,
                                                               round(c.source_phase, 3), c.volume) for c in t.clips]]
                                           for t in timeline.tracks],
                                 'problem': wrong[:6], 'count': len(wrong)})
    print(json.dumps({'runs': runs, 'failed': len(failures), 'failures': failures}, indent=1, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
