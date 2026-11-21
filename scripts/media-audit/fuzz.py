"""Random edit sequences checked against what every frame shows.

Each run builds a random multi-track project (speeds, gaps, transitions, captions with word timings, shapes,
markers, a sound track), applies a random chain of edits and, after each edit, compares what every
timeline frame shows with what it showed before, under the rule that edit promises:

  split                  nothing changes
  delete_range(s, e)     frames after e move to s, nothing else changes
  slice(s, e)            the part shows frames s..e of the whole
  ripple_delete          the clip's frames go, later frames on that track move left
  local cut (silences)   the same as deleting those frames from the main track, other tracks following
  plan with no change    nothing changes
  speed there and back   the clip plays the same footage
  trim there and back    nothing changes
  save and load          nothing changes

Usage: python scripts/media-audit/fuzz.py <project root> [runs] [first seed]
Prints JSON: the failures grouped by edit, with the seed and steps that reproduce each.
"""
import json
import math
import random
import sys
import traceback
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()))

from akis import edit_plan, silence_cut, timeline_service, word_captions  # noqa: E402
from akis.timeline_model import CLIP_SPEEDS, Clip, Timeline, Track  # noqa: E402
from akis.timeline_render import TRANSITIONS, duration_frames, transition_of  # noqa: E402
from akis.timeline_slice import FREEZE, TRANSITION_ELAPSED, slice_timeline  # noqa: E402

RATES = [(24, 1), (25, 1), (30, 1), (30000, 1001), (60, 1)]
SOURCES = ['a.mp4', 'b.mp4']
SECONDS = 20
IGNORED_STYLE = {'source_phase', 'speed', 'words', '_shape_offset', '_shape_length', '_shape_seed_id',
                 TRANSITION_ELAPSED, 'transition', 'transition_frames', 'transition_fixed'}


class Broken(Exception):
    pass


ANIMATION = {'on': True}    # a local cut starts a mark again when its start was cut (its entrance replays)


# ---------------------------------------------------------------- what a frame shows
def exact_source(clip, frame):
    return round(clip.source_in + clip.source_phase + (frame - clip.start) * clip.speed, 4)


def lit_word(clip, offset):
    for a, b, index in word_captions.states(clip):
        if a <= offset < b:
            return None if index is None else clip.style['words'][index][2]
    return None


def layer(track, clip, frame, transitions=True):
    offset = frame - clip.start
    look = tuple(sorted((k, json.dumps(v, sort_keys=True)) for k, v in clip.style.items() if k not in IGNORED_STYLE))
    item = {'kind': track.kind, 'source': clip.source, 'text': clip.text, 'volume': clip.volume, 'look': look}
    if clip.source:
        item['at'] = exact_source(clip, frame)
        item['speed'] = clip.speed
    if clip.style.get('words'):     # what is said now; how the line is grouped may change with a cut
        item['lit'] = lit_word(clip, offset)
        item['text'] = ''
    if clip.style.get('shape') and ANIMATION['on']:
        item['shape_frame'] = clip.style.get('_shape_offset', 0) + offset
    if transitions and track.kind == 'video':
        found = transition_of(track, clip)
        elapsed = int(clip.style.get(TRANSITION_ELAPSED, 0))
        if found and offset < found[1] - elapsed:
            item['transition'] = (found[0], found[1], offset + elapsed)
    return tuple(sorted(item.items()))


def frame_view(timeline, frame, tracks=None, transitions=True):
    view = []
    for index, track in enumerate(timeline.tracks):
        if track.muted or (tracks is not None and index not in tracks):
            continue
        if track.clips and all(c.style.get(FREEZE) for c in track.clips):
            continue                                           # the held picture a slice adds under a transition
        for clip in track.clips:
            if clip.start <= frame < clip.end:
                view.append((track.name, layer(track, clip, frame, transitions)))
    return tuple(view)


def views(timeline, length=None, transitions=True):
    length = duration_frames(timeline) if length is None else length
    return [frame_view(timeline, f, transitions=transitions) for f in range(length)]


def first_difference(got, want):
    while got and not got[-1]:
        got = got[:-1]
    while want and not want[-1]:
        want = want[:-1]
    for frame, (a, b) in enumerate(zip(got, want)):
        if a != b:
            return f'kare {frame}: şimdi {a} · beklenen {b}'
    if len(got) != len(want):
        return f'uzunluk {len(got)} · beklenen {len(want)}'
    return None


def check_model(timeline):
    for track in timeline.tracks:
        track.validate()
        for clip in track.clips:
            if clip.source and not 0 <= clip.source_phase < 1:
                raise Broken(f'faz {clip.source_phase}')
            for a, b, _ in clip.style.get('words') or []:
                if b <= a:
                    raise Broken(f'kelime zamanı ters: {(a, b)}')
            for name, points in clip.keyframes.items():
                if any(not 0 <= p['frame'] < clip.length for p in points):
                    raise Broken(f'anahtar kare klibin dışında: {name}')
            if clip.source_length is not None and clip.source_end > clip.source_length:
                raise Broken('kaynağı aşıyor')
    frames = [m.get('frame', 0) for m in timeline.markers]
    if any(f < 0 for f in frames):
        raise Broken('negatif işaretçi')


# ---------------------------------------------------------------- random projects
def random_project(rng):
    num, den = rng.choice(RATES)
    fps = num / den
    length = int(SECONDS * fps)
    main, cursor = [], rng.choice([0, 0, 0, 7])
    for _ in range(rng.randint(2, 6)):
        speed = rng.choice(CLIP_SPEEDS + (1.0,) * 4)
        frames = rng.randint(8, 70)
        source_in = rng.randint(0, length // 3)
        style = {} if speed == 1 else {'speed': speed}
        if rng.random() < .3:
            style.update(transition=rng.choice(TRANSITIONS), transition_frames=rng.choice([4, 6, 10, 15]))
        clip = Clip(rng.choice(SOURCES), cursor, frames, source_in=source_in, source_length=length,
                    volume=rng.choice([1.0, 1.0, 0.5, 0.0]), style=style)
        if clip.source_end > length:
            continue
        main.append(clip)
        cursor = clip.end + rng.choice([0, 0, 0, 3, 12])
    tracks = [Track('video', 'Video', main)]
    total = cursor
    if rng.random() < .7:      # a sound track: one long bed or two separate clips
        if rng.random() < .5:
            sound = [Clip('music.wav', 0, max(1, total), source_length=length)]
        else:
            half = max(2, total // 2)
            sound = [Clip('mic.wav', 0, half, source_length=length),
                     Clip('mic.wav', half, max(1, total - half), source_in=half, source_length=length)]
        tracks.append(Track('audio', 'Ses', sound, muted=rng.random() < .1))
    if rng.random() < .8:      # word-by-word captions over the main cut
        captions, at = [], 0
        while at < total - 4:
            size = rng.randint(4, 30)
            size = min(size, total - at)
            count = rng.randint(1, 4)
            step = max(1, size // count)
            words = [[i * step, min(size, (i + 1) * step), f'k{at}_{i}'] for i in range(count) if i * step < size]
            captions.append(Clip('', at, size, text=' '.join(w[2] for w in words), style={'words': words}))
            at += size + rng.choice([0, 2, 5])
        tracks.append(Track('text', timeline_service.CAPTION_TRACK, captions))
    if rng.random() < .5:      # a hand-drawn mark
        at = rng.randint(0, max(0, total - 10))
        tracks.append(Track('overlay', 'İşaretler', [Clip('', at, rng.randint(5, 40),
                                                         style={'shape': rng.choice(['circle', 'arrow']), 'x': .5, 'y': .5})]))
    markers = [{'frame': rng.randint(0, max(1, total)), 'label': f'm{i}'} for i in range(rng.randint(0, 4))]
    return Timeline(num, den, tracks, sorted(markers, key=lambda m: m['frame']))


def sources_of(timeline):
    fps = timeline.fps_num / timeline.fps_den
    return [{'path': s, 'duration': SECONDS * 1.0} for s in SOURCES] if fps else []


# ---------------------------------------------------------------- edits and their promises
def pick_clip(rng, timeline, kinds=None, media=False):
    found = [(i, c) for i, t in enumerate(timeline.tracks) if kinds is None or t.kind in kinds
             for c in t.clips if (c.source or not media)]
    return rng.choice(found) if found else (None, None)


def edit_split(rng, timeline):
    index, clip = pick_clip(rng, timeline)
    if clip is None or clip.length < 2:
        return None
    frame = rng.randint(clip.start + 1, clip.end - 1)
    track = timeline.tracks[index]
    found = transition_of(track, clip)
    inside = found and frame < clip.start + found[1] - int(clip.style.get(TRANSITION_ELAPSED, 0))
    before = views(timeline, transitions=not inside)
    head = views(timeline)[:frame]
    track.split(clip.id, frame)
    problem = first_difference(views(timeline, transitions=not inside), before)
    if not problem and inside:   # split inside the transition: it ends at the split, the part before is as it was
        problem = first_difference(views(timeline)[:frame], head)
    return f'split {track.name} @{frame}' + (' (geçiş içinde)' if inside else ''), problem


def edit_delete_range(rng, timeline):
    total = duration_frames(timeline)
    if total < 4:
        return None
    start = rng.randint(0, total - 2)
    end = rng.randint(start + 1, min(total, start + 40))
    before = views(timeline, transitions=False)
    markers = deepcopy(timeline.markers)
    timeline_service.delete_range(timeline, start, end)
    want = before[:start] + before[end:]
    problem = first_difference(views(timeline, len(want), transitions=False), want)
    if not problem:
        expected = [dict(m, frame=m['frame'] - (end - start) if m['frame'] >= end else m['frame'])
                    for m in markers if not start <= m['frame'] < end]
        if timeline.markers != expected:
            problem = f'işaretçiler {timeline.markers} · beklenen {expected}'
    return f'delete_range {start}-{end}', problem


def edit_slice(rng, timeline):
    total = duration_frames(timeline)
    if total < 4:
        return None
    start = rng.randint(0, total - 2)
    end = rng.randint(start + 1, total)
    before = views(timeline)
    part = slice_timeline(timeline, start, end)
    check_model(part)
    problem = first_difference(views(part, end - start), before[start:end])
    if not problem and duration_frames(part) != end - start:
        problem = f'parça uzunluğu {duration_frames(part)} · beklenen {end - start}'
    return f'slice {start}-{end}', problem          # the project itself does not change


def edit_ripple_delete(rng, timeline):
    index, clip = pick_clip(rng, timeline, kinds=('video',))
    if clip is None or len(timeline.tracks[index].clips) < 2:
        return None
    track = timeline.tracks[index]
    before = [frame_view(timeline, f, tracks={index}, transitions=False) for f in range(duration_frames(timeline))]
    start, end = clip.start, clip.end
    timeline.ripple_delete(index, clip.id)
    after = [frame_view(timeline, f, tracks={index}, transitions=False) for f in range(duration_frames(timeline) + 1)]
    want = before[:start] + before[end:]
    return f'ripple_delete {track.name} {start}-{end}', first_difference(after[:len(want)], want)


def timeline_ranges_of_silence(timeline, source_index, a, b):
    """Timeline frames of the main track that play source seconds [a, b) of source `source_index`."""
    fps = timeline.fps_num / timeline.fps_den
    path = SOURCES[source_index]
    ranges = []
    for clip in edit_plan.primary_track(timeline).clips:
        if clip.source != path:
            continue
        lo, hi = clip.source_bounds
        x, y = max(lo, a * fps), min(hi, b * fps)
        if x <= lo + 1e-3 and y >= hi - 1e-3:
            continue                       # a silence over a whole clip leaves it alone (keep_segments)
        if y - x > 1e-6:
            ranges.append((clip.timeline_frame(x), clip.timeline_frame(y)))
    return ranges


def edit_local_cut(rng, timeline):
    main = edit_plan.primary_track(timeline)
    candidates = [c for c in main.clips if c.length >= 6]
    if not candidates:
        return None
    clip = rng.choice(candidates)
    first = rng.randint(clip.start + 1, clip.end - 3)
    last = rng.randint(first + 1, min(clip.end - 1, first + 20))
    fps = timeline.fps_num / timeline.fps_den
    a, b = [round((clip.source_in + clip.source_phase + (f - clip.start) * clip.speed) / fps, 6) for f in (first, last)]
    index = SOURCES.index(clip.source)
    removed = sorted(timeline_ranges_of_silence(timeline, index, a, b))
    if any(abs(x - round(x)) > 1e-3 or abs(y - round(y)) > 1e-3 for x, y in removed):
        return None    # the silence does not fall on frame edges in some other use of the source
    sources = sources_of(timeline)
    if any(round(y) - round(x) < 1 for x, y in removed):
        return None
    expected = deepcopy(timeline)
    for x, y in reversed(removed):
        timeline_service.delete_range(expected, round(x), round(y))
    segments = edit_plan.current_segments(timeline, sources, keep=True)
    new, cuts = silence_cut.keep_segments(segments, {index: [(a, b)]}, margin=0, min_keep=0)
    if not cuts:
        return None
    result = edit_plan.apply_plan(timeline, sources, {'segments': new})
    check_model(result)
    ANIMATION['on'] = False
    try:
        problem = _compare_cut(timeline, expected, result, main)
    finally:
        ANIMATION['on'] = True
    timeline.tracks, timeline.markers = result.tracks, result.markers
    return f'local_cut {a:.3f}-{b:.3f}s kaynak {index} (çizelge {removed})', problem


def _compare_cut(timeline, expected, result, main):
    main_index = timeline.tracks.index(main)
    end = max(c.end for c in edit_plan.primary_track(expected).clips)
    want = [frame_view(expected, f, tracks={main_index}, transitions=False) for f in range(end)]
    got = [frame_view(result, f, tracks={main_index}, transitions=False) for f in range(len(want))]
    problem = first_difference(got, want)
    if not problem:
        for i, track in enumerate(timeline.tracks):     # captions and marks follow the picture
            if track.kind not in ('text', 'overlay'):
                continue
            want = [frame_view(expected, f, tracks={i}, transitions=False) for f in range(end)]
            got = [frame_view(result, f, tracks={i}, transitions=False) for f in range(len(want))]
            if track.kind == 'text':
                # A word whose moment was cut leaves the caption (the word before stays lit over the silence
                # after it); a caption whose words were all cut goes, its silent tail with it.
                said = {dict(item)['lit'] for frame in got for _, item in frame if 'lit' in dict(item)}
                want = [w if g and all(dict(item).get('lit') in said for _, item in w) else g
                        for g, w in zip(got, want)]
            problem = first_difference(got, want)
            if problem:
                problem = f'{track.name}: {problem}'
                break
    return problem


def edit_noop_plan(rng, timeline):
    sources = sources_of(timeline)
    segments = edit_plan.current_segments(timeline, sources, keep=True)
    if not segments:
        return None
    end = max(c.end for c in edit_plan.primary_track(timeline).clips)   # a recut ends with the main video
    before = views(timeline, end)
    result = edit_plan.apply_plan(timeline, sources, {'segments': segments})
    check_model(result)
    problem = first_difference(views(result, end), before)
    kept = [m for m in timeline.markers if m['frame'] <= end]
    if not problem and result.markers != kept:
        problem = f'işaretçiler {result.markers} · beklenen {kept}'
    return 'plan (değişiklik yok)', problem


def edit_speed_round_trip(rng, timeline):
    index, clip = pick_clip(rng, timeline, kinds=('video', 'audio'), media=True)
    if clip is None:
        return None
    old = clip.speed
    new = rng.choice([s for s in CLIP_SPEEDS if s != old])
    footage = (clip.source_in, clip.source_phase, clip.source_frames)
    try:
        timeline_service.set_clip_speed(timeline, (index, clip.id), new)
    except ValueError:
        return None
    try:
        timeline_service.set_clip_speed(timeline, (index, clip.id), old)
    except ValueError as error:
        return f'speed {old}→{new}→{old}', f'geri alınamadı: {error}'
    now = (clip.source_in, clip.source_phase, clip.source_frames)
    # Whole timeline frames cannot hold every footage length at every speed: a frame either way per step.
    slack = 1 + math.ceil(max(new, old))
    same = now[:2] == footage[:2] and abs(now[2] - footage[2]) <= slack
    return f'speed {old}→{new}→{old}', None if same else f'oynatılan kaynak {now} · önce {footage}'


def edit_trim_round_trip(rng, timeline):
    index, clip = pick_clip(rng, timeline)
    if clip is None or clip.length < 3:
        return None
    track = timeline.tracks[index]
    before = views(timeline)
    side = rng.choice(['start', 'end'])
    if side == 'start':
        old = clip.start
        new = rng.randint(clip.start + 1, clip.end - 1)
        track.trim_start(clip.id, new)
        track.trim_start(clip.id, old)
    else:
        old = clip.end
        new = rng.randint(clip.start + 1, clip.end - 1)
        track.trim_end(clip.id, new)
        track.trim_end(clip.id, old)
    return f'trim_{side} {old}→{new}→{old} ({track.name})', first_difference(views(timeline), before)


def edit_save_load(rng, timeline):
    before = views(timeline)
    data = json.loads(json.dumps(timeline.to_dict()))
    loaded = Timeline.from_dict(data)
    problem = first_difference(views(loaded), before)
    again = json.loads(json.dumps(loaded.to_dict()))
    if not problem and Timeline.from_dict(again).to_dict() != again:
        problem = 'ikinci kayıt farklı'
    timeline.tracks, timeline.markers = loaded.tracks, loaded.markers
    return 'kaydet/aç', problem


EDITS = [edit_split, edit_split, edit_delete_range, edit_slice, edit_ripple_delete, edit_local_cut,
         edit_local_cut, edit_noop_plan, edit_speed_round_trip, edit_trim_round_trip, edit_save_load]


def run(seed, steps=8):
    rng = random.Random(seed)
    timeline = random_project(rng)
    done = []
    for _ in range(steps):
        edit = rng.choice(EDITS)
        snapshot = deepcopy(timeline)
        try:
            outcome = edit(rng, timeline)
        except (ValueError, Broken) as error:
            name = edit.__name__
            if isinstance(error, ValueError) and str(error) in ('Invalid trim', 'Slip exceeds source duration'):
                timeline = snapshot
                continue
            return edit.__name__, f'{type(error).__name__}: {error}', done + [name], snapshot
        except Exception as error:   # noqa: BLE001 - a crash is a finding too
            return edit.__name__, f'çöktü: {type(error).__name__}: {error}\n{traceback.format_exc(limit=3)}', \
                done + [edit.__name__], snapshot
        if outcome is None:
            continue
        label, problem = outcome
        done.append(label)
        try:
            check_model(timeline)
        except (ValueError, Broken) as error:
            problem = problem or f'model bozuk: {error}'
        if problem:
            return edit.__name__, problem, done, snapshot
    return None


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    for seed in range(first, first + runs):
        failure = run(seed)
        if failure:
            edit, problem, steps, _ = failure
            found[edit].append({'seed': seed, 'steps': steps, 'problem': problem[:600]})
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()),
              'groups': {edit: {'count': len(cases), 'examples': cases[:4]}
                         for edit, cases in sorted(found.items(), key=lambda item: -len(item[1]))}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


if __name__ == '__main__':
    raise SystemExit(main())
