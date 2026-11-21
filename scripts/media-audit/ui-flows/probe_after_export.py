"""Probe: after a Shorts / highlights / three-format export, does the main window still take mouse clicks and
Ctrl+E? Every step uses the real mouse and keyboard (no UIA invoke, which goes past a modal window).

Usage: python probe_after_export.py <workdir> <shorts|highlights|three> [packaged exe]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import longmedia as LM  # noqa: E402
import flow_edges_lib as L  # noqa: E402
import flow_more_lib as F  # noqa: E402

work = Path(sys.argv[1])
kind = sys.argv[2]
exe = Path(sys.argv[3]) if len(sys.argv) > 3 else None
video = work / 'Uzun çekim ğüş' / 'uzun örnek ş.mp4'
if not video.exists():
    LM.make(video, 64)
out = work / f'yoklama-{kind}'
out.mkdir(parents=True, exist_ok=True)
result = {'kind': kind}


def click(control):
    control.click_input()
    time.sleep(0.6)


def top_windows():
    found = []
    for w in U.Desktop(backend='uia').windows():
        if w.process_id() in process.owners:
            r = w.rectangle()
            found.append({'title': w.window_text(), 'class': w.element_info.class_name, 'visible': w.is_visible(),
                          'rect': [r.left, r.top, r.width(), r.height()],
                          'children': [(c.window_text(), c.element_info.class_name, c.is_visible())
                                       for c in w.children() if c.element_info.control_type == 'Window']})
    return found


def timeline_click_moves_playhead():
    view = window.child_window(class_name='MultitrackWidget')
    r = view.rectangle()
    before = L.clock(window)
    U.mouse.click(coords=(r.left + 100 + 300, r.top + 50))
    time.sleep(1.0)
    return before, L.clock(window)


process, app, window = U.start(exe=exe, settings=work / f'settings-probe-{kind}.ini')
process.main = window.handle
try:
    L.add(window, app, video, 64)
    result['before'] = timeline_click_moves_playhead()
    L.keys(window, '{HOME}')
    F.tab(window, 'Yayın')
    if kind == 'three':
        click(U.button(window, 'Üç biçimde dışa aktar'))
        U.file_dialog(app, out / 'üç.mp4')
    elif kind == 'shorts':
        click(U.button(window, "Shorts'a böl"))
        box = F.wait_dialog(process, title="Shorts'a böl", timeout=120)
        click([b for b in box.descendants(control_type='Button') if b.window_text() == 'Parçaları dışa aktar'][0])
    else:
        click(U.button(window, 'Öne çıkan anları bul'))
        box = F.wait_dialog(process, title='Öne çıkan anlar', timeout=180)
        click([b for b in box.descendants(control_type='Button') if 'Shorts olarak' in b.window_text()][0])
    if kind != 'three':
        picker = F.wait_dialog(process, title='Kaydedilecek klasör', timeout=30)
        edit = [e for e in picker.descendants(control_type='Edit') if 'fileName' in (e.element_info.automation_id or '')][0]
        click(edit)
        U.keyboard.send_keys('^a')
        U.keyboard.send_keys(str(out), with_spaces=True, pause=0.01)
        time.sleep(0.5)
        U.keyboard.send_keys('{ENTER}')
    box = F.wait_dialog(process, contains='başarıyla', timeout=900)
    click([b for b in box.descendants(control_type='Button') if b.window_text() in ('OK', 'Tamam')][0])
    time.sleep(1.5)
    result['windows_after'] = top_windows()
    result['after'] = timeline_click_moves_playhead()
    window.set_focus()
    U.keyboard.send_keys('^e')
    try:
        F.wait_dialog(process, native=True, timeout=8)
        result['ctrl_e'] = 'save dialog opened'
        U.keyboard.send_keys('{ESC}')
    except TimeoutError:
        result['ctrl_e'] = 'nothing'
    result['status'] = [t for t in U.status(window) if len(t) > 3][:8]
finally:
    U.stop(process)
    U.clean_recovery()
    (work / f'probe-{kind}.json').write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, default=str))
