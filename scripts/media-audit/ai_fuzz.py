"""Random AI replies and transcripts fed through the plan parser and the speech-based tools.

Rules checked on every run:
  plan          parse_plan only refuses with ValueError; what it accepts is in range; applying it (and the
                plan review's keep) gives a valid timeline or a ValueError, never another exception
  captions      captions from a transcript lie on clips of their recording, never overlap, and every word
                caption has words inside it (an empty word list would draw the whole sentence as text)
  fillers,      cuts are in order, never overlap, and cutting them gives a valid timeline
  retakes
  speakers      markers land inside the edit
  beat, punch   snapped cuts and punch-ins stay inside their clips' footage
Inputs follow the shapes the providers return (akis.ai_providers.group_words) with random values.

Usage: python scripts/media-audit/ai_fuzz.py <project root> [runs] [first seed]
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

from akis import beat_sync, caption_service, edit_plan, emphasis, fillers, plan_review, retakes, silence_cut, speakers  # noqa: E402
from akis.timeline_render import TRANSITIONS, duration_frames  # noqa: E402
import fuzz  # noqa: E402

WORDS = ['şey', 'yani', 'eee', 'ıı', 'hmm', 'merhaba', 'bugün', 'size', 'sizlere', 'bir', 'konu', 'anlatacağım',
         'işte', 'bu', 'video', 'çok', 'güzel', 'olacak', 'ee', 'mmm', 'Şey,', 'Yani…', 'tamam.', 'evet!', 'nasıl?']


class Broken(Exception):
    pass


def garbage(rng):
    return rng.choice([None, True, 'abc', '', [], {}, -1, 1e9, 'NaN', '1.5', 3, 0.0, -0.4, float('inf'), '∞', 'fade'])


def random_number(rng, low, high):
    return rng.choice([rng.uniform(low, high), rng.uniform(low, high), round(rng.uniform(low, high), 2),
                       rng.randint(int(low), int(high)), garbage(rng)])


def random_plan(rng, durations):
    plan = {}
    if rng.random() < .8:
        plan['segments'] = []
        for _ in range(rng.randint(0, 8)):
            item = {'source': rng.choice([0, 1, 0, 1, rng.randint(-1, 3), garbage(rng)]),
                    'start': random_number(rng, -1, max(durations) + 2),
                    'end': random_number(rng, -1, max(durations) + 2)}
            if rng.random() < .3:
                item['transition'] = rng.choice(list(TRANSITIONS) + ['none', '', 'wipe', None, 5])
            if rng.random() < .05:
                item = garbage(rng)
            plan['segments'].append(item)
    if rng.random() < .5:
        plan['texts'] = [{'text': rng.choice(['Başlık', '🔥🔥', '', ' çok güzel ', garbage(rng)]),
                          'start': random_number(rng, -1, 30), 'end': random_number(rng, -1, 30),
                          'x': random_number(rng, -1, 2), 'y': random_number(rng, -1, 2),
                          'size': rng.choice(['small', 'large', 'huge', None]), 'color': rng.choice(['red', 'mor', None])}
                         for _ in range(rng.randint(0, 5))]
    if rng.random() < .4:
        plan['marks'] = [{'type': rng.choice(['circle', 'arrow', 'star', None]), 'source': rng.choice([0, 1, None, 7]),
                          'start': random_number(rng, -1, 20), 'end': rng.choice([None, random_number(rng, -1, 20)]),
                          'x': random_number(rng, -1, 2), 'y': random_number(rng, -1, 2),
                          'size': random_number(rng, 0, 2), 'from_x': rng.choice([None, 0.1, 'a']), 'from_y': rng.choice([None, 0.9])}
                         for _ in range(rng.randint(0, 4))]
    for key, make in (('captions', lambda: rng.choice([True, False, 'yes'])),
                      ('remove', lambda: rng.choice(['captions', ['texts', 'marks', 'x'], 5, 'MARKS '])),
                      ('color', lambda: rng.choice([{'brightness': random_number(rng, -80, 80), 'hue': 3}, 'warm', None])),
                      ('speed', lambda: random_number(rng, 0, 3)),
                      ('aspect', lambda: rng.choice(['9:16', '16:9', '3:2', 1])),
                      ('volume', lambda: random_number(rng, -1, 2)),
                      ('music_volume', lambda: random_number(rng, -1, 2)),
                      ('summary', lambda: rng.choice(['Kısa kurgu', None, 5])),
                      ('hashtags', lambda: rng.choice([['#a', '', 5], 'x', None]))):
        if rng.random() < .25:
            plan[key] = make()
    return plan


def wrap(rng, plan):
    text = json.dumps(plan, ensure_ascii=False, allow_nan=True)
    choice = rng.random()
    if choice < .2:
        text = '```json\n' + text + '\n```'
    elif choice < .3:
        text = 'Tabii, işte plan: {not json} ' + text + ' Umarım beğenirsiniz {}.'
    elif choice < .38:
        text = json.dumps({'plan': plan}, ensure_ascii=False, allow_nan=True)
    elif choice < .43:
        text = text[:rng.randint(0, len(text))]                  # cut off mid-reply
    return text


def check_plan(rng, timeline):
    sources = [{'path': p, 'duration': float(fuzz.SECONDS), 'transcript': rng.choice([None, [], random_transcript(rng)]),
                'size': (1920, 1080)} for p in fuzz.SOURCES]
    durations = [s['duration'] for s in sources]
    text = wrap(rng, random_plan(rng, durations))
    try:
        plan = edit_plan.parse_plan(text, durations, current_duration=rng.choice([None, 0, 12.0]))
    except ValueError:
        return 'plan reddedildi'
    for segment in plan.get('segments', ()):
        if not (0 <= segment['source'] < len(durations) and 0 <= segment['start'] < segment['end'] <= durations[segment['source']]
                and segment['end'] - segment['start'] >= edit_plan.MIN_SEGMENT_SECONDS - 1e-9):
            raise Broken(f'kabul edilen parça aralık dışında: {segment}')
    for item in plan.get('texts', ()):
        if not 0 <= item['start'] < item['end'] or not (0 <= item['x'] <= 1 and 0 <= item['y'] <= 1):
            raise Broken(f'kabul edilen yazı aralık dışında: {item}')
    for item in plan.get('marks', ()):
        if not 0 <= item['start'] < item['end'] <= durations[item['source']]:
            raise Broken(f'kabul edilen işaret aralık dışında: {item}')
    for key in ('volume', 'music_volume'):
        if key in plan and not 0 <= plan[key] <= 1:
            raise Broken(f'{key} aralık dışında: {plan[key]}')
    plans = [plan]
    names = [name for name, _ in plan_review.parts(plan)] if plan_review.parts(plan) else []
    if names:
        plans.append(plan_review.keep(plan, set(rng.sample(names, rng.randint(0, len(names))))))
    for one in plans:
        try:
            result = edit_plan.apply_plan(timeline, sources, one, canvas=rng.choice([None, (1080, 1920), (1920, 1080)]))
        except ValueError:
            continue
        fuzz.check_model(result)
        video_end = max((c.end for t in result.tracks if t.kind == 'video' for c in t.clips), default=0)
        for track in result.tracks:
            if track.name in (edit_plan.TEXT_TRACK, edit_plan.MARK_TRACK) or track.name.startswith(edit_plan.MARK_TRACK):
                for clip in track.clips:
                    if clip.end > video_end:
                        raise Broken(f'{track.name}: AI öğesi videonun sonunu aşıyor ({clip.end} > {video_end})')
        edit_plan.describe(one, result)
    return 'plan uygulandı'


def random_transcript(rng):
    words, at = [], rng.uniform(0, 1)
    for _ in range(rng.randint(0, 60)):
        length = rng.choice([0.0, 0.05, 0.2, 0.4, 0.8])
        words.append({'text': rng.choice(WORDS), 'start': round(at, 3), 'end': round(at + length, 3)})
        at += length + rng.choice([0.0, 0.05, 0.1, 0.7, 1.5])
        if rng.random() < .05:
            at -= 0.3                                   # Whisper's word times can overlap a little
    if not words:
        return []
    from akis.ai_providers import group_words
    return group_words(words)


def check_captions(rng, timeline):
    transcript = random_transcript(rng)
    source = rng.choice(fuzz.SOURCES)
    look = rng.choice(['klasik', 'vurgu', 'kutu'])
    before = len(timeline.tracks)
    caption_service.caption_track(timeline, source, transcript, look)
    if len(timeline.tracks) == before:
        return 'altyazı yok'
    track = timeline.tracks[-1]
    track.validate()
    pictures = [c for t in timeline.tracks if t.kind == 'video' and not t.muted for c in t.clips if c.source == source]
    for clip in track.clips:
        if not any(p.start <= clip.start < p.end for p in pictures):
            raise Broken(f'altyazı kendi kaydının klibi üzerinde değil: {clip.start}-{clip.end} "{clip.text}"')
        if look != 'klasik':
            words = clip.style.get('words')
            if not words:
                raise Broken(f'kelime altyazısında kelime yok, cümle düz yazı çıkar: {clip.start}-{clip.end} "{clip.text}"')
            if any(not (0 <= a < clip.length and a < b) for a, b, _ in words):
                raise Broken(f'kelime zamanı klibin dışında: {words} / {clip.length}')
    return 'altyazı'


def check_word_cuts(rng, timeline):
    transcript = random_transcript(rng)
    source = rng.randrange(len(fuzz.SOURCES))
    tool = rng.choice(['fillers', 'retakes'])
    if tool == 'fillers':
        cuts = [(a, b) for a, b, _ in fillers.find(fillers.words_of(transcript))]
    else:
        cuts = [(a, b) for a, b, _, _ in retakes.find(transcript)]
    if any(b <= a for a, b in cuts) or any(cuts[i][1] > cuts[i + 1][0] for i in range(len(cuts) - 1)):
        raise Broken(f'{tool}: kesimler sırasız ya da çakışık: {cuts[:6]}')
    if not cuts:
        return f'{tool} yok'
    sources = fuzz.sources_of(timeline)
    segments = edit_plan.current_segments(timeline, sources, keep=True)
    new, removed = silence_cut.keep_segments(segments, {source: cuts}, margin=0, whole=True)
    if not removed:
        return f'{tool} kesmedi'
    try:
        result = edit_plan.apply_plan(timeline, sources, {'segments': new})
    except ValueError:
        return f'{tool} hepsini kesti'
    fuzz.check_model(result)
    return tool


def check_speakers(rng, timeline):
    transcript = random_transcript(rng)
    words = fillers.words_of(transcript)
    spans = speakers.utterances(words)
    found = [(a, b, rng.choice([0, 1]), t) for a, b, t in spans]
    fps = timeline.fps_num / timeline.fps_den
    main = edit_plan.primary_track(timeline)
    clips = [c for c in main.clips if c.source == fuzz.SOURCES[0]]
    total = duration_frames(timeline)
    for marker in speakers.markers(found, clips, fps):
        if not 0 <= marker['frame'] <= total:
            raise Broken(f'konuşmacı işaretçisi videonun dışında: {marker} / {total}')
    return 'konuşmacı'


def check_beats_and_punches(rng, timeline):
    sources = fuzz.sources_of(timeline)
    segments = edit_plan.current_segments(timeline, sources, keep=True)
    beats = sorted(rng.uniform(0, 20) for _ in range(rng.randint(0, 40)))
    snapped, _ = beat_sync.snap_segments(segments, beats, [s['duration'] for s in sources])
    for piece in snapped:
        if not 0 <= piece['start'] < piece['end'] <= fuzz.SECONDS + 1e-6:
            raise Broken(f'ritme oturtulan parça kaynağın dışında: {piece}')
    try:
        result = edit_plan.apply_plan(timeline, sources, {'segments': snapped})
        fuzz.check_model(result)
    except ValueError:
        pass
    moments = {p: sorted(rng.uniform(0, fuzz.SECONDS) for _ in range(rng.randint(0, 10))) for p in fuzz.SOURCES}
    punched = deepcopy(timeline)
    emphasis.apply(punched, moments)
    for clip in edit_plan.primary_track(punched).clips:
        for first, length in clip.style.get('punch', ()):
            if not clip.source_in <= first < clip.source_end or length < 1:
                raise Broken(f'vurgu yakınlaştırması klibin dışında: {first} / {clip.source_in}-{clip.source_end}')
        emphasis.zoom_filter(clip, timeline.fps_num, timeline.fps_den, 0, 1080, 1920)
    return 'ritim ve vurgu'


CHECKS = [check_plan, check_plan, check_plan, check_captions, check_captions, check_word_cuts, check_word_cuts,
          check_speakers, check_beats_and_punches]


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    for seed in range(first, first + runs):
        rng = random.Random(seed)
        timeline = fuzz.random_project(rng)
        if rng.random() < .5:              # some projects carry earlier edits
            for _ in range(rng.randint(1, 3)):
                edit = rng.choice([fuzz.edit_split, fuzz.edit_speed_round_trip, fuzz.edit_delete_range])
                try:
                    edit(rng, timeline)
                except Exception:          # noqa: BLE001 - the edit checker covers these
                    pass
        timeline.tracks = [t for t in timeline.tracks if t.kind != 'text']
        if rng.random() < .3:              # the same recording again on a second video track (a B-roll cut)
            from akis.timeline_model import Clip, Track
            fps = timeline.fps_num / timeline.fps_den
            at = rng.randint(0, 60)
            timeline.tracks.append(Track('video', 'B-roll', [Clip(rng.choice(fuzz.SOURCES), at, rng.randint(10, 80),
                                                                  source_in=rng.randint(0, int(fps * 5)),
                                                                  source_length=int(fuzz.SECONDS * fps))]))
        check = rng.choice(CHECKS)
        try:
            check(rng, deepcopy(timeline))
        except Broken as error:
            found[check.__name__].append({'seed': seed, 'problem': str(error)[:500]})
        except Exception as error:   # noqa: BLE001 - a crash is a finding
            found[check.__name__].append({'seed': seed, 'problem': f'çöktü: {type(error).__name__}: {error}',
                                          'where': traceback.format_exc(limit=-3)[-700:]})
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()),
              'groups': {name: {'count': len(cases), 'examples': cases[:4]} for name, cases in found.items()}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


if __name__ == '__main__':
    raise SystemExit(main())
