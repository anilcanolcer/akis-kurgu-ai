"""Random edits rendered by FFmpeg, every output frame read back and compared with the timeline model.

Each source frame carries its own number (three grey blocks, base 8) and a fourth block naming the file,
so a decoded output frame says which file and which source frame it shows. For random projects built
from edits (speed, split, trim, delete, local cut, slice) the exported frames, and still previews of a few
random frames, must show what Clip.source_frame names for the top picture at that frame. Frames inside a
transition are skipped (they blend two pictures).

Usage: python scripts/media-audit/render_fuzz.py <project root> [runs] [first seed]
"""
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()))

from akis import edit_plan, silence_cut, timeline_service  # noqa: E402
from akis.media_service import MediaService  # noqa: E402
from akis.timeline_model import CLIP_SPEEDS, Clip, Timeline, Track  # noqa: E402
from akis.timeline_render import TRANSITIONS, TimelineRenderer, duration_frames, outgoing_hold, transition_of  # noqa: E402
from akis.timeline_slice import FREEZE, slice_timeline  # noqa: E402

W, H = 64, 36
FRAMES = 400
TAGS = {'a': 235, 'b': 128, 'c': 70}          # fourth block: which file
RATES = {'a': (30, 1), 'b': (30, 1), 'c': (25, 1)}

MEDIA = MediaService(shutil.which('ffmpeg'))


def ff(args):
    done = MEDIA.run(['-v', 'error', *args])
    if done.returncode:
        raise RuntimeError(done.stderr)
    return done.stdout


def make_source(folder, name):
    raw = bytearray()
    for i in range(FRAMES):
        frame = np.zeros((H, W), dtype=np.uint8)
        digits = (i // 64, (i // 8) % 8, i % 8)
        for k, digit in enumerate(digits):
            frame[:, k * 16:(k + 1) * 16] = 20 + digit * 30
        frame[:, 48:] = TAGS[name]
        raw += frame.tobytes()
    source = folder / f'{name}.gray'
    source.write_bytes(bytes(raw))
    out = folder / f'{name}.mp4'
    num, den = RATES[name]
    ff(['-y', '-f', 'rawvideo', '-pixel_format', 'gray', '-video_size', f'{W}x{H}', '-framerate', f'{num}/{den}',
        '-i', str(source), '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono', '-shortest',
        '-c:v', 'libx264', '-crf', '0', '-g', '12', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(out)])
    return str(out)


def read_frames(path):
    data = np.frombuffer(ff(['-i', str(path), '-vf', f'scale={W}:{H}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'gray', '-']),
                         dtype=np.uint8).reshape(-1, H, W).astype(int)
    return [decode(frame) for frame in data]


def decode(frame):
    tag = frame[4:-4, 52:60].mean()
    if tag < 40:
        return None                                  # black: nothing there
    name = min(TAGS, key=lambda n: abs(TAGS[n] - tag))
    digits = [int(round((frame[4:-4, k * 16 + 4:k * 16 + 12].mean() - 20) / 30)) for k in range(3)]
    return name, digits[0] * 64 + digits[1] * 8 + digits[2]


def expected(timeline, frame, paths):
    """(file, source frame) of the top picture at `frame`, None for black, 'skip' inside a transition."""
    shown = None
    for track in timeline.tracks:
        if track.muted or track.kind not in ('video', 'overlay'):
            continue
        for clip in track.clips:
            hold = outgoing_hold(track, clip) if track.kind == 'video' else 0
            if clip.end <= frame < clip.end + hold:
                shown = 'skip'                       # held under the next clip's transition
            if not clip.start <= frame < clip.end or not clip.source:
                continue
            found = transition_of(track, clip)
            elapsed = int(clip.style.get('_transition_elapsed', 0))
            if found and frame - clip.start < found[1] - elapsed:
                shown = 'skip'
                continue
            name = paths[clip.source]
            if clip.style.get(FREEZE):
                exact = clip.source_in
            else:
                exact = clip.source_in + clip.source_phase + (frame - clip.start) * clip.speed
            fps = timeline.fps_num / timeline.fps_den
            num, den = RATES[name]
            source_rate = num / den
            if abs(source_rate - fps) < 1e-9:
                picture = int(exact + 1e-6)
            else:   # a source off the timeline's grid is put on the grid first: the picture on screen
                picture = int(int(exact + 1e-6) / fps * source_rate + 1e-6)   # at that grid moment
            shown = (name, picture)
    return shown


def random_project(rng, sources):
    num, den = rng.choice([(30, 1), (30, 1), (25, 1), (24, 1), (60, 1)])
    clips, cursor = [], rng.choice([0, 0, 5])
    for _ in range(rng.randint(2, 4)):
        path = rng.choice(list(sources.values()))
        speed = rng.choice(CLIP_SPEEDS + (1.0,) * 3)
        length = rng.randint(6, 40)
        style = {} if speed == 1 else {'speed': speed}
        if rng.random() < .25:
            style.update(transition=rng.choice(TRANSITIONS), transition_frames=rng.choice([4, 6]))
        clip = Clip(path, cursor, length, source_in=rng.randint(0, 120), source_length=FRAMES * num // 30 - 30, style=style)
        if clip.source_end > clip.source_length:
            continue
        clips.append(clip)
        cursor = clip.end + rng.choice([0, 0, 4])
    tracks = [Track('video', 'Video', clips)]
    if rng.random() < .3 and cursor > 10:
        at = rng.randint(0, cursor - 6)
        tracks.append(Track('overlay', 'B-roll', [Clip(sources['c'], at, rng.randint(4, 20), source_in=rng.randint(0, 100),
                                                         style={'speed': rng.choice([1.0, 0.5, 2.0])})]))
    return Timeline(num, den, tracks)


def random_edits(rng, timeline, names):
    steps = []
    for _ in range(rng.randint(1, 4)):
        what = rng.choice(['split', 'trim_start', 'trim_end', 'speed', 'delete', 'cut'])
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
            elif what == 'delete':
                total = duration_frames(timeline)
                a = rng.randint(0, max(0, total - 3))
                timeline_service.delete_range(timeline, a, min(total, a + rng.randint(1, 10)))
            elif what == 'cut' and clip.length > 4:
                fps = timeline.fps_num / timeline.fps_den
                sources = [{'path': p, 'duration': 12.0} for p in names]
                first = rng.randint(clip.start + 1, clip.end - 2)
                a = (clip.source_in + clip.source_phase + (first - clip.start) * clip.speed) / fps
                b = a + rng.randint(1, 8) / fps
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
        if total > 6:
            a = rng.randint(0, total // 2)
            timeline = slice_timeline(timeline, a, rng.randint(a + 3, total))
            steps.append('slice')
    return timeline, steps


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    failures = []
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        sources = {name: make_source(root, name) for name in TAGS}
        paths = {path: name for name, path in sources.items()}
        renderer = TimelineRenderer(MEDIA, (W, H))
        for seed in range(first, first + runs):
            rng = random.Random(seed)
            timeline = random_project(rng, sources)
            timeline, steps = random_edits(rng, timeline, list(sources.values()))
            total = duration_frames(timeline)
            if total < 1:
                continue
            out = root / f'out{seed}.mp4'
            try:
                renderer.export(timeline, out)
            except Exception as error:   # noqa: BLE001
                failures.append({'seed': seed, 'steps': steps, 'problem': f'dışa aktarma hatası: {error}'[:300]})
                continue
            got = read_frames(out)
            wrong = []
            if len(got) != total:
                wrong.append(f'kare sayısı {len(got)} · beklenen {total}')
            for frame in range(min(total, len(got))):
                want = expected(timeline, frame, paths)
                if want != 'skip' and got[frame] != want:
                    wrong.append(f'kare {frame}: {got[frame]} · beklenen {want}')
            for frame in rng.sample(range(total), min(2, total)):
                want = expected(timeline, frame, paths)
                still = root / f'still{seed}.png'
                try:
                    renderer.preview(timeline, frame, still)
                except Exception as error:   # noqa: BLE001
                    wrong.append(f'önizleme {frame} hatası: {error}'[:200])
                    continue
                shown = read_frames(still)[0]
                if want != 'skip' and shown != want:
                    wrong.append(f'önizleme kare {frame}: {shown} · beklenen {want}')
            if wrong:
                failures.append({'seed': seed, 'steps': steps, 'fps': [timeline.fps_num, timeline.fps_den],
                                 'clips': [[t.kind, [(c.start, c.length, paths.get(c.source), c.source_in,
                                                      c.speed, round(c.source_phase, 3)) for c in t.clips]]
                                           for t in timeline.tracks],
                                 'problem': wrong[:5], 'count': len(wrong)})
    print(json.dumps({'runs': runs, 'failed': len(failures), 'failures': failures}, indent=1, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
