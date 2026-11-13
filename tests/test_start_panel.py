"""The three-step start panel: shown on an empty project, gone once there is something to edit."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel

from akis.start_panel import STEPS, StartPanel
from main import MainWindow

app = QApplication.instance() or QApplication([])


class PanelTests(unittest.TestCase):
    def test_three_steps_and_the_two_actions(self):
        calls = []
        panel = StartPanel(add_video=lambda: calls.append('add'), show_templates=lambda: calls.append('templates'))
        texts = [label.text() for label in panel.findChildren(QLabel)]
        for title, hint, _button, _action in STEPS:
            self.assertIn(title, texts)
            self.assertIn(hint, texts)
        self.assertEqual([number for number in texts if number in ('1', '2', '3')], ['1', '2', '3'])
        panel.buttons['add'].click()
        panel.buttons['templates'].click()
        self.assertEqual(calls, ['add', 'templates'])


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_empty_project_shows_it_and_a_video_hides_it(self):
        w = self.window
        w.seek_timeline(0)
        self.assertFalse(w.start_panel.isHidden())
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(w.load_video(str(video)))
        self.assertTrue(w.start_panel.isHidden())

    def test_buttons_reach_the_windows_commands(self):
        w = self.window
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=('', '')) as chooser:
            w.start_panel.buttons['add'].click()
        chooser.assert_called_once()
        with patch('akis.template_dialog.TemplateDialog.exec', new=lambda dialog: 0):
            w.start_panel.buttons['templates'].click()      # opens Templates; dismissed, nothing changes
        self.assertFalse(w.undo())

    def test_template_tracks_alone_do_not_hide_it_but_a_title_does(self):
        w = self.window
        w.seek_timeline(0)
        self.assertFalse(w.start_panel.isHidden())
        with patch('akis.template_dialog.TemplateDialog.exec', new=lambda dialog: 1):
            w.show_templates()                               # adds tracks and a three-second title clip
        self.assertTrue(w.start_panel.isHidden())            # there is something on the timeline now

    def test_texts_follow_the_language(self):
        w = self.window
        w.apply_language('en')
        texts = [label.text() for label in w.start_panel.findChildren(QLabel)]
        self.assertIn('Your first video in three steps', texts)
        self.assertEqual(w.start_panel.buttons['add'].text(), 'Choose video')
        self.assertEqual(w.start_panel.buttons['templates'].text(), 'Templates')
        w.apply_language('tr')
        self.assertEqual(w.start_panel.buttons['add'].text(), 'Video seç')


if __name__ == '__main__':
    unittest.main()
