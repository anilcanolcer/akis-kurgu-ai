import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from main import MainWindow

app = QApplication.instance() or QApplication([])

class MainWindowFlowTests(unittest.TestCase):
    def test_video_load_and_volume_use_timeline_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'demo.mp4'
            video.touch()
            window = MainWindow()
            with patch('main.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
                window.load_video(str(video))
            self.assertEqual(window.multitrack.tracks[0].clips[0].length, 60)
            window.preview_audio_output.setVolume(.3)
            self.assertAlmostEqual(window.preview_audio_output.volume(), .3, places=2)
            window.close()

    def test_adding_video_keeps_project_and_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / 'first.mp4'; first.touch()
            second = Path(tmp) / 'second.mp4'; second.touch()
            window = MainWindow()
            with patch('main.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
                window.load_video(str(first))
                window.project_path = str(Path(tmp) / 'original.akis.json')
                original = window.multitrack.tracks[0].clips[0]
                window.add_video(str(second))
                self.assertEqual([c.source for c in window.multitrack.tracks[0].clips], [str(first), str(second)])
                self.assertIs(window.multitrack.tracks[0].clips[0], original)
                self.assertEqual(window.multitrack.tracks[0].clips[1].start, 60)
                self.assertTrue(window.project_path.endswith('original.akis.json'))
            window.close()

    def test_failed_project_open_does_not_change_target(self):
        window = MainWindow()
        window.project_path = 'existing.akis.json'
        with patch('main.QFileDialog.getOpenFileName', return_value=('broken.akis.json', '')), \
             patch('main.project_service.load_with_source', return_value=({'state': {}}, 'bad.mp4')), \
             patch.object(window, 'load_video', return_value=None):
            window.open_project()
            self.assertEqual(window.project_path, 'existing.akis.json')
            self.assertIsNone(window._pending_project)
        window.close()

    def test_reopen_restores_all_project_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / 'first.mp4'; first.touch()
            second = Path(tmp) / 'second.mp4'; second.touch()
            project = Path(tmp) / 'demo.akis.json'
            window = MainWindow()
            with patch('main.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
                window.load_video(str(first))
                window.add_video(str(second))
                window.write_project(str(project))
                with patch('main.QFileDialog.getOpenFileName', return_value=(str(project), '')):
                    window.open_project()
                self.assertEqual(window.media_bin.paths, [str(first), str(second)])
            window.close()

    def test_save_failure_is_reported_without_setting_path(self):
        window = MainWindow()
        window.state.source = 'video.mp4'
        with patch('main.QFileDialog.getSaveFileName', return_value=('target.akis.json', '')), \
             patch.object(window, 'write_project', side_effect=OSError('disk full')), \
             patch('main.QMessageBox.critical') as message:
            window.save_project()
            message.assert_called_once()
            self.assertEqual(window.project_path, '')
        window.close()

if __name__ == '__main__': unittest.main()
