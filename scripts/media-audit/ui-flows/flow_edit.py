"""Real-UI flow: Video ekle → split and trim on the timeline → undo/redo → save → close → reopen → export,
then read the exported MP4 frame by frame and second by second.

Usage: python flow_edit.py <workdir> [packaged exe]
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
work.mkdir(parents=True, exist_ok=True)
video = M.make(work / 'Çekim ğüşİ klasörü' / 'örnek video çalışma.mp4')
project = work / 'Projeler İş' / 'Deneme projesi ğüş.akis.json'
project.parent.mkdir(exist_ok=True)
output = work / 'Çıktılar' / 'son video ğüş.mp4'
output.parent.mkdir(exist_ok=True)
settings = work / 'settings.ini'
log = []


def note(step, **data):
    log.append({'step': step, 't': round(time.time() - started, 1), **data})
    print(step, data, flush=True)


def clock(window):
    for text in U.status(window):
        found = re.fullmatch(r'(\d+):(\d+\.\d+) / (\d+):(\d+\.\d+)', text.strip())
        if found:
            return int(found[1]) * 60 + float(found[2]), int(found[3]) * 60 + float(found[4])
    return None


def popups(process, main):
    out = []
    for w in U.Desktop(backend='uia').windows():
        if w.process_id() in process.owners:
            for d in ([w] if w.handle != main.handle else []) + \
                    [c for c in w.children() if c.element_info.control_type == 'Window']:
                texts = [c.window_text() for c in d.descendants(control_type='Text') if c.window_text()]
                out.append((d, d.window_text(), texts))
    return out


def answer(process, main, wanted_text, button_names=('OK', 'Tamam'), timeout=120):
    def find():
        for w, title, texts in popups(process, main):
            if any(wanted_text in t for t in texts):
                return w, texts
        return None
    w, texts = U.wait_for(find, timeout=timeout, what=f'"{wanted_text}" penceresi')
    for b in w.descendants(control_type='Button'):
        if b.window_text() in button_names:
            b.invoke()
            return texts
    U.keyboard.send_keys('{ENTER}')
    return texts


def timeline_point(window, frame, zoom, track=0):
    view = window.child_window(class_name='MultitrackWidget')
    r = view.rectangle()
    return int(r.left + 100 + frame * zoom), int(r.top + 30 + track * 43 + 20)


def keys(window, text):
    window.set_focus()
    U.keyboard.send_keys(text, pause=0.05)
    time.sleep(0.4)


started = time.time()
result = {'source': str(video), 'mode': 'exe' if exe else 'source'}
process, app, window = U.start(exe=exe, settings=settings)
try:
    note('opened', title=window.window_text())
    U.press(window, 'Video ekle')
    U.file_dialog(app, video)
    U.wait_for(lambda: (clock(window) or (0, 0))[1] > 7.9, timeout=60, what='video eklenmesi')
    note('video added', clock=clock(window), popups=[p[1:] for p in popups(process, main=window)])

    # learn the timeline scale: click 200 px into the clip and read the clock
    view = window.child_window(class_name='MultitrackWidget')
    r = view.rectangle()
    U.mouse.click(coords=(r.left + 100 + 200, r.top + 50))
    time.sleep(0.6)
    at = clock(window)[0]
    zoom = 200 / (at * 30) if at else 3.0
    note('clicked clip', clock=clock(window), zoom=round(zoom, 3))

    keys(window, '{HOME}+{RIGHT}+{RIGHT}')                  # playhead to 2 s
    note('playhead', clock=clock(window))
    keys(window, 's')
    note('split', status=[t for t in U.status(window) if 'bölün' in t.lower() or 'seç' in t.lower()][:3])

    U.mouse.click(coords=timeline_point(window, 150, zoom))  # select the second piece
    time.sleep(0.5)
    keys(window, '{HOME}' + '+{RIGHT}' * 4)                 # playhead to 4 s
    note('second piece', clock=clock(window))
    keys(window, 'q')                                      # drop 2 s – 4 s of the second piece
    after_cut = clock(window)
    note('trimmed', clock=after_cut, status=[t for t in U.status(window) if 'atıldı' in t or 'Kırp' in t][:3])

    def said():
        return [t for t in U.status(window) if t in ('Son adım geri alındı.', 'Adım yinelendi.')]
    keys(window, '^z')
    after_undo = said()
    keys(window, '^y')
    after_redo = said()
    note('undo/redo', after_undo=after_undo, after_redo=after_redo)

    keys(window, '^s')
    U.file_dialog(app, project)
    U.wait_for(lambda: project.is_file(), timeout=30, what='proje kaydı')
    time.sleep(1)
    saved = json.loads(project.read_text(encoding='utf-8'))
    tracks = saved.get('timeline', saved.get('multitrack', {})).get('tracks', [])
    result['saved_clips'] = [[(c.get('start'), c.get('length'), c.get('source_in')) for c in t.get('clips', [])]
                             for t in tracks]
    note('saved', bytes=project.stat().st_size, title=window.window_text(), clips=result['saved_clips'],
         keys=list(saved)[:12])

    window.child_window(title='Kapat', control_type='Button', found_index=0).invoke()
    U.wait_for(lambda: process.poll() is not None, timeout=30, what='program kapanması')
    leftover = popups(process, main=window) if process.poll() is None else []
    note('closed', exit=process.poll(), leftover=[p[1:] for p in leftover])
    U.stop(process)

    process, app, window = U.start(exe=exe, settings=settings)
    U.press(window, 'Proje aç')
    U.file_dialog(app, project)
    U.wait_for(lambda: (clock(window) or (0, 0))[1] > 0.5, timeout=60, what='proje açılması')
    reopened = clock(window)
    note('reopened', clock=reopened, title=window.window_text())

    keys(window, '^e')

    def question_or_dialog():
        for w, title, texts in popups(process, window):
            if w.element_info.class_name == '#32770':
                return 'dialog', texts
            if texts:
                return 'question', texts
        return None
    kind, texts = U.wait_for(question_or_dialog, timeout=20, what='dışa aktarma penceresi')
    if kind == 'question':                       # the pre-export check (a gap in the timeline)
        note('export question', texts=texts)
        answer(process, window, texts[0], button_names=('Yes', '&Yes', 'Evet', '&Evet'))
    U.file_dialog(app, output)
    texts = answer(process, window, 'başarıyla', timeout=300)
    note('exported', message=texts)

    result.update(after_cut=after_cut, after_undo=after_undo, after_redo=after_redo, reopened=reopened,
                  output=str(output), info=M.info(output))
    shown = M.frames(output)
    heard = M.seconds(output)
    # split at 2 s, then Q at 4 s on the second piece: 0-2 s plays, 2-4 s is an empty gap (black, silent), 4-8 s plays
    expected = list(range(0, 60)) + [None] * 60 + list(range(120, 240))
    result['frames_ok'] = shown == expected
    if not result['frames_ok']:
        result['frames'] = shown
        result['frame_mismatches'] = [(i, a, b) for i, (a, b) in enumerate(zip(shown, expected)) if a != b][:20]
    result['sound'] = heard
    result['sound_ok'] = heard == [0, 0, 1, 1, None, None, None, None, 4, 4, 5, 5, 6, 6, 7, 7]
finally:
    result['log'] = log
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_edit.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'log'}, ensure_ascii=False))

if not ('Son adım geri alındı.' in after_undo and 'Adım yinelendi.' in after_redo and
        result['frames_ok'] and result['sound_ok']):
    raise AssertionError('Undo, redo or decoded media check failed; see flow_edit.json')
