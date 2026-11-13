"""Opening a file handed to the app: on the command line, by “Open with”, or dropped on the window."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

import main
from main import MainWindow, startup_file

app = QApplication.instance() or QApplication([])


class StartupArgumentTests(unittest.TestCase):
    def test_first_plain_argument_is_the_file(self):
        self.assertEqual(startup_file(['app.exe']), '')
        self.assertEqual(startup_file(['app.exe', 'C:/v/proje.akis.json']), 'C:/v/proje.akis.json')
        self.assertEqual(startup_file(['app.exe', '', 'a.mp4']), 'a.mp4')

    def test_options_are_not_files(self):
        self.assertEqual(startup_file(['app.exe', '--audio-diagnostic', 'report.json']), '')
        self.assertEqual(startup_file(['app.exe', '--whisper-diagnostic', 'report.json']), '')


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

    def video(self, name='a.mp4'):
        path = self.root / name
        path.touch()
        return path

    def test_video_is_added_and_project_is_opened(self):
        w = self.window
        self.assertTrue(w.open_path(str(self.video())))
        self.assertEqual(Path(w.state.source).name, 'a.mp4')
        project = self.root / 'kayit.akis.json'
        w.write_project(str(project))
        w.apply_preset(9, 9, 9)
        with patch.object(w, 'confirm_close', return_value=True):
            self.assertTrue(w.open_path(str(project)))
        self.assertEqual(w.brightness.value(), 0)          # the saved project came back

    def test_declining_the_unsaved_work_question_keeps_the_project(self):
        w = self.window
        w.open_path(str(self.video()))
        project = self.root / 'kayit.akis.json'
        w.write_project(str(project))
        w.apply_preset(9, 9, 9)
        with patch.object(w, 'confirm_close', return_value=False), patch.object(w, 'open_project_file') as opened:
            self.assertFalse(w.open_path(str(project)))
        opened.assert_not_called()
        self.assertEqual(w.brightness.value(), 9)

    def test_missing_and_unsupported_files_only_say_so(self):
        w = self.window
        self.assertFalse(w.open_path(str(self.root / 'yok.mp4')))
        self.assertEqual(w.status_label.text(), 'Dosya bulunamadı: yok.mp4')
        note = self.root / 'not.txt'
        note.write_text('x')
        self.assertFalse(w.open_path(str(note)))
        self.assertEqual(w.status_label.text(), 'Bu dosya türü açılamıyor: not.txt')
        self.assertEqual(w.state.source, '')

    def test_project_file_can_be_dropped_on_the_window(self):
        w = self.window
        project = self.root / 'kayit.akis.json'
        project.write_text('{}')
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(project))])
        enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        w.dragEnterEvent(enter)
        self.assertTrue(enter.isAccepted())
        drop = QDropEvent(QPoint(5, 5), Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        with patch.object(w, 'open_path') as opened:
            w.dropEvent(drop)
        opened.assert_called_once_with(str(project).replace('\\', '/'))


if __name__ == '__main__':
    unittest.main()
