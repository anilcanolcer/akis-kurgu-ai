"""Keyboard shortcuts: which key does what, when they stay out of the way, and the help list."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
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


def press(key, modifiers=NONE, repeat=False):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers, '', repeat)


class TableTests(unittest.TestCase):
    def test_every_shortcut_is_unique_and_described(self):
        combos = [(key, modifiers) for key, modifiers, *_ in shortcuts.SHORTCUTS]
        self.assertEqual(len(combos), len(set(combos)))
        self.assertTrue(all(keys and what for _, _, keys, what, _ in shortcuts.SHORTCUTS))

    def test_help_lists_everything_including_undo(self):
        text = shortcuts.help_text()
        for _, _, keys, what, _ in shortcuts.SHORTCUTS:
            self.assertIn(keys, text)
            self.assertIn(what, text)
        self.assertIn('Ctrl + Z', text)

    def test_find_matches_key_and_modifiers_exactly(self):
        self.assertIsNotNone(shortcuts.find(Qt.Key.Key_S, NONE))
        self.assertIsNot(shortcuts.find(Qt.Key.Key_S, NONE), shortcuts.find(Qt.Key.Key_S, CTRL))
        self.assertIsNone(shortcuts.find(Qt.Key.Key_S, CTRL | SHIFT))
        self.assertIsNone(shortcuts.find(Qt.Key.Key_Q, NONE))
        keypad = Qt.KeyboardModifier.KeypadModifier
        self.assertIs(shortcuts.find(Qt.Key.Key_Left, keypad), shortcuts.find(Qt.Key.Key_Left, NONE))


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.MediaService.duration', return_value=4.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
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
        with patch('akis.shortcuts.QApplication.focusWidget', return_value=focus),              patch('akis.shortcuts.QApplication.activeWindow', return_value=self.active):
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

    def test_s_splits_and_delete_removes_in_undoable_steps(self):
        w = self.window
        index = next(i for i, t in enumerate(w.multitrack.tracks) if t.kind == 'video')
        clip = w.multitrack.tracks[index].clips[0]
        whole = clip.length
        w.multitrack_view.selected, w.multitrack_view.selected_track = (index, clip.id), index
        w.multitrack_view.playhead = 30
        self.assertTrue(self.send(Qt.Key.Key_S))
        self.assertEqual(len(w.multitrack.tracks[index].clips), 2)
        self.assertTrue(self.send(Qt.Key.Key_Delete))
        self.assertEqual(len(w.multitrack.tracks[index].clips), 1)
        self.assertTrue(w.undo())
        self.assertTrue(w.undo())
        self.assertEqual(len(w.multitrack.tracks[index].clips), 1)
        self.assertEqual(w.multitrack.tracks[index].clips[0].length, whole)

    def test_plain_keys_are_left_to_input_widgets_but_ctrl_keys_are_not(self):
        w = self.window
        for widget in (QLineEdit(), QSlider(), w.ai_prompt):
            self.assertFalse(self.send(Qt.Key.Key_Right, focus=widget), widget)
            self.assertFalse(self.send(Qt.Key.Key_S, focus=widget), widget)
        self.assertEqual(w.timeline_frame, 0)
        self.assertTrue(self.send(Qt.Key.Key_Right, focus=QPushButton()))   # a button does not need the arrows
        with patch.object(w, 'save_project') as save:
            self.assertTrue(self.send(Qt.Key.Key_S, CTRL, focus=w.ai_prompt))
        save.assert_called_once()

    def test_ctrl_keys_reach_their_commands(self):
        w = self.window
        for key, name in ((Qt.Key.Key_O, 'open_project'), (Qt.Key.Key_E, 'export_video'), (Qt.Key.Key_I, 'choose_video')):
            with patch.object(w, name) as command:
                self.assertTrue(self.send(key, CTRL))
            command.assert_called_once()
        with patch('akis.shortcuts.show_help') as shown:
            self.send(Qt.Key.Key_F1)
        shown.assert_called_once_with(w)

    def test_space_plays_only_when_there_is_a_video(self):
        w = self.window
        with patch.object(w, 'toggle_play') as play:
            self.send(Qt.Key.Key_Space)
            play.assert_called_once()
            w.state.source = ''
            self.send(Qt.Key.Key_Space)
            play.assert_called_once()                  # no file dialog out of nowhere

    def test_nothing_fires_behind_a_dialog_or_in_another_window(self):
        w = self.window
        with patch('akis.shortcuts.QApplication.activeModalWidget', return_value=QPushButton()):
            self.assertFalse(self.send(Qt.Key.Key_Right))
        for other in (None, QPushButton()):               # no window, or one that never registered
            self.active = other
            self.assertFalse(self.send(Qt.Key.Key_Right))
        self.assertEqual(w.timeline_frame, 0)

    def test_one_filter_serves_every_window_and_forgets_closed_ones(self):
        second = MainWindow()
        self.assertIs(second.shortcut_filter, self.filter)
        self.assertIn(second, self.filter.windows)
        second._close_confirmed = True
        second.close()
        second.deleteLater()
        del second
        import gc
        gc.collect()
        self.assertIn(self.window, self.filter.windows)

    def test_held_space_does_not_toggle_again(self):
        with patch.object(self.window, 'toggle_play') as play,              patch('akis.shortcuts.QApplication.focusWidget', return_value=None),              patch('akis.shortcuts.QApplication.activeWindow', return_value=self.window):
            self.assertTrue(self.filter.eventFilter(self.window, press(Qt.Key.Key_Space, repeat=True)))
        play.assert_not_called()

    def test_other_keys_and_releases_pass_through(self):
        self.assertFalse(self.send(Qt.Key.Key_Q))
        release = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Right, NONE)
        self.assertFalse(self.filter.eventFilter(self.window, release))


if __name__ == '__main__':
    unittest.main()
