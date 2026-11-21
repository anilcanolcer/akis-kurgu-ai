"""Probe: does Ctrl+E open the export dialog after the FCPXML hand-off? Once with buttons pressed through UI
Automation (invoke), once with real mouse clicks; the focused control is logged before Ctrl+E.

Usage: python probe_ctrl_e.py <workdir> [packaged exe]
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

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
work.mkdir(parents=True, exist_ok=True)
video = work / 'Ctrl E' / 'ctrl e video.mp4'
if not video.exists():
    M.make(video)
results = {}


focused = F.focused


def ctrl_e(window, process):
    window.set_focus()
    time.sleep(0.3)
    before = focused()
    U.keyboard.send_keys('^e')
    try:
        F.wait_dialog(process, native=True, timeout=6)
        U.keyboard.send_keys('{ESC}')
        time.sleep(0.8)
        return before, 'save dialog opened'
    except TimeoutError:
        return before, 'nothing'


for mode in ('invoke', 'click'):
    process, app, window = U.start(exe=exe, settings=work / f'settings-ctrl-e-{mode}.ini')
    process.main = window.handle
    try:
        L.add(window, app, video, 8)
        results[f'{mode}: after adding'] = ctrl_e(window, process)
        F.tab(window, 'Yayın')
        button = U.button(window, 'Kurgu dosyası olarak aktar')
        button.invoke() if mode == 'invoke' else button.click_input()
        U.file_dialog(app, work / f'ctrl e {mode}.fcpxml', replace=True if (work / f'ctrl e {mode}.fcpxml').exists() else None)
        box = F.wait_dialog(process, contains='Kurgu dosyası kaydedildi', timeout=20)
        ok = [b for b in box.descendants(control_type='Button') if b.window_text() in ('OK', 'Tamam')][0]
        ok.invoke() if mode == 'invoke' else ok.click_input()
        time.sleep(1)
        results[f'{mode}: after FCPXML'] = ctrl_e(window, process)
        results[f'{mode}: windows'] = [(d.window_text(), d.element_info.class_name, d.is_visible()) for d in F.dialogs(process)]
        results[f'{mode}: status'] = [t for t in U.status(window) if 'Kurgu' in t or 'aktar' in t][:3]
    finally:
        U.stop(process)
        U.clean_recovery()
print(json.dumps(results, ensure_ascii=False, indent=1))
