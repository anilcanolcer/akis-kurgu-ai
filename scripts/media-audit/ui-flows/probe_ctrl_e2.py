"""Probe: after which editing step does Ctrl+E stop opening the export dialog? Ctrl+E is tried (and the
dialog closed again) after each step of a cut on the timeline; the focused control is logged each time.

Usage: python probe_ctrl_e2.py <workdir> [packaged exe] [invoke|click]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402
import flow_edges_lib as L  # noqa: E402
import flow_more_lib as F  # noqa: E402
from flow_more_lib import focused  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] not in ('invoke', 'click') else None
mode = sys.argv[-1] if sys.argv[-1] in ('invoke', 'click') else 'invoke'
work.mkdir(parents=True, exist_ok=True)
video = work / 'Ctrl E' / 'ctrl e video.mp4'
if not video.exists():
    M.make(video)
steps = []


def try_ctrl_e(step):
    window.set_focus()
    time.sleep(0.3)
    where = focused()
    U.keyboard.send_keys('^e')
    try:
        F.wait_dialog(process, native=True, timeout=5)
        U.keyboard.send_keys('{ESC}')
        time.sleep(0.8)
        outcome = 'dialog'
    except TimeoutError:
        outcome = 'NOTHING'
    steps.append((step, outcome, where[:2], [t for t in U.status(window) if len(t) > 12][-1:]))
    print(step, outcome, where[:2], flush=True)


def press(name):
    control = U.button(window, name)
    control.invoke() if mode == 'invoke' else control.click_input()
    time.sleep(0.6)


process, app, window = U.start(exe=exe, settings=work / f'settings-ctrl-e2-{mode}.ini')
process.main = window.handle
try:
    L.add(window, app, video, 8)
    try_ctrl_e('video added')
    view = window.child_window(class_name='MultitrackWidget')
    r = view.rectangle()
    U.mouse.click(coords=(r.left + 100 + 150, r.top + 15))
    time.sleep(0.6)
    try_ctrl_e('ruler clicked')
    U.mouse.click(coords=(r.left + 100 + 150, r.top + 50))
    time.sleep(0.6)
    try_ctrl_e('clip clicked (selected)')
    L.keys(window, 's')
    try_ctrl_e('S pressed (split)')
    U.mouse.click(coords=(r.left + 100 + 60, r.top + 50))
    time.sleep(0.6)
    press('Ripple sil')
    try_ctrl_e('Ripple sil')
    F.tab(window, 'Yayın')
    try_ctrl_e('Yayın tab')
    press('Kurgu dosyası olarak aktar')
    U.file_dialog(app, work / f'ctrl e2 {mode}.fcpxml', replace=True if (work / f'ctrl e2 {mode}.fcpxml').exists() else None)
    F.answer(process, 'Kurgu dosyası kaydedildi')
    time.sleep(0.8)
    try_ctrl_e('FCPXML written')
finally:
    U.stop(process)
    U.clean_recovery()
    (work / f'probe-ctrl-e2-{mode}.json').write_text(json.dumps(steps, ensure_ascii=False, indent=1), encoding='utf-8')
