"""Random edits checked against the smooth-playback copy's pieces and the live sound targets.

Rules:
  pieces       chunk_bounds covers the edit with no gap or overlap, never starts a piece inside an
               entrance, and the pieces joined show the same frames as the whole edit
  reuse        after a random edit, a stored piece is reused (same piece_key) only if it shows exactly
               what it showed before; a piece whose picture changed always gets a new key
  sound        audio_targets at every frame names each clip heard there, at the clip's source moment
               (within a frame), rate and volume, and nothing else
Usage: python scripts/media-audit/preview_fuzz.py <project root> [runs] [first seed]
"""
import json
import random
import sys
import traceback
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from akis import chunk_preview, timeline_service  # noqa: E402
from akis.timeline_render import duration_frames  # noqa: E402
from akis.timeline_slice import slice_timeline, transition_intervals  # noqa: E402
import fuzz  # noqa: E402

EDITS = [fuzz.edit_split, fuzz.edit_delete_range, fuzz.edit_ripple_delete, fuzz.edit_local_cut,
         fuzz.edit_speed_round_trip, fuzz.edit_trim_round_trip]


class Broken(Exception):
    pass


def check_pieces(timeline, limit, seconds):
    total = duration_frames(timeline)
    if total < 2:
        return []
    bounds = chunk_preview.chunk_bounds(timeline, total, limit, seconds)
    if bounds[0][0] != 0 or bounds[-1][1] != total or any(a[1] != b[0] or a[0] >= a[1] for a, b in zip(bounds, bounds[1:])):
        raise Broken(f'parçalar kurguyu tam örtmüyor: {bounds[:8]} / {total}')
    entrances = transition_intervals(timeline)
    for a, _ in bounds[1:]:
        if any(x < a < y for x, y in entrances):
            raise Broken(f'parça bir geçişin içinde başlıyor: {a} {entrances}')
    whole = fuzz.views(timeline, total)
    joined = []
    for a, b in bounds:
        joined += fuzz.views(slice_timeline(timeline, a, b), b - a)
    problem = fuzz.first_difference(joined, whole)
    if problem:
        raise Broken(f'parçalar birleşince farklı: {problem[:300]}')
    return bounds


def picture(part, length):
    """What a piece shows: its frames without the sound (audio tracks, clip volumes), mixed separately."""
    return [tuple((name, tuple(kv for kv in item if kv[0] != 'volume')) for name, item in frame
                  if dict(item)['kind'] != 'audio') for frame in fuzz.views(part, length)]


def check_reuse(rng, timeline, limit, seconds):
    bounds = check_pieces(timeline, limit, seconds)
    if not bounds:
        return
    size, settings = (360, 640), {'brightness': 0}
    before = {}
    for a, b in bounds:
        part = slice_timeline(timeline, a, b)
        before[chunk_preview.piece_key(part, size, dict(settings, output_frames=b - a))] = picture(part, b - a)   # as export_pieces
    edited = deepcopy(timeline)
    edit = rng.choice(EDITS)
    try:
        if edit(rng, edited) is None:
            return
    except Exception:          # noqa: BLE001 - the edit checker covers the edits themselves
        return
    total = duration_frames(edited)
    if total < 2:
        return
    for a, b in check_pieces(edited, limit, seconds):
        part = slice_timeline(edited, a, b)
        key = chunk_preview.piece_key(part, size, dict(settings, output_frames=b - a))
        if key in before and before[key] != picture(part, b - a):
            raise Broken(f'{edit.__name__} sonrası {a}-{b} parçası değişti ama eski önizleme parçası yeniden kullanılıyor')


def check_sound(timeline):
    fps = timeline.fps_num / timeline.fps_den
    for frame in range(duration_frames(timeline)):
        speed = 1.0
        got = sorted((t.track_index, t.source, t.rate, t.volume, t.position)
                     for t in timeline_service.audio_targets(timeline, frame, speed))
        want = []
        for index, track in enumerate(timeline.tracks):
            if track.muted or track.kind not in ('audio', 'video'):
                continue
            for clip in track.clips:
                if clip.source and clip.volume > 0 and clip.start <= frame < clip.end:
                    exact = (clip.source_in + clip.source_phase + (frame - clip.start) * clip.speed) / fps * 1000
                    want.append((index, clip.source, speed * clip.speed, clip.volume, exact))
        want.sort()
        if len(got) != len(want) or any(g[:4] != w[:4] or abs(g[4] - w[4]) > 1000 / fps + 1 for g, w in zip(got, want)):
            raise Broken(f'kare {frame}: ses hedefleri {got} · beklenen {want}')


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    for seed in range(first, first + runs):
        rng = random.Random(seed)
        timeline = fuzz.random_project(rng)
        for _ in range(rng.randint(0, 3)):
            try:
                rng.choice(EDITS)(rng, timeline)
            except Exception:      # noqa: BLE001
                pass
        limit, seconds = rng.choice([1, 2, 3, 120]), rng.choice([0.2, 0.5, 1.0, 8.0])
        for name, check in (('pieces', lambda: check_pieces(timeline, limit, seconds)),
                            ('reuse', lambda: check_reuse(rng, timeline, limit, seconds)),
                            ('sound', lambda: check_sound(timeline))):
            try:
                check()
            except Broken as error:
                found[name].append({'seed': seed, 'problem': str(error)[:500]})
            except Exception as error:   # noqa: BLE001
                found[name].append({'seed': seed, 'problem': f'çöktü: {type(error).__name__}: {error}',
                                    'where': traceback.format_exc(limit=-3)[-600:]})
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()),
              'groups': {name: {'count': len(cases), 'examples': cases[:4]} for name, cases in found.items()}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


if __name__ == '__main__':
    raise SystemExit(main())
