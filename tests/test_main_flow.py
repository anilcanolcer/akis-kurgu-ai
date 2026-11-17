import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
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
            with patch('akis.media_service.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
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
            with patch('akis.media_service.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
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
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=('broken.akis.json', '')), \
             patch('akis.project_service.load_project', return_value=({'state': {}}, 'bad.mp4', [])), \
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
            with patch('akis.media_service.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
                window.load_video(str(first))
                window.add_video(str(second))
                window.write_project(str(project))
                with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(project), '')):
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
        window._close_confirmed = True  # a visible window with clips now asks before closing
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
            with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(source), '')), \
                 patch('main.QMessageBox.warning') as warning, \
                 patch('akis.window.exporting.TimelineRenderWorker') as worker:
                window.export_video()
                warning.assert_called_once(); worker.assert_not_called()
                self.assertEqual(source.read_bytes(), b'original')
            window.close()

    def test_save_failure_is_reported_without_setting_path(self):
        window = MainWindow()
        window.state.source = 'video.mp4'
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=('target.akis.json', '')), \
             patch.object(window, 'write_project', side_effect=OSError('disk full')), \
             patch('main.QMessageBox.critical') as message:
            window.save_project()
            message.assert_called_once()
            self.assertEqual(window.project_path, '')
        window.close()

    def test_snapshot_denial_keeps_the_successfully_saved_project(self):
        from akis import project_service
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'chosen.akis.json'
            window = MainWindow()
            window.state.source = 'video.mp4'
            window.state.duration = 2
            window.multitrack = Timeline(tracks=[Track('video', 'Video', [Clip('video.mp4', 0, 60)])])
            window.multitrack_view.set_model(window.multitrack)
            real_save = project_service.save

            def deny_snapshot(path, document, **options):
                if Path(path).parent.name == f'{target.name}.versions':
                    raise PermissionError(13, 'Access denied')
                return real_save(path, document, **options)

            with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(target), '')) as chooser, \
                 patch('akis.project_service.save', side_effect=deny_snapshot), \
                 patch('main.QMessageBox.critical') as critical:
                window.save_project()
                chooser.assert_called_once()
                critical.assert_not_called()
            self.assertEqual(window.project_path, str(target))
            self.assertFalse(window.has_unsaved_changes())
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['state']['source'], 'video.mp4')
            self.assertIn('anlık görüntüsü oluşturulamadı', window.status_label.text())
            window.close()

    def test_save_uses_existing_path_and_refused_normalized_save_as_preserves_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = MainWindow()
            window.state.source = 'video.mp4'
            window.state.duration = 2
            window.multitrack = Timeline(tracks=[Track('video', 'Video', [Clip('video.mp4', 0, 60)])])
            window.multitrack_view.set_model(window.multitrack)
            target = Path(tmp) / 'first.akis.json'
            with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(target), '')) as chooser:
                window.save_project()
            chooser.assert_called_once()
            self.assertEqual(window.project_path, str(target))

            window.publish_title.setText('Saved again')
            with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName') as chooser:
                window.save_project()
            chooser.assert_not_called()
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['publish']['title'], 'Saved again')

            protected = Path(tmp) / 'protected.akis.json'
            protected.write_bytes(b'keep this file')
            with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(Path(tmp) / 'protected.json'), '')), \
                 patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as question:
                window.project_path = ''  # another Save As flow, with the normalized target already present
                window.save_project()
            question.assert_called_once()
            self.assertEqual(protected.read_bytes(), b'keep this file')
            self.assertEqual(window.project_path, '')
            window.close()

    def test_access_denied_reports_selected_location_and_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'existing.akis.json'
            target.write_bytes(b'previous project')
            window = MainWindow()
            window.project_path = str(target)
            window.state.source = 'video.mp4'
            window.state.duration = 2
            with patch.object(window, 'write_project', side_effect=PermissionError(13, 'Access denied')), \
                 patch('main.QMessageBox.critical') as critical:
                window.save_project()
            critical.assert_called_once()
            message = critical.call_args.args[2]
            self.assertIn(str(target), message)
            self.assertIn('Defender', message)
            self.assertIn('farklı bir konum', message)
            self.assertEqual(window.project_path, str(target))
            self.assertTrue(window.has_unsaved_changes())
            self.assertEqual(target.read_bytes(), b'previous project')
            window.close()

    def test_save_as_failure_keeps_current_project_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / 'current.akis.json'
            chosen = Path(tmp) / 'new.akis.json'
            current.write_bytes(b'current project')
            window = MainWindow()
            window.project_path = str(current)
            window.state.source = 'video.mp4'
            window.state.duration = 2
            with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(chosen), '')) as chooser, \
                 patch.object(window, 'write_project', side_effect=PermissionError(13, 'Access denied')), \
                 patch('main.QMessageBox.critical') as critical:
                window.save_project_as()
            chooser.assert_called_once()
            critical.assert_called_once()
            self.assertEqual(window.project_path, str(current))
            self.assertEqual(current.read_bytes(), b'current project')
            self.assertFalse(chosen.exists())
            window.close()

    def test_save_as_is_discoverable_and_has_a_window_shortcut(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        window = MainWindow()
        self.assertEqual(window.save_as_button.text(), 'Farklı kaydet')
        self.assertIn('Ctrl+Shift+S', window.save_as_button.toolTip())
        self.assertEqual(window.shortcut_actions['Ctrl+Shift+S'].shortcut().toString(), 'Ctrl+Shift+S')
        window.show()
        app.processEvents()
        with patch.object(window, 'save_project_as') as save_as:
            QTest.keyClick(window, Qt.Key.Key_S,
                           Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            app.processEvents()
        save_as.assert_called_once()
        window.close()

if __name__ == '__main__': unittest.main()
