import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError

from PySide6.QtWidgets import QApplication, QMessageBox

from akis.ai_providers import post_json
from akis.timeline_model import Clip, Track
from main import MainWindow

app = QApplication.instance() or QApplication([])


class UnsavedChangesTests(unittest.TestCase):
    def test_changes_are_tracked_from_load_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'demo.mp4'
            video.touch()
            window = MainWindow()
            with patch('akis.media_service.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
                self.assertFalse(window.has_unsaved_changes())  # nothing loaded yet
                window.load_video(str(video))
                self.assertFalse(window.has_unsaved_changes())
                window.multitrack.tracks[2].add(Clip('', 0, 10, text='Merhaba'))
                self.assertTrue(window.has_unsaved_changes())
                window.project_path = str(Path(tmp) / 'demo.akis.json')
                window.save_project()
                self.assertFalse(window.has_unsaved_changes())
                window.publish_title.setText('Yeni başlık')
                self.assertTrue(window.has_unsaved_changes())
            window._close_confirmed = True
            window.close()

    def test_visible_window_asks_before_closing_with_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'demo.mp4'
            video.touch()
            window = MainWindow()
            with patch('akis.media_service.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
                window.load_video(str(video))
            window.publish_title.setText('değişti')
            with patch.object(window, 'isVisible', return_value=True), \
                    patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Cancel) as ask:
                self.assertFalse(window.confirm_close())
                ask.assert_called_once()
            with patch.object(window, 'isVisible', return_value=True), \
                    patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Discard):
                self.assertTrue(window.confirm_close())
            window._close_confirmed = True
            window.close()

    def test_removing_a_track_with_clips_needs_confirmation(self):
        window = MainWindow()
        window.multitrack.tracks.append(Track('audio', 'Müzik', [Clip('a.wav', 0, 30)]))
        index = len(window.multitrack.tracks) - 1
        window.multitrack_view.selected_track = index
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.No), \
                patch.object(window, 'seek_timeline'):
            window.remove_track()
        self.assertEqual(window.multitrack.tracks[index].name, 'Müzik')
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
                patch.object(window, 'seek_timeline'):
            window.remove_track()
        self.assertFalse(any(t.name == 'Müzik' for t in window.multitrack.tracks))
        window.close()


class NetworkErrorTests(unittest.TestCase):
    def test_offline_error_is_explained(self):
        opener = Mock(side_effect=URLError('getaddrinfo failed'))
        with self.assertRaisesRegex(RuntimeError, 'bağlanılamadı'):
            post_json('OpenAI', 'https://api.openai.com/v1/responses', b'{}', {}, 5, opener=opener)

    def test_timeout_inside_urlerror_is_a_timeout(self):
        opener = Mock(side_effect=URLError(TimeoutError('timed out')))
        with self.assertRaisesRegex(RuntimeError, 'yanıt vermedi'):
            post_json('Gemini', 'https://example.invalid', b'{}', {}, 5, opener=opener)


if __name__ == '__main__':
    unittest.main()
