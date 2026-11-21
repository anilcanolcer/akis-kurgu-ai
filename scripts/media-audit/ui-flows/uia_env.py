"""Start the editor as its own process and press its buttons from outside, through Windows UI Automation.

pywinauto is not a dependency of the program: install it next to these scripts (see README.md here), or point
AKIS_UIA_LIBS at a folder that holds it.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

S = Path(__file__).resolve().parent
LIBS = Path(os.environ.get('AKIS_UIA_LIBS') or S / '.uia')
for part in ('', 'win32', 'win32/lib', 'pythonwin'):
    sys.path.insert(0, str(LIBS / part))
if (LIBS / 'pywin32_system32').is_dir():
    os.add_dll_directory(str(LIBS / 'pywin32_system32'))
    os.environ['PATH'] = str(LIBS / 'pywin32_system32') + os.pathsep + os.environ['PATH']

from pywinauto import Desktop, keyboard, mouse  # noqa: E402,F401  (mouse: used by the flows through this module)
from pywinauto.application import Application  # noqa: E402

REPO = S.parents[2]
PYTHON = REPO / '.venv' / 'Scripts' / 'python.exe'
TITLE = r'.*Akış Kurgu AI.*'


RECOVERY = Path(os.environ['LOCALAPPDATA']) / 'AkisStudio' / 'Akış Kurgu AI' / 'recovery'
BEFORE = {p.name for p in RECOVERY.glob('*')} if RECOVERY.is_dir() else set()


def clean_recovery():
    """Remove only the recovery files these test sessions made (the person's own ones stay)."""
    if RECOVERY.is_dir():
        for p in RECOVERY.glob('*'):
            if p.name not in BEFORE:
                try:
                    p.unlink()
                except OSError:
                    pass


def dismiss_recovery(window, timeout=6):
    """At start the editor may offer a recovered session: answer "Sonra sor" (keeps the file, opens nothing)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for d in [c for c in window.children() if c.element_info.control_type == 'Window']:
            texts = [c.window_text() for c in d.descendants(control_type='Text')]
            if any('Kurtarılmış çalışma' in t for t in texts):
                for b in d.descendants(control_type='Button'):
                    if b.window_text() == 'Sonra sor':
                        b.invoke()
                        return texts
        time.sleep(0.3)
    return None


def start(exe=None, settings=None, args=(), recovery='later', command=None):
    """recovery='later' answers a startup recovery offer with "Sonra sor"; None leaves it to the caller.
    command replaces how the editor is started (e.g. fake_ai_launch.py)."""
    env = dict(os.environ)
    env['QT_QPA_PLATFORM'] = 'windows'
    env.pop('AKIS_RUN_WINDOWS_GUI_SMOKE', None)
    if settings:
        env['AKIS_SETTINGS_FILE'] = str(settings)
    command = list(command or ([str(exe)] if exe else [str(PYTHON), str(REPO / 'main.py')]))
    process = subprocess.Popen(command + list(args), cwd=str(REPO), env=env)
    deadline = time.time() + 90
    while True:
        owners = family(process.pid)        # the venv's python.exe starts the real interpreter as a child
        found = [w for w in Desktop(backend='uia').windows(title_re=TITLE, control_type='Window')
                 if w.process_id() in owners]
        if found:
            app = Application(backend='uia').connect(process=found[0].process_id())
            window = app.window(handle=found[0].handle)
            window.wait('visible', timeout=10)
            process.owners = owners
            process.recovery_offer = dismiss_recovery(window) if not args and recovery == 'later' else None
            return process, app, window
        if time.time() > deadline or process.poll() is not None:
            raise TimeoutError('düzenleyici penceresi açılmadı')
        time.sleep(1)


def family(pid):
    """`pid` and its child processes."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_char * 260)]
    kernel = ctypes.windll.kernel32
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)
    pairs = []
    ok = kernel.Process32First(snapshot, ctypes.byref(entry))
    while ok:
        pairs.append((entry.th32ProcessID, entry.th32ParentProcessID))
        ok = kernel.Process32Next(snapshot, ctypes.byref(entry))
    kernel.CloseHandle(snapshot)
    owners = {pid}
    for _ in range(3):
        owners |= {child for child, parent in pairs if parent in owners}
    return owners


def stop(process):
    for pid in sorted(getattr(process, 'owners', {process.pid}) | family(process.pid), reverse=True):
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)


def button(window, name, timeout=10):
    """A button whose name contains `name` (Qt gives a button its text as its name)."""
    control = window.child_window(title_re=f'.*{name}.*', control_type='Button')
    control.wait('exists', timeout=timeout)
    return control


def press(window, name, timeout=10):
    control = button(window, name, timeout)
    control.invoke() if hasattr(control, 'invoke') else control.click_input()
    return control


def windows_of(app):
    """Top-level windows of the editor and the dialogs it owns (UIA lists those under the main window)."""
    out = []
    for w in Desktop(backend='uia').windows():
        if w.process_id() == app.process:
            out.append(w)
            children = [c for c in w.children() if c.element_info.control_type == 'Window']
            out += children
            for child in children:     # a file dialog opened from a dialog (e.g. Toplu dışa aktar › Video ekle)
                out += [c for c in child.children() if c.element_info.control_type == 'Window']
    return out


def file_dialog(app, path, title_re=None, timeout=20, replace=None):
    """Fill the open or save dialog the editor shows (Windows' own) and confirm it."""
    deadline = time.time() + timeout
    while True:
        dialogs = [w for w in windows_of(app) if w.element_info.class_name == '#32770']
        if dialogs:
            break
        if time.time() > deadline:
            raise TimeoutError('dosya penceresi açılmadı')
        time.sleep(0.3)
    dialog = dialogs[0]
    edits = dialog.descendants(control_type='Edit')
    named = [e for e in edits if e.element_info.automation_id in ('1148', '1001')
             or re.match(r'(Dosya adı|File name)', e.element_info.name or '')]
    try:
        named[0].set_edit_text(str(path))
    except Exception:   # noqa: BLE001   (the save dialog's box refuses the value pattern: paste instead)
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(str(path), win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        (named or edits)[0].set_focus()
        keyboard.send_keys('^a^v')
    time.sleep(0.2)
    keyboard.send_keys('{ENTER}')
    if replace is not None:                      # Windows' own "already exists, replace?" prompt
        deadline = time.time() + 6
        while time.time() < deadline:
            prompts = [d for d in dialog.descendants(control_type='Window')] + \
                      [d for w in windows_of(app) for d in w.descendants(control_type='Window') if d.element_info.class_name == '#32770']
            for prompt in prompts:
                buttons = {b.window_text().replace('&', ''): b for b in prompt.descendants(control_type='Button')}
                wanted = ('Evet', 'Yes') if replace else ('Hayır', 'No')
                for name in wanted:
                    if name in buttons and ({'Evet', 'Hayır'} <= set(buttons) or {'Yes', 'No'} <= set(buttons)):
                        dialog.replaced = [t.window_text() for t in prompt.descendants(control_type='Text')]
                        buttons[name].invoke()
                        if not replace:                    # back in the file dialog: close it
                            time.sleep(0.5)
                            keyboard.send_keys('{ESC}')
                        return dialog
            time.sleep(0.25)
    return dialog


def status(window):
    """Every label text in the window (the status line is one of them)."""
    return [c.window_text() for c in window.descendants(control_type='Text') if c.window_text()]


def wait_for(check, timeout=30, step=0.3, what='koşul'):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = check()
        if value:
            return value
        time.sleep(step)
    raise TimeoutError(f'{what} {timeout} saniyede gerçekleşmedi')
