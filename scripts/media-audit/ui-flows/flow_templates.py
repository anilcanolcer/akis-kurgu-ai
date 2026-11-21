"""Real-UI flow: Şablonlar (apply a ready-made template, undo it) and Şablonlarım (save this project's look as
a template, change everything, apply the saved template, delete it).

Saved templates live in the person's own app-data folder (templates.json): the file is copied first and put
back afterwards, whatever happens.
Usage: python flow_templates.py <workdir> [packaged exe]
"""
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402
import flow_edges_lib as L  # noqa: E402
import flow_more_lib as F  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
work.mkdir(parents=True, exist_ok=True)
video = work / 'Şablon denemesi' / 'şablon video.mp4'
if not video.exists():
    M.make(video)
templates = Path(os.environ['LOCALAPPDATA']) / 'AkisStudio' / 'Akış Kurgu AI' / 'templates.json'
backup = work / 'templates.json.yedek'
had_templates = templates.exists()
if had_templates:
    shutil.copy2(templates, backup)
results = {'mode': 'exe' if exe else 'source'}


def record(name, ok, **detail):
    results[name] = {'ok': bool(ok), **detail}
    print(name, 'OK' if ok else 'FAILED', json.dumps(detail, ensure_ascii=False, default=str)[:900], flush=True)


def look(window):
    """What the Düzenle tab shows: canvas, speed and the three colour values."""
    F.tab(window, 'Düzenle')
    combos = [c.selected_text() for c in window.descendants(control_type='ComboBox')[:3]]
    values = [t for t in U.status(window) if t.startswith(('+', '-')) or t == '0']
    return {'combos': combos, 'colour_labels': values[:3]}


def saved_project(window, app, path):
    L.keys(window, '^+s')
    U.file_dialog(app, path, replace=True if path.exists() else None)
    time.sleep(1.5)
    data = json.loads(path.read_text(encoding='utf-8'))
    tracks = [(t['kind'], t['name'], len(t['clips'])) for t in data['timeline']['tracks']]
    keep = ('aspect', 'brightness', 'contrast', 'saturation', 'speed', 'audio_level', 'audio_denoise', 'audio_duck')
    return {'tracks': tracks, 'state': {k: data['state'].get(k) for k in keep}}


process, app, window = U.start(exe=exe, settings=work / 'settings-templates.ini')
process.main = window.handle
try:
    L.add(window, app, video, 8)
    try:
        before = saved_project(window, app, work / 'önce.akis.json')
        U.press(window, '◈   Şablonlar')
        box = F.wait_dialog(process, title='Şablonlar', timeout=20)
        items = box.descendants(control_type='ListItem')
        chosen = items[1] if len(items) > 1 else items[0]
        chosen.select()
        time.sleep(0.5)
        described = F.texts_of(box)[:12]
        F.click(box, 'Şablonu uygula')
        time.sleep(1.5)
        for d in F.dialogs(process):          # a question about replacing the edit, if any
            described.append(('soru', F.texts_of(d)))
            F.click(d, r'(Yes|Evet|Uygula|OK|Tamam)')
            time.sleep(1)
        applied = saved_project(window, app, work / 'şablonlu.akis.json')
        L.keys(window, '^z')
        time.sleep(0.8)
        undone = saved_project(window, app, work / 'geri alınmış.akis.json')
        record('ready-made template', applied != before and undone == before, template=chosen.window_text(),
               dialog=described, before=before, applied=applied, undone=undone,
               status=[t for t in U.status(window) if 'uygula' in t.lower() or 'alındı' in t][:3])
    except Exception as exc:  # noqa: BLE001
        record('ready-made template', False, error=f'{type(exc).__name__}: {exc}', trace=traceback.format_exc()[-1000:],
               dialogs=[(d.window_text(), F.texts_of(d)[:6], F.buttons(d)) for d in F.dialogs(process)])
        for d in F.dialogs(process):
            d.close()

    try:
        F.tab(window, 'Düzenle')
        U.press(window, 'Canlı görünüm uygula')
        speed = [c for c in window.descendants(control_type='ComboBox') if c.selected_text().endswith('×')][0]
        F.choose(speed, '1.25×')
        F.tab(window, 'Yayın')
        window.child_window(title_re='.*gürültü azaltma.*', control_type='CheckBox').toggle()
        mine = saved_project(window, app, work / 'benim ayarlarım.akis.json')
        U.press(window, '◈   Şablonlar')
        box = F.wait_dialog(process, title='Şablonlar', timeout=20)
        F.click(box, 'Şablonlarım…')
        box = F.wait_dialog(process, title='Şablonlarım', timeout=20)
        F.click(box, 'Bu projeyi şablon olarak kaydet')
        ask = F.wait_dialog(process, title='Şablon olarak kaydet', timeout=10)
        ask.descendants(control_type='Edit')[0].set_edit_text('Deneme şablonu ğüş')
        F.click(ask, r'(OK|Tamam)')
        time.sleep(1)
        listed = [i.window_text() for i in box.descendants(control_type='ListItem')]
        F.click(box, 'İptal')
        stored = json.loads(templates.read_text(encoding='utf-8'))
        # change everything back by hand, then apply the saved template
        F.tab(window, 'Düzenle')
        U.press(window, 'Doğal görünüme dön')
        F.choose(speed, '1.00×')
        F.tab(window, 'Yayın')
        window.child_window(title_re='.*gürültü azaltma.*', control_type='CheckBox').toggle()
        plain = saved_project(window, app, work / 'sade.akis.json')
        U.press(window, '◈   Şablonlar')
        box = F.wait_dialog(process, title='Şablonlar', timeout=20)
        F.click(box, 'Şablonlarım…')
        box = F.wait_dialog(process, title='Şablonlarım', timeout=20)
        [i for i in box.descendants(control_type='ListItem') if 'Deneme şablonu' in i.window_text()][0].select()
        F.click(box, 'Şablonu uygula')
        time.sleep(1.5)
        again = saved_project(window, app, work / 'şablondan.akis.json')
        same = {k: again['state'][k] for k in ('brightness', 'contrast', 'saturation', 'speed', 'audio_denoise', 'aspect')}
        wanted = {k: mine['state'][k] for k in same}
        record('my template', same == wanted and plain['state'] != mine['state'], listed=listed,
               stored=[{k: t.get(k) for k in ('name', 'aspect', 'color', 'speed', 'audio')} for t in stored],
               mine=mine['state'], plain=plain['state'], applied=again['state'])
        # delete it again through the dialog
        U.press(window, '◈   Şablonlar')
        box = F.wait_dialog(process, title='Şablonlar', timeout=20)
        F.click(box, 'Şablonlarım…')
        box = F.wait_dialog(process, title='Şablonlarım', timeout=20)
        [i for i in box.descendants(control_type='ListItem') if 'Deneme şablonu' in i.window_text()][0].select()
        F.click(box, 'Şablonu sil')
        time.sleep(0.5)
        for d in F.dialogs(process):
            if d.handle != box.handle:
                F.click(d, r'(Yes|Evet|Sil)')
        time.sleep(0.5)
        F.click(box, 'İptal')
        results['after delete'] = json.loads(templates.read_text(encoding='utf-8'))
    except Exception as exc:  # noqa: BLE001
        record('my template', False, error=f'{type(exc).__name__}: {exc}', trace=traceback.format_exc()[-1000:],
               dialogs=[(d.window_text(), F.texts_of(d)[:6], F.buttons(d)) for d in F.dialogs(process)])
finally:
    U.stop(process)
    U.clean_recovery()
    if had_templates:
        shutil.copy2(backup, templates)
    elif templates.exists():
        templates.unlink()
    results['templates_restored'] = templates.read_text(encoding='utf-8') if templates.exists() else None
    (work / 'flow_templates.json').write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
