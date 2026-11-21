"""Real-UI flow: Kayıt al → preview → Kaydı başlat → the program steps aside → stop from the small bar →
the recording is in the project → open the MP4 and measure it.

Usage: python flow_record.py <workdir> [packaged exe]
"""
import ctypes
import json
import re
import subprocess
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow_more_lib as F
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402
from PIL import ImageGrab, ImageStat  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
work.mkdir(parents=True, exist_ok=True)
recordings = tempfile.TemporaryDirectory(dir=work, prefix='Akış kayıt ')
videos = Path(recordings.name)
user32 = ctypes.windll.user32
result = {'mode': 'exe' if exe else 'source', 'checks': {}}
started = time.time()


def check(name, ok, **detail):
    result['checks'][name] = {'ok': bool(ok), **detail}
    print(name, 'OK' if ok else 'FAILED', detail, flush=True)


def children(window):
    return [c for c in window.children() if c.element_info.control_type == 'Window']


def clock(window):
    for text in U.status(window):
        found = re.fullmatch(r'(\d+):(\d+\.\d+) / (\d+):(\d+\.\d+)', text.strip())
        if found:
            return int(found[1]) * 60 + float(found[2]), int(found[3]) * 60 + float(found[4])
    return None


def spread(rect):
    """How much the pixels in a screen area differ (0 for a flat colour): a live picture is not flat."""
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).convert('L')
    return ImageStat.Stat(image).stddev[0]


process, app, window = U.start(exe=exe, settings=work / 'settings.ini')
try:
    U.press(window, 'Kayıt al')
    dialog = U.wait_for(lambda: next((d for d in children(window) if d.window_text() in ('Kayıt', 'Record')), None),
                        timeout=15, what='kayıt penceresi')
    folder_button = next(b for b in dialog.descendants(control_type='Button') if Path(b.window_text()).is_absolute())
    folder_button.invoke()
    F.qt_folder(process, videos, title='Kayıt klasörü')
    U.wait_for(lambda: Path(folder_button.window_text()) == videos, what='özel kayıt klasörü')
    time.sleep(1.5)
    dialog.set_focus()
    stage = U.wait_for(lambda: next((c for c in dialog.descendants() if c.is_visible() and
                       c.element_info.automation_id.endswith('.screenPreview')), None), what='ekran önizlemesi')
    variance = spread(stage.rectangle())
    check('preview shows the screen', variance > 8, spread=round(variance, 1), rect=str(stage.rectangle()))
    main_handle = window.handle
    start_button = next(b for b in dialog.descendants(control_type='Button') if 'Kaydı başlat' in b.window_text())
    start_button.invoke()
    time.sleep(2.0)

    def bar():
        for w in U.Desktop(backend='uia').windows():
            if w.process_id() in process.owners:
                for b in w.descendants(control_type='Button'):
                    if 'Durdur ve ekle' in b.window_text():
                        return w, b
        return None
    found = U.wait_for(bar, timeout=10, what='kayıt çubuğu')
    check('main window minimised', user32.IsIconic(main_handle), )
    check('record window off the screen', user32.IsIconic(dialog.handle) or not user32.IsWindowVisible(dialog.handle),
          iconic=bool(user32.IsIconic(dialog.handle)), visible=bool(user32.IsWindowVisible(dialog.handle)))
    bar_window, stop_button = found
    check('bar shown', bar_window.is_visible(), rect=str(bar_window.rectangle()))
    time.sleep(3.0)
    stop_button.invoke()
    U.wait_for(lambda: not dialog.exists() if hasattr(dialog, 'exists') else True, timeout=30, what='kayıt penceresinin kapanması')
    time.sleep(2.0)
    check('main window back', not user32.IsIconic(main_handle))
    total = U.wait_for(lambda: (clock(window) or (0, 0))[1] > 1 and clock(window), timeout=30, what='kaydın projeye eklenmesi')
    check('recording in the project', total[1] > 1, clock=total)
    made = sorted((p for p in videos.glob('*.mp4')), key=lambda p: p.stat().st_mtime)
    check('file written', made, files=[p.name for p in made])
    if made:
        info = M.info(made[-1])
        decoded = subprocess.run([M.FFMPEG, '-v', 'error', '-i', str(made[-1]), '-f', 'null', '-'], capture_output=True, text=True)
        check('mp4 opens and decodes', info['frames'] > 30 and not decoded.stderr.strip(), **info,
              decode_errors=decoded.stderr.strip()[:200])
        check('length matches the clock', abs(info['seconds'] - total[1]) < 0.5, file_seconds=info['seconds'], clock=total[1])
finally:
    U.stop(process)
    U.clean_recovery()
    recordings.cleanup()
    result['seconds'] = round(time.time() - started, 1)
    (work / 'flow_record.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))

if not all(check['ok'] for check in result['checks'].values()):
    raise AssertionError('Recording checks failed; see flow_record.json')
