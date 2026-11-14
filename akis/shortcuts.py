"""Timeline keys for the editor window, and the help text that lists every shortcut.

The window's own actions handle Ctrl+Z/Y, Ctrl+S/O/E, Space and Delete. This module adds the keys that
move along the timeline and edit at the playhead, plus F1. Self-contained: install(window) is the only
call the host makes. Plain keys are left to whatever input widget has the focus, so typing a caption or
nudging a slider works as before; they act on the timeline everywhere else. Ctrl combinations always act.
"""
import weakref

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox, QLineEdit,
                               QListWidget, QMessageBox, QPlainTextEdit, QTextEdit)

from akis import i18n

INPUTS = (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QComboBox, QAbstractSlider, QListWidget)
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


def _step(window, frames):
    window.seek_timeline(window.timeline_frame + frames)


def _second(window):
    timeline = window.multitrack
    return max(1, round(timeline.fps_num / timeline.fps_den))


# (key, modifiers, text shown in the help, what it does, action(window))
SHORTCUTS = (
    (Qt.Key.Key_S, NONE, 'S', 'Seçili klibi oynatma çizgisinden böl', lambda w: w.split_clip()),
    (Qt.Key.Key_Q, NONE, 'Q', 'Seçili klibin oynatma çizgisinden önceki kısmını at', lambda w: w.trim_left()),
    (Qt.Key.Key_W, NONE, 'W', 'Seçili klibin oynatma çizgisinden sonraki kısmını at', lambda w: w.trim_right()),
    (Qt.Key.Key_Escape, NONE, 'Esc', 'Seçili aralığı bırak', lambda w: w.multitrack_view.set_range(None)),
    (Qt.Key.Key_Left, NONE, '←', 'Bir kare geri', lambda w: _step(w, -1)),
    (Qt.Key.Key_Right, NONE, '→', 'Bir kare ileri', lambda w: _step(w, 1)),
    (Qt.Key.Key_Left, SHIFT, 'Shift + ←', 'Bir saniye geri', lambda w: _step(w, -_second(w))),
    (Qt.Key.Key_Right, SHIFT, 'Shift + →', 'Bir saniye ileri', lambda w: _step(w, _second(w))),
    (Qt.Key.Key_Home, NONE, 'Home', 'Başa git', lambda w: w.seek_timeline(0)),
    (Qt.Key.Key_End, NONE, 'End', 'Sona git', lambda w: w.seek_timeline(1 << 40)),
    (Qt.Key.Key_I, CTRL, 'Ctrl + I', 'Video ekle', lambda w: w.choose_video()),
    (Qt.Key.Key_F1, NONE, 'F1', 'Bu kısayol listesini göster', lambda w: show_help(w)),
)
# Handled by the window's own actions; listed so the help is complete.
BUILT_IN = (('Boşluk', 'Oynat / duraklat'), ('Delete', 'Seçili aralığı ya da klibi sil'),
            ('Ctrl + Z', 'Son adımı geri al'), ('Ctrl + Y', 'Geri alınan adımı yinele'),
            ('Ctrl + O', 'Proje aç'), ('Ctrl + S', 'Projeyi kaydet'), ('Ctrl + E', 'Videoyu dışa aktar'))
TITLE = 'Klavye kısayolları'
NOTE = 'Yazı alanına yazarken tek tuşlu kısayollar çalışmaz; yazdığınız harf yazıya gider.'
KEY_NAMES = ('Boşluk',)  # key names that are words and need translating; the rest are symbols or key caps


def help_text(language='tr'):
    """Every shortcut, one per line, keys aligned."""
    say = lambda text: i18n.translate(text, language)
    rows = (list(BUILT_IN[:2]) + [(keys, what) for _, _, keys, what, _ in SHORTCUTS[:-1]] + list(BUILT_IN[2:])
            + [SHORTCUTS[-1][2:4]])
    rows = [(say(keys) if keys in KEY_NAMES else keys, say(what)) for keys, what in rows]
    width = max(len(keys) for keys, _ in rows)
    return '\n'.join(f'{keys.ljust(width)}   {what}' for keys, what in rows)


def show_help(window):
    language = window.ui_language() if hasattr(window, 'ui_language') else 'tr'
    box = QMessageBox(window)
    box.setWindowTitle(i18n.translate(TITLE, language))
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(i18n.translate(NOTE, language))
    box.setInformativeText(f'<pre>{help_text(language)}</pre>')
    box.exec()


def find(key, modifiers):
    """The action for a key press, or None. Keypad and other incidental modifier bits are ignored."""
    wanted = modifiers & (CTRL | SHIFT | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
    for shortcut_key, shortcut_modifiers, _, _, action in SHORTCUTS:
        if key == shortcut_key and wanted == shortcut_modifiers:
            return action
    return None


class ShortcutFilter(QObject):
    """One application-wide key filter for every editor window: a press acts on the window that is active.

    A single filter, however many windows register: every event of the application passes through it, so
    it must stay cheap and must not multiply.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.windows = weakref.WeakSet()

    def target(self):
        """The registered window that has the keyboard, or None."""
        if QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None:
            return None
        window = QApplication.activeWindow()
        return window if window is not None and window in self.windows else None

    @staticmethod
    def applies(modifiers, focus):
        """Plain keys are left to an input widget that has the focus; Ctrl combinations always act."""
        return bool(modifiers & CTRL) or not isinstance(focus, INPUTS)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.KeyPress:
            return False
        action = find(event.key(), event.modifiers())
        if action is None:
            return False
        window = self.target()
        if window is None or not self.applies(event.modifiers(), QApplication.focusWidget()):
            return False
        action(window)
        return True


_filter = None


def install(window):
    """Give the window its timeline keys; returns the shared filter."""
    global _filter
    if _filter is None:
        _filter = ShortcutFilter(QApplication.instance())
        QApplication.instance().installEventFilter(_filter)
    _filter.windows.add(window)
    return _filter
