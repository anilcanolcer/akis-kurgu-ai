"""Real-UI: projects whose settings part is damaged (hand-edited, another program, a cut-off sync), opened
with "Proje aç". Every message the editor shows is recorded in order, then what opened.

Usage: python flow_settings.py <workdir> [packaged exe]
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
video = work / 'Ayar denemesi ğ' / 'ayar videosu.mp4'
if not video.exists():
    M.make(video)
folder = work / 'Bozuk ayarlı projeler'
folder.mkdir(exist_ok=True)


def project(state=None, **top):
    fps_clip = {'id': 'c1', 'source': str(video), 'start': 0, 'length': 240, 'source_in': 0, 'source_length': 240}
    doc = {'format': 'akis-kurgu-project', 'version': 2, 'saved_at': '2026-11-21T12:00:00+03:00',
           'state': {'source': str(video), 'duration': 8.0, 'start': 0.0, 'end': 8.0, 'aspect': '9:16 · Reels / Shorts',
                     'brightness': 10, 'contrast': 0, 'saturation': 0, 'speed': 1.0,
                     'export_profile': 'Reels · 1080×1920'},
           'timeline': {'fps_num': 30, 'fps_den': 1, 'tracks': [{'kind': 'video', 'name': 'Video', 'clips': [fps_clip]}]},
           'publish': {'title': 'Yayın', 'caption': '', 'hashtags': ''}, 'ai_prompt': ''}
    if state is not None:
        doc['state'] = state
    for key, value in top.items():
        if key.startswith('state_'):
            doc['state'][key[6:]] = value
        else:
            doc[key] = value
    return json.dumps(doc, ensure_ascii=False)


cases = {
    'ayarlar metin': project(state='metin'),
    'dev doygunluk, yayın sayı, istek sözlük': project(state_saturation=10 ** 30, publish=5, ai_prompt={'x': 1}),
    'hız yazı, tuval liste': project(state_speed='hızlı', state_aspect=['9:16']),
}
results = {'mode': 'exe' if exe else 'source'}
process, app, window = U.start(exe=exe, settings=work / 'settings-bozuk-ayar.ini')
process.main = window.handle
try:
    for name, body in cases.items():
        path = folder / f'{name}.akis.json'
        path.write_text(body, encoding='utf-8')
        U.press(window, 'Proje aç')
        try:                                   # a previous project with changes asks first
            box = F.wait_dialog(process, contains='kaydedilsin', timeout=3)
            F.click(box, 'At|Discard|Hayır|No')
        except TimeoutError:
            pass
        U.file_dialog(app, path)
        shown = []
        while True:
            try:
                box = F.wait_dialog(process, timeout=6)
            except TimeoutError:
                break
            shown.append(F.texts_of(box))
            F.click(box, r'(OK|Tamam|Ok)')
            time.sleep(0.6)
        time.sleep(1)
        clock = L.clock(window)
        results[name] = {'messages': shown, 'clock': clock, 'title': window.window_text(),
                         'status': [t for t in U.status(window) if 'Proje' in t][:3]}
        print(name, json.dumps(results[name], ensure_ascii=False), flush=True)
finally:
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_settings.json').write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
