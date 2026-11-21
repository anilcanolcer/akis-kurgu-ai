"""Real-UI flow: switch the interface to English with its own button, then read every text the main window
and its dialogs show and list what is still Turkish. Switch back and check the Turkish labels return; the
light theme button changes the window's colours and back.

Dialogs opened in English: Inspiration, Templates, Story Studio, F1 shortcuts, Record, Remove silences,
Split into Shorts, Batch export, Find highlights (refusal on a short video), the version button.

Usage: python flow_language.py <workdir> [packaged exe]
"""
import json
import re
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
video = work / 'Dil denemesi' / 'dil ğüş.mp4'
if not video.exists():
    M.make(video)
results = {'mode': 'exe' if exe else 'source'}
TURKISH = re.compile(r'[çğışöüÇĞİŞÖÜ]')
# What is allowed to stay Turkish: the brand, language names, Windows voices, the person's own files.
ALLOWED = ('Akış Kurgu', 'AKIŞ KURGU', 'Akış edits', 'Türkçe', 'tr-TR', 'Microsoft', 'dil ğüş', 'Dil denemesi',
           'Tolga', 'Yelda')


def everything(box):
    """Every name and description (tooltip, placeholder) UIA gives for the controls under `box`; Windows' own
    title-bar buttons ("Simge Durumuna Küçült"…) are left out: they follow the language of Windows."""
    seen = []
    for c in box.descendants():
        info = c.element_info
        try:
            if c.parent().element_info.control_type == 'TitleBar':
                continue
        except Exception:  # noqa: BLE001
            pass
        for text in (info.name, F.description(c)):
            if text and text.strip():
                seen.append((info.control_type, text.strip()))
    return seen


def leftovers(box):
    return sorted({f'{kind}: {text}'[:160] for kind, text in everything(box)
                   if TURKISH.search(text) and not any(a in text for a in ALLOWED)})


def brightness(window):
    image = window.capture_as_image().convert('L')
    small = image.resize((64, 36))
    return sum(small.tobytes()) / (64 * 36)


def switch(window, name):
    """The language and theme switches are checkable buttons (UIA lists them as check boxes): click one."""
    window.child_window(title=name, control_type='CheckBox').click_input()
    time.sleep(0.8)


process, app, window = U.start(exe=exe, settings=work / 'settings-lang.ini')
process.main = window.handle


def opened(name, open_step, close_pattern=r'(Close|Cancel|Kapat|İptal|OK)', title=None, contains=''):
    try:
        before = {d.handle for d in F.dialogs(process)}
        open_step()
        box = U.wait_for(lambda: next((d for d in F.dialogs(process) if d.handle not in before and
                                       (not title or title in d.window_text()) and
                                       (not contains or contains in ' '.join(F.texts_of(d)))), None),
                         timeout=60, what=name)
        time.sleep(1.0)
        found = leftovers(box)
        results[name] = {'title': box.window_text(), 'turkish': found, 'texts': F.texts_of(box)[:6]}
        print(name, len(found), found[:12], flush=True)
        try:
            F.click(box, close_pattern)
        except LookupError:
            box.type_keys('{ESC}')
        time.sleep(0.8)
        for d in F.dialogs(process):           # anything the close left behind
            if d.handle not in before:
                try:
                    d.type_keys('{ESC}')
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001
        results[name] = {'error': f'{type(exc).__name__}: {exc}', 'trace': traceback.format_exc()[-800:],
                         'dialogs': [(d.window_text(), F.texts_of(d)[:5], F.buttons(d)[:6]) for d in F.dialogs(process)]}
        print(name, 'ERROR', exc, flush=True)
        for d in F.dialogs(process):
            try:
                d.close()
            except Exception:  # noqa: BLE001
                pass


try:
    L.add(window, app, video, 8)
    dark = brightness(window)
    switch(window, 'English')
    time.sleep(2)
    results['main window'] = {'turkish': leftovers(window)}
    for tab_name in ('Edit', 'Publish', '✦ AI Edit'):
        F.tab(window, tab_name)
        time.sleep(0.6)
        results[f'tab {tab_name}'] = {'turkish': leftovers(window)}
    print('main', results['main window']['turkish'][:20], flush=True)

    opened('Inspiration', lambda: U.press(window, 'Inspiration'))
    opened('Templates', lambda: U.press(window, '◈   Templates'))
    opened('Story Studio', lambda: U.press(window, 'Story Studio'), close_pattern=r'(Close|Kapat)')
    opened('Shortcuts (F1)', lambda: L.keys(window, '{F1}'))
    opened('Record', lambda: U.press(window, '  Record'), close_pattern=r'(Close|Cancel)')
    F.tab(window, '✦ AI Edit')
    opened('Remove silences', lambda: U.press(window, 'Remove silences'), close_pattern='Cancel')
    F.tab(window, 'Publish')
    opened('Split into Shorts', lambda: U.press(window, 'Split into Shorts'), close_pattern='Cancel')
    opened('Batch export', lambda: U.press(window, 'Batch export'), close_pattern='Cancel')
    opened('Find highlights (short video)', lambda: U.press(window, 'Find highlights'))
    # The version button's screen-reader name is its tooltip ("Installed version: … Click to check for updates.").
    # It answers in the status line: up to date, running from source, or a question when a newer version exists.
    try:
        U.press(window, '(Installed version|Kurulu sürüm)')
        said = U.wait_for(lambda: [t for t in U.status(window) if re.search(r'up to date|from source|Checking|'
                                                                            r'could not|update', t, re.I)
                                   and 'Click to check' not in t], timeout=60, step=1, what='güncelleme yanıtı')
        time.sleep(3)
        said = [t for t in U.status(window) if re.search(r'up to date|from source|could not|update', t, re.I)
                and 'Click to check' not in t] or said
        results['Version button'] = {'status': said, 'turkish': [t for t in said if TURKISH.search(t)
                                                                  and not any(a in t for a in ALLOWED)],
                                     'dialogs': [F.texts_of(d) for d in F.dialogs(process)]}
        for d in F.dialogs(process):
            F.click(d, r'(No|Hayır|Later|Cancel|OK)')
    except Exception as exc:  # noqa: BLE001
        results['Version button'] = {'error': f'{type(exc).__name__}: {exc}'}
    results['status line'] = {'turkish': sorted({t for t in U.status(window) if TURKISH.search(t)
                                                 and not any(a in t for a in ALLOWED)})}

    switch(window, 'Türkçe')
    time.sleep(2)
    back = U.status(window) + [b.window_text() for b in window.descendants(control_type='Button')]
    results['back to Turkish'] = {'ok': all(any(w in t for t in back) for w in ('Dışa aktar', 'Video ekle', 'Proje aç')),
                                  'english_left': sorted({t for t in back if t in ('Export  ↗', 'Open project', 'Save project',
                                                                                    '＋  Add video', 'Remove silences')})}
    switch(window, 'Açık')
    time.sleep(1.5)
    light = brightness(window)
    switch(window, 'Koyu')
    time.sleep(1.5)
    results['theme'] = {'dark': round(dark, 1), 'light': round(light, 1), 'dark_again': round(brightness(window), 1),
                        'ok': light > dark + 40}
finally:
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_language.json').write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps({k: (len(v.get('turkish', [])) if 'turkish' in v else v.get('ok', v.get('error')))
                      for k, v in results.items() if isinstance(v, dict)}, ensure_ascii=False))
