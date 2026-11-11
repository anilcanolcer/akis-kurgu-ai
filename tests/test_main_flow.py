import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from akis.timeline_model import Timeline, Track, Clip
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
             patch('main.project_service.load_project', return_value=({'state': {}}, 'bad.mp4', [])), \
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

    def test_long_timeline_scroll_reaches_late_clip(self):
        window = MainWindow()
        clip = Clip('late.mp4', 2400, 300)
        window.multitrack = Timeline(tracks=[Track('video', 'Video', [clip])])
        window.multitrack_view.set_model(window.multitrack)
        window.show(); app.processEvents()
        window.update_timeline_scroll()
        self.assertGreater(window.horizontal_timeline.maximum(), 0)
        window.horizontal_timeline.setValue(window.horizontal_timeline.maximum())
        app.processEvents()
        x = int(window.multitrack_view.x_for(clip.end - 30))
        self.assertGreaterEqual(x, 100)
        self.assertLess(x, window.multitrack_view.width())
        QTest.mouseClick(window.multitrack_view, Qt.MouseButton.LeftButton, pos=QPoint(x, 45))
        self.assertEqual(window.multitrack_view.selected, (0, clip.id))
        window.close()

    def test_profile_changes_real_export_size_and_aspect(self):
        window = MainWindow()
        window.export_profile.setCurrentText('4K UHD · 3840×2160')
        self.assertTrue(window.aspect.currentText().startswith('16:9'))
        self.assertEqual(window.export_canvas_size(), (3840, 2160))
        window.aspect.setCurrentIndex(2)
        self.assertEqual(window.export_canvas_size(), (2160, 2160))
        self.assertEqual(window.canvas_size(), (1080, 1080))
        window.export_profile.setCurrentText('Reels · 1080×1920')
        self.assertEqual(window.export_canvas_size(), (1080, 1920))
        window.close()

    def test_export_refuses_to_replace_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.mp4'
            source.write_bytes(b'original')
            window = MainWindow()
            window.state.source = str(source); window.state.duration = 1
            window.multitrack = Timeline(tracks=[Track('video', 'Video', [Clip(str(source), 0, 30)])])
            with patch('main.QFileDialog.getSaveFileName', return_value=(str(source), '')), \
                 patch('main.QMessageBox.warning') as warning, \
                 patch('main.TimelineRenderWorker') as worker:
                window.export_video()
                warning.assert_called_once(); worker.assert_not_called()
                self.assertEqual(source.read_bytes(), b'original')
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
