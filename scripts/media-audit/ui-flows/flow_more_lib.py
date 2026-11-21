"""UI steps shared by the second round of flows (publish tab, edit tools, language, recovery)."""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402


def dialogs(process):
    """Every dialog the editor shows (Qt and native), wherever UIA lists it."""
    out = []
    for w in U.Desktop(backend='uia').windows():
        if w.process_id() in process.owners:
            children = [c for c in w.children() if c.element_info.control_type == 'Window']
            # a dialog opened from a dialog (Şablonlarım › name, Toplu dışa aktar › files) comes first
            for child in children:
                out += [c for c in child.children() if c.element_info.control_type == 'Window']
            out += children
            if w.handle != getattr(process, 'main', None):     # a dialog shown as its own top-level window
                out.append(w)
    return out


def texts_of(box):
    return [c.window_text() for c in box.descendants(control_type='Text') if c.window_text()]


def wait_dialog(process, contains='', title='', timeout=30, native=False):
    """The first dialog whose texts (or title) contain `contains` / `title`."""
    def find():
        for d in dialogs(process):
            if (d.element_info.class_name == '#32770') != native:
                continue
            if title and title not in d.window_text():
                continue
            texts = texts_of(d)
            if contains and contains not in ' '.join(texts):
                continue
            if not title and not contains and not texts:
                continue
            return d
        return None
    return U.wait_for(find, timeout=timeout, what=f'"{contains or title}" penceresi')


def buttons(box):
    return [b.window_text() for b in box.descendants(control_type='Button')]


def click(box, pattern):
    for b in box.descendants(control_type='Button'):
        if re.fullmatch(pattern, b.window_text().replace('&', '').strip()):
            b.invoke()
            return b.window_text()
    raise LookupError(f'{pattern} yok: {buttons(box)}')


def answer(process, contains, pattern=r'(OK|Tamam)', timeout=60):
    """Wait for a message containing `contains`, press the button matching `pattern`; returns its texts."""
    box = wait_dialog(process, contains=contains, timeout=timeout)
    texts = texts_of(box)
    click(box, pattern)
    # Invoke returns before the box has closed; a key sent meanwhile goes to the box, not the editor.
    import ctypes

    def gone():
        try:
            return not ctypes.windll.user32.IsWindow(box.handle) or not box.is_visible()
        except Exception:  # noqa: BLE001
            return True
    try:
        U.wait_for(gone, timeout=5, step=0.1, what='ileti kutusunun kapanması')
    except TimeoutError:
        pass
    time.sleep(0.4)
    return texts


def tab(window, name):
    item = window.child_window(title=name, control_type='TabItem')
    item.wait('exists', timeout=10)
    try:
        item.select()
    except Exception:  # noqa: BLE001
        item.click_input()
    time.sleep(0.4)


def describe(box, limit=80):
    """Control types, names and ids under `box` (for the log when a step cannot find what it needs)."""
    out = []
    for c in box.descendants()[:limit]:
        info = c.element_info
        out.append((info.control_type, (info.name or '')[:60], info.automation_id, info.class_name))
    return out


def qt_folder(process, folder, title='Kaydedilecek klasör', timeout=30):
    """Fill Qt's own folder picker (the editor uses it instead of Windows' for Shorts and highlights).
    The folder is made first, as a person would with the picker's "new folder" button."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    box = wait_dialog(process, title=title, timeout=timeout)
    edits = [e for e in box.descendants(control_type='Edit')
             if 'fileName' in (e.element_info.automation_id or '') or (e.element_info.name or '') in ('Directory:', 'Klasör:', 'Dizin:')]
    if not edits:
        edits = box.descendants(control_type='Edit')
    edit = edits[-1]
    try:
        edit.set_edit_text(str(folder))
    except Exception:  # noqa: BLE001
        edit.set_focus()
        U.keyboard.send_keys('^a')
        U.keyboard.send_keys(str(folder), with_spaces=True, pause=0.01)
    time.sleep(0.4)
    for name in (r'Choose', r'Seç', r'Open', r'Aç', r'Tamam', r'OK'):
        try:
            return click(box, name)
        except LookupError:
            continue
    U.keyboard.send_keys('{ENTER}')
    return 'ENTER'


def description(control):
    """What Qt gives UIA as the control's description: its tooltip, or a line edit's placeholder."""
    for prop in (30159, 30013):          # FullDescription, HelpText
        try:
            value = control.element_info.element.GetCurrentPropertyValue(prop)
        except Exception:  # noqa: BLE001
            value = ''
        if value:
            return value
    return ''


def close_lists():
    """Close a combo list left open: an open list takes every key that follows."""
    for _ in range(3):
        if not U.Desktop(backend='uia').windows(class_name='QComboBoxPrivateContainer'):
            return
        U.keyboard.send_keys('{ESC}')
        time.sleep(0.4)


def choose(combo, text):
    """Pick `text` in a combo box (UIA selection; Qt does not give UIA the items' texts or the keyboard
    focus for a combo, so the list cannot be read or walked with keys), then close any list left open."""
    if combo.selected_text() == text:
        return
    try:
        combo.select(text)
    finally:
        time.sleep(0.5)
        close_lists()
    if combo.selected_text() != text:
        raise RuntimeError(f'"{text}" seçilemedi ({combo.selected_text()!r})')


def combo_offering(window, text):
    """The combo box that offers `text`; it is selected in it on the way."""
    for combo in window.descendants(control_type='ComboBox'):
        if combo.rectangle().width() <= 0:
            continue
        try:
            choose(combo, text)
            return combo
        except Exception:  # noqa: BLE001
            continue
    raise LookupError(f'"{text}" seçeneği olan liste yok')


def focused():
    """[control type, name, class, automation id] of the control that has the keyboard focus."""
    from pywinauto.uia_element_info import UIAElementInfo
    from pywinauto.uia_defines import IUIA
    info = UIAElementInfo(IUIA().iuia.GetFocusedElement())
    return [info.control_type, info.name, info.class_name, info.automation_id]


def cells(box):
    """The texts of a table's cells (Qt tables show cells as DataItem or ListItem)."""
    out = []
    for kind in ('DataItem', 'ListItem', 'TreeItem'):
        out += [c.window_text() for c in box.descendants(control_type=kind)]
    return out


def native_files(app, folder, names, timeout=20):
    """Choose several files in Windows' open dialog: go to `folder`, then name them in quotes."""
    U.file_dialog(app, folder, timeout=timeout)
    time.sleep(1.0)
    U.file_dialog(app, ' '.join(f'"{n}"' for n in names), timeout=timeout)
