"""Real-UI: edited but unsaved work is never dropped without a question (open another project, close the window)."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import flow_edges_lib as L  # noqa: E402
from flow_edges2_helpers import message, click  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
video = work / 'Taşınan klasör ğ' / 'kısa video.mp4'
other = work / 'Projeler2' / 'taşınacak proje.akis.json'
results = {}
process, app, window = U.start(exe=exe, settings=work / 'settings4.ini')
try:
    L.add(window, app, video, 8)
    view = window.child_window(class_name='MultitrackWidget').rectangle()
    U.mouse.click(coords=(view.left + 110, view.top + 50))
    L.keys(window, '{HOME}+{RIGHT}+{RIGHT}s')
    split = [t for t in U.status(window) if 'bölündü' in t]

    U.press(window, 'Proje aç')
    U.file_dialog(app, other)
    box, texts, buttons = message(process, timeout=10)
    click(box, 'İptal|Cancel')
    time.sleep(1)
    results['open another project asks'] = {'ok': bool(split) and 'kaydedilmemiş' in ' '.join(texts),
                                            'question': texts, 'buttons': buttons}
    window.child_window(title='Kapat', control_type='Button', found_index=0).invoke()
    box, texts, buttons = message(process, timeout=10)
    click(box, 'İptal|Cancel')
    time.sleep(1)
    still = process.poll() is None and window.exists()
    results['closing asks and Cancel keeps the window'] = {'ok': still and 'kaydedilmemiş' in ' '.join(texts),
                                                          'question': texts}
    window.child_window(title='Kapat', control_type='Button', found_index=0).invoke()
    box, texts, buttons = message(process, timeout=10)
    click(box, 'At|Discard')
    U.wait_for(lambda: process.poll() is not None or not window.exists(), timeout=20, what='kapanma')
    results['discard closes'] = {'ok': True}
finally:
    U.stop(process)
    U.clean_recovery()
    print(json.dumps(results, ensure_ascii=False))
