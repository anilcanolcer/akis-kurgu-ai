"""Real-UI edge cases, part 1: cancel an export and retry it; close the window while an export runs.

The checks look at the export's own FFmpeg (its command line names the output); the editor's background preview
render may start again after a cancel, and that is expected.
Usage: python flow_edges.py <workdir> [packaged exe]
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402
import flow_edges_lib as L  # noqa: E402
from flow_edges2_helpers import click, message  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if work.exists():
    shutil.rmtree(work)
work.mkdir(parents=True)
M.SECONDS = 60
long_video = M.make(work / 'Uzun çekim' / 'uzun video ğüş.mp4')
M.SECONDS = 8
M.make(work / 'Çekim ğüşİ' / 'kısa video.mp4')         # for flow_edges2.py, flow_broken.py, flow_unsaved.py
results = {}


def record(name, ok, **detail):
    results[name] = {'ok': bool(ok), **detail}
    print(name, 'OK' if ok else 'FAILED', json.dumps(detail, ensure_ascii=False)[:400], flush=True)


def exporting(process, output):
    """PIDs of FFmpeg processes of the editor that write `output` (by name, also its hidden .part file)."""
    pids = [p for p in U.family(process.pid) if p not in process.owners]
    if not pids:
        return []
    query = ' OR '.join(f'ProcessId={p}' for p in pids)
    lines = subprocess.run(['powershell', '-NoProfile', '-Command',
                            f"Get-CimInstance Win32_Process -Filter '{query}' | ForEach-Object {{ \"$($_.ProcessId)|$($_.CommandLine)\" }}"],
                           capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.splitlines()
    return [int(line.split('|', 1)[0]) for line in lines if '|' in line and output.stem in line]


def alive(pid):
    return str(pid) in subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True).stdout


process, app, window = U.start(exe=exe, settings=work / 'settings.ini')
try:
    L.add(window, app, long_video, 60)

    # Cancel an export, then retry it
    out = work / 'Çıktı' / 'iptal deneme.mp4'
    out.parent.mkdir()
    L.export(window, app, out)
    time.sleep(2.0)
    running = exporting(process, out)
    next(b for b in window.descendants(control_type='Button') if b.window_text() == 'İptal' and b.is_enabled()).invoke()
    U.wait_for(lambda: [t for t in U.status(window) if 'iptal edildi' in t], timeout=30, what='iptal')
    time.sleep(1.0)
    record('export cancel', running and not out.exists() and not any(alive(p) for p in running),
           export_ffmpeg=running, still_running=[p for p in running if alive(p)],
           files_left=[p.name for p in out.parent.iterdir()])
    L.export(window, app, out)
    box, texts, _ = message(process, timeout=300, contains='başarıyla')
    click(box, 'OK|Tamam')
    info = M.info(out)
    record('export retry after cancel', abs(info['seconds'] - 60) < 0.2 and info['frames'] == 1800, **info)

    # Close the window during an export: asked first; Yes stops FFmpeg and leaves no half file
    out2 = work / 'Çıktı' / 'kapatırken.mp4'
    L.export(window, app, out2, replace=None)
    time.sleep(2.0)
    running = exporting(process, out2)
    window.child_window(title='Kapat', control_type='Button', found_index=0).invoke()
    box, asked, _ = message(process, timeout=10)
    click(box, 'Yes|Evet')
    then = None
    try:
        box, texts, buttons = message(process, timeout=6)
        then = (texts, buttons)
        click(box, 'At|Discard|Hayır|No')
    except TimeoutError:
        pass
    U.wait_for(lambda: process.poll() is not None or not [w for w in U.Desktop(backend='uia').windows()
                                                          if w.process_id() in process.owners], timeout=30, what='kapanma')
    time.sleep(2.0)
    record('close during export', running and not any(alive(p) for p in running) and not out2.exists()
           and not [p for p in out2.parent.iterdir() if '.part' in p.name],
           question=asked, then=then, export_ffmpeg=running)
finally:
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_edges.json').write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v['ok'] for k, v in results.items()}, ensure_ascii=False))
