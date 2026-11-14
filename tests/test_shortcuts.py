"""Timeline keys: which key does what, when they stay out of the way, and the help list."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QSlider

from akis import shortcuts
from main import MainWindow

app = QApplication.instance() or QApplication([])
NONE, CTRL, SHIFT = shortcuts.NONE, shortcuts.CTRL, shortcuts.SHIFT


def press(key, modifiers=NONE):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


class TableTests(unittest.TestCase):
    def test_every_shortcut_is_unique_and_described(self):
        combos = [(key, modifiers) for key, modifiers, *_ in shortcuts.SHORTCUTS]
        self.assertEqual(len(combos), len(set(combos)))
        self.assertTrue(all(keys and what for _, _, keys, what, _ in shortcuts.SHORTCUTS))

    def test_help_lists_these_keys_and_the_windows_own(self):
        text = shortcuts.help_text()
        for _, _, keys, what, _ in shortcuts.SHORTCUTS:
            self.assertIn(keys, text)
            self.assertIn(what, text)
        for keys, what in shortcuts.BUILT_IN:
            self.assertIn(keys, text)
            self.assertIn(what, text)

    def test_help_is_translated(self):
        text = shortcuts.help_text('en')
        for part in ('Space', 'Play / pause', 'Split the selected clip at the playhead', 'One frame back',
                     'Show this list of shortcuts', 'Ctrl + Z'):
            self.assertIn(part, text)
        self.assertNotIn('Boşluk', text)

    def test_keys_the_window_handles_itself_are_not_handled_twice(self):
        for key, modifiers in ((Qt.Key.Key_Space, NONE), (Qt.Key.Key_Delete, NONE), (Qt.Key.Key_S, CTRL),
                               (Qt.Key.Key_O, CTRL), (Qt.Key.Key_E, CTRL), (Qt.Key.Key_Z, CTRL)):
            self.assertIsNone(shortcuts.find(key, modifiers))

    def test_find_matches_key_and_modifiers_exactly(self):
        self.assertIsNotNone(shortcuts.find(Qt.Key.Key_S, NONE))
        self.assertIsNone(shortcuts.find(Qt.Key.Key_S, SHIFT))
        self.assertIsNone(shortcuts.find(Qt.Key.Key_X, NONE))
        keypad = Qt.KeyboardModifier.KeypadModifier
        self.assertIs(shortcuts.find(Qt.Key.Key_Left, keypad), shortcuts.find(Qt.Key.Key_Left, NONE))


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=4.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))
        self.filter = self.window.shortcut_filter
        self.active = self.window

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def send(self, key, modifiers=NONE, focus=None):
        with patch('akis.shortcuts.QApplication.focusWidget', return_value=focus), \
             patch('akis.shortcuts.QApplication.activeWindow', return_value=self.active):
            return self.filter.eventFilter(self.window, press(key, modifiers))

    def test_arrows_home_and_end_move_the_playhead(self):
        w = self.window
        second = round(w.multitrack.fps_num / w.multitrack.fps_den)
        self.assertTrue(self.send(Qt.Key.Key_Right))
        self.assertEqual(w.timeline_frame, 1)
        self.send(Qt.Key.Key_Right, SHIFT)
        self.assertEqual(w.timeline_frame, 1 + second)
        self.send(Qt.Key.Key_Left)
        self.assertEqual(w.timeline_frame, second)
        self.send(Qt.Key.Key_Left, SHIFT)
        self.send(Qt.Key.Key_Left)                     # cannot go before the start
        self.assertEqual(w.timeline_frame, 0)
        self.send(Qt.Key.Key_End)
        self.assertEqual(w.timeline_frame, 4 * second - 1)
        self.send(Qt.Key.Key_Home)
        self.assertEqual(w.timeline_frame, 0)

    def test_s_splits_in_an_undoable_step(self):
        w = self.window
        index = next(i for i, t in enumerate(w.multitrack.tracks) if t.kind == 'video')
        clip = w.multitrack.tracks[index].clips[0]
        whole = clip.length
        w.multitrack_view.selected, w.multitrack_view.selected_track = (index, clip.id), index
        w.multitrack_view.playhead = 30
        self.assertTrue(self.send(Qt.Key.Key_S))
        self.assertEqual(len(w.multitrack.tracks[index].clips), 2)
        self.assertTrue(w.undo())
        self.assertEqual([c.length for c in w.multitrack.tracks[index].clips], [whole])

    def test_plain_keys_are_left_to_input_widgets_but_ctrl_keys_are_not(self):
        w = self.window
        for widget in (QLineEdit(), QSlider(), w.ai_prompt):
            self.assertFalse(self.send(Qt.Key.Key_Right, focus=widget), widget)
            self.assertFalse(self.send(Qt.Key.Key_S, focus=widget), widget)
        self.assertEqual(w.timeline_frame, 0)
        self.assertTrue(self.send(Qt.Key.Key_Right, focus=QPushButton()))   # a button does not need the arrows
        with patch.object(w, 'choose_video') as add:
            self.assertTrue(self.send(Qt.Key.Key_I, CTRL, focus=w.ai_prompt))
        add.assert_called_once()

    def test_f1_shows_the_list_in_the_ui_language(self):
        w = self.window
        with patch('akis.shortcuts.show_help') as shown:
            self.send(Qt.Key.Key_F1)
        shown.assert_called_once_with(w)
        w.apply_language('en')
        with patch('akis.shortcuts.QMessageBox') as box:
            shortcuts.show_help(w)
        box.return_value.setWindowTitle.assert_called_once_with('Keyboard shortcuts')
        self.assertIn('Play / pause', box.return_value.setInformativeText.call_args.args[0])
        w.apply_language('tr')

    def test_nothing_fires_behind_a_dialog_or_in_another_window(self):
        w = self.window
        with patch('akis.shortcuts.QApplication.activeModalWidget', return_value=QPushButton()):
            self.assertFalse(self.send(Qt.Key.Key_Right))
        for other in (None, QPushButton()):               # no window, or one that never registered
            self.active = other
            self.assertFalse(self.send(Qt.Key.Key_Right))
        self.assertEqual(w.timeline_frame, 0)

    def test_one_filter_serves_every_window(self):
        second = MainWindow()
        self.assertIs(second.shortcut_filter, self.filter)
        self.assertIn(second, self.filter.windows)
        second._close_confirmed = True
        second.close()
        second.deleteLater()
        del second
        gc.collect()
        self.assertIn(self.window, self.filter.windows)

    def test_other_keys_and_releases_pass_through(self):
        self.assertFalse(self.send(Qt.Key.Key_X))
        self.assertFalse(self.send(Qt.Key.Key_Space))     # the window's own action plays; not this filter
        release = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Right, NONE)
        self.assertFalse(self.filter.eventFilter(self.window, release))


if __name__ == '__main__':
    unittest.main()
