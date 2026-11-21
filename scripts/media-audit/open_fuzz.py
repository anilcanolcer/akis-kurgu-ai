"""Damaged project settings opened in the real main window (offscreen).

A valid project (with or without a main video) is saved, then its settings are damaged at random the way a
hand edit, another program or a cut-off sync can: the "state", "publish" or "ai_prompt" parts get the wrong
type, an out-of-range number, a missing or unknown value. The window opens it with its own open path.
Rules:
  - nothing raises out of the window
  - a refused file names the problem in plain words (one of the project service's own messages), never
    Python's ("'list' object has no attribute 'get'", "could not convert string to float"…), and the project
    that was open stays exactly as it was
  - an opened file leaves every setting in its range: speed one of the offered speeds, an offered canvas and
    profile, colour values -50…50 and the same on the sliders, sound switches true/false, the old in/out
    range inside the video, publish texts as text; and saving it again then opening that gives the same
Usage: python scripts/media-audit/open_fuzz.py <project root> [runs] [first seed]
"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from akis import i18n, project_service  # noqa: E402
from akis.timeline_model import Clip, Timeline, Track  # noqa: E402
from main import MainWindow  # noqa: E402


class Broken(Exception):
    pass


PLAIN = (project_service.NOT_A_PROJECT, project_service.NEWER_PROJECT, project_service.DAMAGED_PROJECT_TIMELINE,
         'Projede kullanılan kaynak video bulunamadı.')
REPAIRED = getattr(project_service, 'REPAIRED_SETTINGS', '\0').split(':')[0]
WRONG = [None, '', 'abc', '12', '1e400', 12, -7, 3.7, 10 ** 30, -10 ** 30, 1e308, -1e308, float('nan'), float('inf'),
         True, False, [], [1, 2], {}, {'a': 1}, 'Kare 1:1', '2.00×', '1.5', '9:16', 'English']
FIELDS = ['source', 'duration', 'start', 'end', 'aspect', 'brightness', 'contrast', 'saturation', 'speed',
          'export_profile', 'audio_level', 'audio_denoise', 'audio_duck', 'ai_title', 'ai_caption', 'ai_hashtags']


def video(folder):
    path = Path(folder) / 'kaynak.mp4'
    subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=160x90:r=30:d=2',
                    '-f', 'lavfi', '-i', 'sine=d=2', '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                    str(path)], check=True)
    return path


def base_document(rng, with_source):
    state = {'source': str(SOURCE) if with_source else '', 'duration': 2.0 if with_source else 0.0,
             'start': 0.0, 'end': 2.0 if with_source else 0.0, 'aspect': rng.choice(i18n.ASPECTS),
             'brightness': rng.randint(-50, 50), 'contrast': rng.randint(-50, 50), 'saturation': rng.randint(-50, 50),
             'speed': rng.choice(i18n.SPEEDS), 'export_profile': rng.choice(i18n.EXPORT_PROFILES),
             'audio_level': rng.random() < 0.5, 'audio_denoise': rng.random() < 0.5, 'audio_duck': rng.random() < 0.5,
             'ai_title': 'Başlık', 'ai_caption': 'Açıklama', 'ai_hashtags': '#deneme'}
    clips = [Clip(str(SOURCE), 0, 60)] if with_source else [Clip('', 0, 60, text='Yazı ğüş')]
    timeline = Timeline(tracks=[Track('video' if with_source else 'text', 'İz', clips)])
    return project_service.make_document(state, timeline, {'title': 'Yayın', 'caption': 'Metin', 'hashtags': '#a'},
                                         'İstek')


def damage(rng, document):
    """1–3 random damages; returns what was done (for the report)."""
    done = []
    for _ in range(rng.randint(1, 3)):
        kind = rng.random()
        if kind < 0.55 and isinstance(document.get('state'), dict):
            field = rng.choice(FIELDS + ['unknown_field'])
            if rng.random() < 0.15:
                document['state'].pop(field, None)
                done.append(f'state.{field} silindi')
            else:
                value = rng.choice(WRONG)
                document['state'][field] = value
                done.append(f'state.{field}={value!r}')
        elif kind < 0.65:
            value = rng.choice([None, [], 'metin', 5, True])
            document['state'] = value
            done.append(f'state={value!r}')
        elif kind < 0.85:
            if rng.random() < 0.4:
                value = rng.choice([None, [], 'metin', 5])
                document['publish'] = value
                done.append(f'publish={value!r}')
            else:
                if not isinstance(document.get('publish'), dict):
                    document['publish'] = {}
                field = rng.choice(['title', 'caption', 'hashtags'])
                value = rng.choice([None, 5, [], {'x': 1}, True, 'tamam'])
                document['publish'][field] = value
                done.append(f'publish.{field}={value!r}')
        else:
            value = rng.choice([None, 5, [], {'x': 1}, True, 'tamam'])
            document['ai_prompt'] = value
            done.append(f'ai_prompt={value!r}')
    return done


def snapshot(window):
    return json.dumps({'timeline': window.multitrack.to_dict(), 'state': asdict(window.state),
                       'path': window.project_path, 'title': window.publish_title.text(),
                       'prompt': window.ai_prompt.toPlainText()}, sort_keys=True, default=repr)


def check_open_state(window):
    s = window.state
    problems = []
    if not isinstance(s.speed, float) or s.speed not in i18n.SPEEDS:
        problems.append(f'hız {s.speed!r}')
    if s.aspect not in i18n.ASPECTS:
        problems.append(f'tuval {s.aspect!r}')
    if s.export_profile not in i18n.EXPORT_PROFILES:
        problems.append(f'profil {s.export_profile!r}')
    for name, slider in (('brightness', window.brightness), ('contrast', window.contrast), ('saturation', window.saturation)):
        value = getattr(s, name)
        if not isinstance(value, int) or isinstance(value, bool) or not -50 <= value <= 50 or value != slider.value():
            problems.append(f'{name} {value!r} (kaydırıcı {slider.value()})')
    for name in ('audio_level', 'audio_denoise', 'audio_duck'):
        if not isinstance(getattr(s, name), bool):
            problems.append(f'{name} {getattr(s, name)!r}')
    for name in ('start', 'end', 'duration'):
        value = getattr(s, name)
        if not isinstance(value, float) or not math.isfinite(value):
            problems.append(f'{name} {value!r}')
    # The window keeps the old in/out range at least 0.05 s long, even when it starts at the very end.
    if not problems and not (0 <= s.start <= s.end <= max(s.duration, 0.0) + 0.05 + 1e-6):
        problems.append(f'aralık {s.start}–{s.end} / {s.duration}')
    for name in ('source', 'ai_title', 'ai_caption', 'ai_hashtags'):
        if not isinstance(getattr(s, name), str):
            problems.append(f'{name} {getattr(s, name)!r}')
    adjustments = window.render_adjustments()
    for name, value in adjustments.items():
        if name != 'audio' and (not isinstance(value, (int, float)) or not math.isfinite(value)):
            problems.append(f'dışa aktarma ayarı {name}={value!r}')
    return problems


def session(seed, window, folder):
    rng = random.Random(seed)
    document = base_document(rng, with_source=rng.random() < 0.3)
    done = damage(rng, document)
    path = Path(folder) / f'p{seed}.akis.json'
    path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    before = snapshot(window)
    shown = []
    errors = []

    def message(kind):
        def show(*args, **kwargs):
            shown.append((kind, str(args[2]) if len(args) > 2 else ''))
            return QMessageBox.StandardButton.Ok if kind != 'question' else QMessageBox.StandardButton.No
        return show
    hook = sys.excepthook
    sys.excepthook = lambda *exc: errors.append(''.join(traceback.format_exception(*exc))[-600:])
    try:
        with patch.object(QMessageBox, 'critical', message('critical')), \
                patch.object(QMessageBox, 'warning', message('warning')), \
                patch.object(QMessageBox, 'information', message('information')), \
                patch.object(QMessageBox, 'question', message('question')):
            opened = window.load_project_document(str(path), str(path))
            for _ in range(5):
                app.processEvents()
    finally:
        sys.excepthook = hook
    if errors:
        raise Broken(f'yakalanmayan hata ({done}): {errors[0]}')
    if not opened:
        refusals = [text for kind, text in shown if kind == 'critical']
        details = [text.split(': ', 1)[1] if ': ' in text else text for text in refusals]
        if not details or not all(d in PLAIN or d.startswith('Proje dosyası bozuk') for d in details):
            raise Broken(f'anlaşılmaz ret ({done}): {refusals or shown}')
        if snapshot(window) != before:
            raise Broken(f'reddedilen dosya açık projeyi değiştirdi ({done})')
        return 'ret'
    problems = check_open_state(window)
    if problems:
        raise Broken(f'açıldı ama ayarlar geçersiz ({done}): {problems}')
    told = [text for kind, text in shown if text.startswith(REPAIRED)]
    unreadable = [text for kind, text in shown if kind == 'critical' or
                  (kind in ('warning', 'information') and not text.startswith(REPAIRED)
                   and not text.startswith('Projede kullanılan şu medya dosyaları bulunamadı'))]
    if unreadable:
        raise Broken(f'açılırken beklenmeyen ileti ({done}): {unreadable}')
    if told and re.search(r'\b(state|publish|ai_prompt|brightness|speed|source)\b', told[0]):
        raise Broken(f'onarım iletisi programın iç adlarını gösteriyor: {told[0]}')
    again = Path(folder) / f'p{seed}-again.akis.json'
    window.write_project(str(again))
    first = snapshot(window)
    if not window.load_project_document(str(again), str(again)):
        raise Broken(f'yeniden kaydedilen proje açılmadı ({done}): {shown[-1:]}')
    if json.loads(snapshot(window))['state'] != json.loads(first)['state']:
        raise Broken(f'kaydet-aç ayarları değiştirdi ({done})')
    return 'açıldı'


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    outcomes = defaultdict(int)
    window = MainWindow()
    patch.object(window.preview, 'request').start()
    window.apply_language('tr')
    try:
        for seed in range(first, first + runs):
            try:
                outcomes[session(seed, window, TMP.name)] += 1
            except Broken as error:
                found['kural'].append({'seed': seed, 'problem': str(error)[:600]})
            except Exception as error:   # noqa: BLE001
                found['çökme'].append({'seed': seed, 'problem': f'{type(error).__name__}: {error}'[:300],
                                       'where': traceback.format_exc(limit=-4)[-900:]})
    finally:
        window._close_confirmed = True
        window.close()
        app.processEvents()
    kinds = defaultdict(int)       # the same problem once, whatever the seed and the damage that led to it
    seeds = {}
    for cases in found.values():
        for case in cases:
            text = case['problem']
            head = text.split(' (', 1)[0]
            tail = text.rsplit(': ', 1)[-1] if head == 'açıldı ama ayarlar geçersiz' else \
                (text.split('Proje açılamadı: ', 1)[-1][:70] if 'Proje açılamadı' in text else text[-80:])
            key = f'{head}: {re.sub(r"[-0-9.]+", "#", tail)}'
            kinds[key] += 1
            seeds.setdefault(key, case['seed'])
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()), 'outcomes': dict(outcomes),
              'kinds': {f'{key} [seed {seeds[key]}]': count for key, count in sorted(kinds.items(), key=lambda item: -item[1])},
              'groups': {name: {'count': len(cases), 'examples': cases[:6]} for name, cases in found.items()}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


TMP = tempfile.TemporaryDirectory()
SOURCE = video(TMP.name)
patch('akis.app_support.recovery_dir', return_value=Path(TMP.name) / 'recovery').start()

if __name__ == '__main__':
    raise SystemExit(main())
