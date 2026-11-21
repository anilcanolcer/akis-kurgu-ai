"""Real-UI flow over the publish tab and the export variants, each checked on the files it writes:

1. "Üç biçimde dışa aktar": three files, their sizes, every frame and every half second of sound.
2. "Shorts'a böl…": the parts shown in the dialog are the parts written; together they are the whole video,
   nothing lost or repeated.
3. "Öne çıkan anları bul…": each listed stretch is the stretch written.
4. Cut (Böl, Ripple sil) → "Kurgu dosyası olarak aktar": the FCPXML's clips are the timeline's.
5. Ctrl+E normal export of the cut, then the fast (copy) export on "Kaynak oranı": the frames shown.
6. "Toplu dışa aktar…": two videos with "Sessizlikleri çıkar"; only silent frames may be missing.

Usage: python flow_publish.py <workdir> [packaged exe]
"""
import json
import os
import shutil
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import longmedia as LM  # noqa: E402
import flow_edges_lib as L  # noqa: E402
import flow_more_lib as F  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
work.mkdir(parents=True, exist_ok=True)
SECONDS = 64
TOTAL = SECONDS * LM.FPS
video = work / 'Uzun çekim ğüş' / 'uzun örnek ş.mp4'
if not video.exists():
    LM.make(video, SECONDS)
out = work / 'Çıktılar'
shutil.rmtree(out, ignore_errors=True)
out.mkdir()
settings = work / 'settings-publish.ini'
results = {'mode': 'exe' if exe else 'source', 'source': str(video)}
started = time.time()


def record(name, ok, **detail):
    results[name] = {'ok': bool(ok), 't': round(time.time() - started), **detail}
    print(name, 'OK' if ok else 'FAILED', json.dumps(detail, ensure_ascii=False, default=str)[:700], flush=True)


ONLY = [s.strip() for s in os.environ.get('FLOW_SECTIONS', '').split(',') if s.strip()]


def section(name):
    def wrap(function):
        if ONLY and name not in ONLY:
            return function
        try:
            function()
        except Exception as exc:  # noqa: BLE001
            record(name, False, error=f'{type(exc).__name__}: {exc}',
                   dialogs_first=[(d.window_text(), d.element_info.class_name, F.texts_of(d)[:4]) for d in F.dialogs(process)],
                   trace=traceback.format_exc()[-1500:],
                   status=[t for t in U.status(window) if len(t) > 3][:12],
                   buttons_enabled={b.window_text(): b.is_enabled() for b in window.descendants(control_type='Button')
                                    if b.window_text() in ('Dışa aktar  ↗', 'İptal', 'Proje aç')},
                   dialogs=[(d.window_text(), d.element_info.class_name, F.texts_of(d)[:6], F.buttons(d)[:8])
                            for d in F.dialogs(process)])
            for d in F.dialogs(process):          # leave no dialog with text open for the next step
                if F.texts_of(d) or d.element_info.class_name == '#32770':
                    try:
                        d.type_keys('{ESC}')
                    except Exception:  # noqa: BLE001
                        pass
            time.sleep(1)
        return function
    return wrap


def done_message(contains='başarıyla', timeout=600):
    return F.answer(process, contains, timeout=timeout)


def sound_ok(heard, first_frame):
    """Each half second heard is the source second it should be (pauses silent; edges of pauses ignored)."""
    bad = []
    for i, value in enumerate(heard):
        t = first_frame / LM.FPS + i * 0.5
        expected = None if LM.silent_at(t + 0.25) else int(t + 0.25)
        near_edge = any(LM.silent_at(t + d) != LM.silent_at(t + 0.25) for d in (0.0, 0.49))
        if value != expected and not near_edge:
            bad.append((i, value, expected))
    return bad


process, app, window = U.start(exe=exe, settings=settings)
process.main = window.handle
try:
    L.add(window, app, video, SECONDS)
    record('video added', True, clock=L.clock(window))
    F.tab(window, 'Yayın')

    @section('three formats')
    def _three():
        U.press(window, 'Üç biçimde dışa aktar')
        U.file_dialog(app, out / 'üç biçim ğ.mp4')
        message = done_message()
        files = {}
        for suffix, size in (('dikey', (1080, 1920)), ('kare', (1080, 1080)), ('yatay', (1920, 1080))):
            path = out / f'üç biçim ğ_{suffix}.mp4'
            got_size, duration = LM.size(path) if path.exists() else ((0, 0), None)
            shown = LM.frames(path) if path.exists() else []
            heard = LM.seconds(path) if path.exists() else []
            files[suffix] = {'exists': path.exists(), 'size': got_size, 'size_ok': got_size == size,
                             'duration': duration, 'frames_ok': shown == list(range(TOTAL)),
                             'runs': LM.runs(shown)[:6], 'sound_bad': sound_ok(heard, 0)[:6]}
        record('three formats', all(f['exists'] and f['size_ok'] and f['frames_ok'] and not f['sound_bad']
                                    for f in files.values()), message=message[:2], files=files)

    @section('shorts')
    def _shorts():
        U.press(window, "Shorts'a böl")
        box = F.wait_dialog(process, title="Shorts'a böl", timeout=120)
        spin = box.descendants(control_type='Spinner') or [e for e in box.descendants(control_type='Edit')]
        spin[0].set_focus()
        U.keyboard.send_keys('^a20{TAB}')
        time.sleep(0.6)
        shown_cells = F.cells(box)
        summary = [t for t in F.texts_of(box) if 'parçaya' in t]
        F.click(box, 'Parçaları dışa aktar')
        chosen = F.qt_folder(process, out / 'Shorts ğüş')
        message = done_message(timeout=900)
        parts = sorted((out / 'Shorts ğüş').glob('*.mp4'))
        pieces, joined = [], []
        for path in parts:
            shown = LM.frames(path)
            size, duration = LM.size(path)
            pieces.append({'name': path.name, 'size': size, 'seconds': duration, 'runs': LM.runs(shown)[:4]})
            joined += shown
        record('shorts', bool(parts) and joined == list(range(TOTAL)) and all(p['size'] == (1080, 1920) for p in pieces),
               summary=summary, cells=shown_cells[:24], folder_button=chosen, message=message[:2], parts=pieces,
               missing=sorted(set(range(TOTAL)) - set(x for x in joined if x is not None))[:20],
               unread=sum(1 for x in joined if x is None))

    @section('highlights')
    def _highlights():
        U.press(window, 'Öne çıkan anları bul')
        box = F.wait_dialog(process, title='Öne çıkan anlar', timeout=180)
        listed = F.cells(box)
        F.click(box, 'Seçilenleri Shorts olarak dışa aktar')
        F.qt_folder(process, out / 'Öne çıkan')
        message = done_message(timeout=900)
        found = []
        for path in sorted((out / 'Öne çıkan').glob('*.mp4')):
            shown = LM.frames(path)
            found.append({'name': path.name, 'size': LM.size(path), 'runs': LM.runs(shown)[:4],
                          'first_s': (shown[0] or 0) / LM.FPS if shown else None,
                          'last_s': ((shown[-1] or 0) + 1) / LM.FPS if shown else None})
        record('highlights', bool(found) and all(len(f['runs']) == 1 for f in found), listed=listed[:24],
               message=message[:2], outputs=found)

    # --- cut the timeline: split at 10 s and 15 s, ripple-delete the middle piece -------------------------
    @section('cut')
    def _cut():
        view = window.child_window(class_name='MultitrackWidget')
        r = view.rectangle()
        window.set_focus()

        def at(x):   # click the ruler at x (a click on a clip only selects it) and read where the playhead went
            for _ in range(3):
                U.mouse.click(coords=(x, r.top + 15))
                time.sleep(0.8)
                found = L.clock(window)[0]
                if found > 0:
                    return found
            raise RuntimeError(f'tıklama oynatma çizgisini taşımadı (x={x})')
        x1, x2 = r.left + 100 + 150, r.left + 100 + 450
        t1, t2 = at(x1), at(x2)
        zoom = (x2 - x1) / ((t2 - t1) * LM.FPS)
        U.mouse.click(coords=(x1, r.top + 50))               # select the clip
        L.keys(window, '{HOME}' + '+{RIGHT}' * 10)
        L.keys(window, 's')
        U.mouse.click(coords=(int(x1 + (12.5 - t1) * LM.FPS * zoom), r.top + 50))   # the piece after 10 s
        L.keys(window, '{HOME}' + '+{RIGHT}' * 15)
        L.keys(window, 's')
        U.mouse.click(coords=(int(x1 + (12.5 - t1) * LM.FPS * zoom), r.top + 50))   # the 10–15 s piece
        time.sleep(0.5)
        U.press(window, 'Ripple sil')
        time.sleep(0.8)
        record('cut', abs(L.clock(window)[1] - (SECONDS - 5)) < 0.1, zoom=round(zoom, 4), clock=L.clock(window))

    expected_cut = list(range(0, 300)) + list(range(450, TOTAL))

    @section('fcpxml')
    def _fcpxml():
        U.press(window, 'Kurgu dosyası olarak aktar')
        U.file_dialog(app, out / 'kurgu ğüş.fcpxml')
        message = done_message('Kurgu dosyası kaydedildi')
        tree = ET.parse(out / 'kurgu ğüş.fcpxml')

        def sec(value):
            return float(Fraction(value.rstrip('s'))) if value else 0.0
        clips = [(round(sec(c.get('offset')), 3), round(sec(c.get('start')), 3), round(sec(c.get('duration')), 3))
                 for c in tree.iter('asset-clip')]
        assets = [a.get('name') or a.get('src') for a in tree.iter('asset')]
        media = [m.get('src') for m in tree.iter('media-rep')] or [a.get('src') for a in tree.iter('asset')]
        record('fcpxml', clips[:2] == [(0.0, 0.0, 10.0), (10.0, 15.0, 49.0)] and len(clips) == 2,
               clips=clips, assets=assets, media=media, message=message[:3])

    @section('export cut')
    def _export():
        results['export cut focus'] = F.focused()
        L.keys(window, '^e')
        try:                                     # the pre-export check may ask first
            box = F.wait_dialog(process, timeout=4)
            results['export cut question'] = F.texts_of(box)
            F.click(box, r'(Yes|Evet)')
        except TimeoutError:
            pass
        try:
            F.wait_dialog(process, native=True, timeout=6)
        except TimeoutError:                     # nothing opened: note where the keyboard was, activate, retry
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            title = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, title, 256)
            results['export cut retry'] = {'focus': F.focused(), 'foreground': [hwnd, title.value],
                                           'main': window.handle}
            r = window.rectangle()
            U.mouse.click(coords=(r.left + 300, r.top + 12))
            time.sleep(0.5)
            U.keyboard.send_keys('^e')
        U.file_dialog(app, out / 'kesilmiş ğ.mp4')
        message = done_message()
        shown = LM.frames(out / 'kesilmiş ğ.mp4')
        heard = LM.seconds(out / 'kesilmiş ğ.mp4')
        record('export cut', shown == expected_cut, size=LM.size(out / 'kesilmiş ğ.mp4'), runs=LM.runs(shown)[:6],
               heard=heard[18:24], message=message[:2])

    @section('fast export')
    def _fast():
        F.tab(window, 'Düzenle')
        combo = [c for c in window.descendants(control_type='ComboBox') if c.selected_text().startswith('9:16')][0]
        F.choose(combo, 'Kaynak oranı')
        results['aspect_now'] = combo.selected_text()
        time.sleep(0.5)
        L.keys(window, '^e')
        U.file_dialog(app, out / 'hızlı ğ.mp4')           # the name first, then the fast-copy question
        question = F.wait_dialog(process, contains='hızlı', timeout=20)
        asked = F.texts_of(question)
        F.click(question, r'(Yes|Evet)')
        message = done_message()
        path = out / 'hızlı ğ.mp4'
        shown = LM.frames(path)
        missing = sorted(set(expected_cut) - set(x for x in shown if x is not None))
        extra = sorted(set(x for x in shown if x is not None) - set(expected_cut))
        record('fast export', len(missing) <= 1 and len(extra) <= 2 * LM.FPS, asked=asked[:1], size=LM.size(path),
               runs=LM.runs(shown)[:6], missing=missing[:10], extra_count=len(extra), message=message[:2])

    @section('batch')
    def _batch():
        F.tab(window, 'Yayın')
        second = work / 'Toplu ğ' / 'ikinci örnek.mp4'
        if not second.exists():
            LM.make(second, 24)
        first = second.parent / 'birinci örnek ş.mp4'
        if not first.exists():
            shutil.copy(video, first)
        U.press(window, 'Toplu dışa aktar')
        box = F.wait_dialog(process, title='Toplu dışa aktar', timeout=20)
        F.click(box, 'Video ekle')
        F.native_files(app, second.parent, [first.name, second.name])
        time.sleep(1)
        listed = F.cells(box)
        if len(listed) != 2:
            raise RuntimeError(f'iki video listelenmedi: {listed}')
        (out / 'Toplu çıktı').mkdir(exist_ok=True)       # Başlat stays off while the typed folder does not exist
        folder_edit = [e for e in box.descendants(control_type='Edit')][-1]
        folder_edit.set_edit_text(str(out / 'Toplu çıktı'))
        F.click(box, 'Başlat')
        report = F.answer(process, 'dışa aktarıldı', timeout=900)
        outputs = sorted((out / 'Toplu çıktı').glob('*.mp4'))
        checked = []
        for path in outputs:
            shown = [x for x in LM.frames(path) if x is not None]
            total = (SECONDS if 'birinci' in path.name else 24) * LM.FPS
            dropped = sorted(set(range(total)) - set(shown))
            loud_dropped = [f for f in dropped if not LM.silent(f) and not any(LM.silent(f + d) for d in range(-9, 10))]
            checked.append({'name': path.name, 'size': LM.size(path), 'kept': len(shown), 'of': total,
                            'dropped': len(dropped), 'non_silent_dropped': loud_dropped[:10],
                            'ascending': shown == sorted(shown)})
        record('batch', len(outputs) == 2 and all(not c['non_silent_dropped'] and c['ascending'] and c['dropped'] > 0
                                                  for c in checked),
               listed=listed, report=report[:4], outputs=checked)
finally:
    results['dialogs_left'] = [(d.window_text(), F.texts_of(d)[:4]) for d in F.dialogs(process)]
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_publish.json').write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps({k: v.get('ok') if isinstance(v, dict) else v for k, v in results.items()}, ensure_ascii=False))
