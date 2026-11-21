"""Real-UI edge cases, part 2: a second job while one runs, an output file another program holds open,
the same name as an existing file or the source, moved media.

Run after flow_edges.py (it uses that run's videos and moves the short one's folder for the relink test).
Usage: python flow_edges2.py <workdir of flow_edges.py> [packaged exe]
"""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402
import flow_edges_lib as L  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
long_video = work / 'Uzun çekim' / 'uzun video ğüş.mp4'
short_video = work / 'Çekim ğüşİ' / 'kısa video.mp4'
if not short_video.exists():
    M.make(short_video)
out_dir = work / 'Çıktı2'
shutil.rmtree(out_dir, ignore_errors=True)
out_dir.mkdir()
settings = work / 'settings2.ini'
results = {}


def record(name, ok, **detail):
    results[name] = {'ok': bool(ok), **detail}
    print(name, 'OK' if ok else 'FAILED', json.dumps(detail, ensure_ascii=False)[:500], flush=True)


def dialogs(process):
    out = []
    for w in U.Desktop(backend='uia').windows():
        if w.process_id() in process.owners:
            out += [c for c in w.children() if c.element_info.control_type == 'Window']
    return out


def message(process, timeout=20, contains=''):
    def find():
        for d in dialogs(process):
            if d.element_info.class_name == '#32770':
                continue
            texts = [c.window_text() for c in d.descendants(control_type='Text') if c.window_text()]
            if texts and contains in ' '.join(texts):
                return d, texts, [b.window_text() for b in d.descendants(control_type='Button')]
        return None
    return U.wait_for(find, timeout=timeout, what='ileti penceresi')


def click(box, pattern):
    for b in box.descendants(control_type='Button'):
        if re.fullmatch(pattern, b.window_text().replace('&', '')):
            b.invoke()
            return b.window_text()
    raise LookupError(f'{pattern} yok: {[b.window_text() for b in box.descendants(control_type="Button")]}')


def closed(process):
    return process.poll() is not None or not [w for w in U.Desktop(backend='uia').windows() if w.process_id() in process.owners]


process, app, window = U.start(exe=exe, settings=settings)
try:
    # A second job while an export runs: no second dialog opens, the first export finishes intact
    L.add(window, app, long_video, 60)
    first = out_dir / 'birinci.mp4'
    L.export(window, app, first)
    time.sleep(1.5)
    window.set_focus()
    U.keyboard.send_keys('^e')
    seen = set()
    for _ in range(15):
        seen |= {t for t in U.status(window) if 'devam ediyor' in t}
        time.sleep(0.1)
    second_dialog = any(d.element_info.class_name == '#32770' for d in dialogs(process))
    box, texts, _ = message(process, timeout=300, contains='başarıyla')
    click(box, 'OK|Tamam')
    info = M.info(first)
    record('second job refused while exporting', not second_dialog and info['frames'] == 1800, status=sorted(seen),
           second_dialog=second_dialog, first_export=info)
    U.stop(process)

    process, app, window = U.start(exe=exe, settings=settings)
    L.add(window, app, short_video, 8)

    # An output file another program holds open: the export fails with a message, and works once it is free
    held = out_dir / 'açık dosya.mp4'
    held.write_bytes(b'baska program')
    holder = subprocess.Popen(['powershell', '-NoProfile', '-Command',
                               f"$f=[IO.File]::Open('{held}','Open','ReadWrite','None'); Start-Sleep 40; $f.Close()"])
    time.sleep(2)
    d = L.export(window, app, held, replace=True)
    overwrite_question = getattr(d, 'replaced', None)
    box, texts, buttons = message(process, timeout=120)
    click(box, 'OK|Tamam')
    time.sleep(0.5)
    parts = [p.name for p in out_dir.iterdir() if '.part' in p.name]
    named = any('başka bir programda açık' in t for t in texts)          # 0.6.18: "[WinError 5] … .part-….mp4"
    record('output held by another program', process.poll() is None and named and not parts
           and not any('.part' in t for t in texts),
           overwrite_question=overwrite_question, message=texts, part_files_left=parts)
    holder.kill()
    time.sleep(1)
    L.export(window, app, held, replace=True)
    box, texts, _ = message(process, timeout=120, contains='başarıyla')
    click(box, 'OK|Tamam')
    record('same export works once the file is free', M.info(held)['frames'] == 240)

    # Same name as an existing file: "No" keeps it; the source video itself is refused
    existing = out_dir / 'var olan.mp4'
    existing.write_bytes(b'eski dosya')
    d = L.export(window, app, existing, replace=False)
    texts = getattr(d, 'replaced', None)
    time.sleep(0.8)
    record('existing output kept on No', existing.read_bytes() == b'eski dosya', question=texts)
    before = short_video.read_bytes()
    d = L.export(window, app, short_video, replace=True)
    shown = [('Windows', getattr(d, 'replaced', None))]
    for _ in range(3):
        try:
            box, texts, _ = message(process, timeout=6)
        except TimeoutError:
            break
        shown.append(texts)
        click(box, 'Yes|Evet|OK|Tamam') if any('üzerine' in t or 'zaten var' in t for t in texts) else click(box, 'OK|Tamam|No|Hayır')
        time.sleep(0.5)
    time.sleep(2)
    record('source video never overwritten', short_video.read_bytes() == before, messages=shown)

    # Save, move the media folder away, reopen: the editor asks for the file and the project plays again
    project = work / 'Projeler2' / 'taşınacak proje.akis.json'
    shutil.rmtree(project.parent, ignore_errors=True)
    project.parent.mkdir()
    L.keys(window, '^s')
    U.file_dialog(app, project)
    U.wait_for(project.is_file, timeout=20, what='kayıt')
    window.child_window(title='Kapat', control_type='Button', found_index=0).invoke()
    U.wait_for(lambda: closed(process), timeout=30, what='kapanma')
    U.stop(process)
    moved = work / 'Taşınan klasör ğ'
    shutil.rmtree(moved, ignore_errors=True)
    shutil.copytree(short_video.parent, moved)
    shutil.rmtree(short_video.parent)
    process, app, window = U.start(exe=exe, settings=settings)
    U.press(window, 'Proje aç')
    U.file_dialog(app, project)
    steps = []
    for _ in range(4):
        found = U.wait_for(lambda: dialogs(process) or ((L.clock(window) or (0, 0))[1] > 7.9 and ['ready']),
                           timeout=20, what='eksik medya adımı')
        if found == ['ready']:
            break
        d = found[0]
        if d.element_info.class_name == '#32770':
            steps.append(('dosya penceresi', d.window_text()))
            U.file_dialog(app, moved / short_video.name)
        else:
            texts = [c.window_text() for c in d.descendants(control_type='Text') if c.window_text()]
            steps.append(('ileti', texts, [b.window_text() for b in d.descendants(control_type='Button')]))
            click(d, 'Yes|Evet|Bul.*|Konumu.*|OK|Tamam')
        time.sleep(1)
    total = (L.clock(window) or (0, 0))[1]
    record('moved media found again', total > 7.9, steps=steps, clock=total)
    out = out_dir / 'taşındıktan sonra.mp4'
    L.export(window, app, out)
    box, texts, _ = message(process, timeout=120, contains='başarıyla')
    click(box, 'OK|Tamam')
    record('export after relinking shows the moved video', M.frames(out)[:3] == [0, 1, 2] and M.info(out)['frames'] == 240)
    # Broken project files: flow_broken.py. Unsaved work on open and close: flow_unsaved.py.
finally:
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_edges2.json').write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v['ok'] for k, v in results.items()}, ensure_ascii=False))
