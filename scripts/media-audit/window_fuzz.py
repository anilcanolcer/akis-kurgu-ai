"""Random editing sessions in the real main window, checked against undo and redo.

A random project is opened in MainWindow (offscreen); a random series of the editor's own actions follows:
split, trim to the playhead, delete, ripple delete, range delete, clip volume, speed and framing, add and
remove a track, and mouse drags on the track view (move, move to another track, trim either edge).
Rules:
  - no action raises; the timeline stays valid after each one
  - every action that changed the timeline is one undo step: undoing all of them gives back the project
    as it was opened, redoing all of them gives back the final project, and every state in between
  - saving the project and opening it again gives the same timeline
Usage: python scripts/media-audit/window_fuzz.py <project root> [runs] [first seed]
"""
import json
import os
import random
import sys
import tempfile
import traceback
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(ROOT)

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

import fuzz  # noqa: E402
from akis import project_service  # noqa: E402
from akis.timeline_model import CLIP_SPEEDS, Timeline  # noqa: E402
from main import MainWindow  # noqa: E402


class Broken(Exception):
    pass


def state(window):
    return json.dumps(window.multitrack.to_dict(), sort_keys=True)


def track_y(index):
    return 30 + index * 43 + 20


def pick(rng, window, kinds=None):
    found = [(i, c) for i, t in enumerate(window.multitrack.tracks) if kinds is None or t.kind in kinds for c in t.clips]
    if not found:
        return None
    index, clip = rng.choice(found)
    window.multitrack_view.selected, window.multitrack_view.selected_track = (index, clip.id), index
    return index, clip


def action(rng, window):
    """One random editor action; returns its name."""
    view = window.multitrack_view
    name = rng.choice(['split', 'trim_left', 'trim_right', 'delete', 'ripple', 'range', 'volume', 'speed', 'fit',
                       'add_track', 'remove_track', 'drag_move', 'drag_trim_start', 'drag_trim_end', 'drag_track'])
    if name in ('split', 'trim_left', 'trim_right'):
        picked = pick(rng, window)
        if not picked:
            return None
        _, clip = picked
        view.playhead = rng.randint(clip.start, clip.end)
        {'split': window.split_clip, 'trim_left': window.trim_left, 'trim_right': window.trim_right}[name]()
    elif name in ('delete', 'ripple'):
        if not pick(rng, window):
            return None
        (window.delete_clip if name == 'delete' else window.ripple_delete)()
    elif name == 'range':
        total = max((c.end for t in window.multitrack.tracks for c in t.clips), default=0)
        if total < 2:
            return None
        a = rng.randint(0, total - 1)
        view.set_range((a, rng.randint(a + 1, total)))
        window.delete_range()
    elif name == 'volume':
        if not pick(rng, window, ('video', 'audio')):
            return None
        with patch.object(QInputDialog, 'getInt', return_value=(rng.choice([0, 35, 100]), True)):
            window.set_clip_volume()
    elif name == 'speed':
        if not pick(rng, window, ('video', 'audio', 'overlay')):
            return None
        with patch.object(QInputDialog, 'getItem', return_value=(f'{rng.choice(CLIP_SPEEDS):g}×', True)):
            window.set_clip_speed()
    elif name == 'fit':
        if not pick(rng, window, ('video', 'overlay')):
            return None
        from akis import clip_fit
        labels = [window.ui_text(label) for label, _, _ in clip_fit.CHOICES]
        with patch.object(QInputDialog, 'getItem', return_value=(rng.choice(labels), True)):
            window.set_clip_fit()
    elif name == 'add_track':
        with patch.object(QInputDialog, 'getItem', return_value=(rng.choice(['video', 'audio', 'text', 'overlay']), True)):
            window.add_track()
    elif name == 'remove_track':
        if not window.multitrack.tracks:
            return None
        view.selected_track = rng.randrange(len(window.multitrack.tracks))
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            window.remove_track()
    else:
        picked = pick(rng, window)
        if not picked:
            return None
        index, clip = picked
        view.selected = None
        x0 = {'drag_move': (view.x_for(clip.start) + view.x_for(clip.end)) // 2,
              'drag_track': (view.x_for(clip.start) + view.x_for(clip.end)) // 2,
              'drag_trim_start': view.x_for(clip.start) + 2, 'drag_trim_end': view.x_for(clip.end) - 2}[name]
        if not 100 <= x0 < view.width() or (name != 'drag_trim_end' and clip.length * view.zoom < 24):
            return None
        y0 = track_y(index)
        y1 = track_y(rng.randrange(len(window.multitrack.tracks))) if name == 'drag_track' else y0
        QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(int(x0), y0))
        for _ in range(rng.randint(1, 3)):
            QTest.mouseMove(view, QPoint(int(max(101, x0 + rng.randint(-60, 60))), y1))
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(int(max(101, x0 + rng.randint(-60, 60))), y1))
    app.processEvents()
    return name


def session(seed, steps=12):
    rng = random.Random(seed)
    timeline = fuzz.random_project(rng)
    for track in timeline.tracks:                     # media the window can find on disk
        for clip in track.clips:
            if clip.source:
                clip.source = str(MEDIA / Path(clip.source).name)
    window = MainWindow()
    try:
        window.apply_language('tr')
        patch.object(window.preview, 'request').start()
        window.show_timeline(Timeline.from_dict(timeline.to_dict()))
        window.clear_history()
        window.multitrack_view.zoom = rng.choice([2.0, 4.0, 8.0])
        window.multitrack_view.resize(1600, 400)
        states, done = [state(window)], []
        for _ in range(steps):
            before = state(window)
            undo_depth = len(window._undo_stack)
            name = action(rng, window)
            if name is None:
                continue
            for track in window.multitrack.tracks:
                track.validate()
            fuzz.check_model(window.multitrack)
            after = state(window)
            if after != before:
                if len(window._undo_stack) != undo_depth + 1:
                    raise Broken(f'{name}: zaman çizelgesi değişti ama geri alma adımı eklenmedi '
                                 f'({undo_depth} → {len(window._undo_stack)})')
                states.append(after)
                done.append(name)
            elif len(window._undo_stack) != undo_depth:
                raise Broken(f'{name}: hiçbir şey değişmedi ama geri alma adımı eklendi')
        for expected in reversed(states[:-1]):
            window.undo()
            if state(window) != expected:
                raise Broken(f'geri alma sırasında beklenen duruma dönülmedi (adımlar: {done})')
        if window.undo():
            raise Broken('fazladan geri alma adımı var')
        for expected in states[1:]:
            window.redo()
            if state(window) != expected:
                raise Broken(f'yineleme sırasında beklenen duruma ulaşılmadı (adımlar: {done})')
        project = Path(TMP.name) / f'p{seed}.akis'
        document = project_service.make_document({'source': ''}, window.multitrack, {}, '')
        project_service.save(project, document)
        loaded, _, _ = project_service.load_project(project)
        again = Timeline.from_dict(loaded['timeline'])
        if json.dumps(again.to_dict(), sort_keys=True) != states[-1] and \
                json.dumps(Timeline.from_dict(json.loads(states[-1])).to_dict(), sort_keys=True) != json.dumps(again.to_dict(), sort_keys=True):
            raise Broken('kaydedip açınca zaman çizelgesi farklı')
        return done
    finally:
        window._close_confirmed = True
        window.close()
        app.processEvents()


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    for seed in range(first, first + runs):
        try:
            session(seed)
        except Broken as error:
            found['kural'].append({'seed': seed, 'problem': str(error)[:500]})
        except Exception as error:   # noqa: BLE001
            found['çökme'].append({'seed': seed, 'problem': f'{type(error).__name__}: {error}'[:300],
                                   'where': traceback.format_exc(limit=-4)[-900:]})
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()),
              'groups': {name: {'count': len(cases), 'examples': cases[:4]} for name, cases in found.items()}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


TMP = tempfile.TemporaryDirectory()
MEDIA = Path(TMP.name)
for name in fuzz.SOURCES + ['music.wav', 'mic.wav']:
    (MEDIA / name).touch()
patch('akis.app_support.recovery_dir', return_value=MEDIA / 'recovery').start()
patch('akis.media_service.MediaService.duration', return_value=float(fuzz.SECONDS)).start()

if __name__ == '__main__':
    raise SystemExit(main())
