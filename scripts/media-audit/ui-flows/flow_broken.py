"""Real-UI: a broken or future-format project file is refused and the open project stays."""
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
folder = work / 'Projeler3'
folder.mkdir(exist_ok=True)
cases = {'yarım JSON': '{"format": "akis-kurgu-project", "timeline": [',
         'gelecek sürüm': json.dumps({'format': 'akis-kurgu-project', 'version': 99}),
         'boş dosya': ''}
results = {}
process, app, window = U.start(exe=exe, settings=work / 'settings3.ini')
try:
    L.add(window, app, video, 8)
    for name, body in cases.items():
        broken = folder / f'{name}.akis.json'
        broken.write_text(body, encoding='utf-8')
        U.press(window, 'Proje aç')
        asked = []
        try:
            box, texts, buttons = message(process, timeout=4)
            asked = texts
            click(box, 'At|Discard|Hayır|No')
        except TimeoutError:
            pass
        U.file_dialog(app, broken)
        box, texts, _ = message(process, timeout=15)
        click(box, 'OK|Tamam')
        time.sleep(0.8)
        total = (L.clock(window) or (0, 0))[1]
        results[name] = {'ok': total > 7.9, 'unsaved_question': asked, 'message': texts, 'clock': total}
        print(name, results[name], flush=True)
finally:
    U.stop(process)
    U.clean_recovery()
    print(json.dumps({k: v['ok'] for k, v in results.items()}, ensure_ascii=False))
