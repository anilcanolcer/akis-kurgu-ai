import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from akis import project_service
from akis.timeline_model import Timeline, Track, Clip
from main import MainWindow, EditState

app = QApplication.instance() or QApplication([])


def write_project_b(tmp, **state):
    """Project B on disk: its own source and a 90-frame clip, plus whatever state the test needs."""
    video = Path(tmp) / 'b.mp4'
    video.touch()
    project = Path(tmp) / 'b.akis.json'
    timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(video), 0, 90)]), Track('audio', 'Audio')])
    document = project_service.make_document(asdict(EditState(source=str(video), **state)), timeline,
                                             {'title': 'B başlık', 'caption': '', 'hashtags': ''}, 'B istek')
    project_service.save(project, document)
    return project, video


class ProjectOpenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch('main.MediaService.duration', return_value=2.0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.preview = patch.object(self.window.preview, 'request').start()
        self.addCleanup(patch.stopall)
        # Project A: saved once, then edited (unsaved), with one AI-undo step.
        self.video_a = Path(self.tmp.name) / 'a.mp4'
        self.video_a.touch()
        self.project_a = Path(self.tmp.name) / 'a.akis.json'
        self.window.load_video(str(self.video_a))
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(self.project_a), '')):
            self.window.save_project()
        self.window._edit_undo.append(self.window.edit_snapshot())
        self.window.undo_edit_button.setEnabled(True)
        self.window.publish_title.setText('A başlık (kaydedilmedi)')
        self.window.brightness.setValue(7)
        self.assertTrue(self.window.has_unsaved_changes())

    def picture(self):
        w = self.window
        return {'path': w.project_path, 'source': w.state.source, 'state': asdict(w.state),
                'timeline': w.multitrack.to_dict(), 'view_model': w.multitrack_view.model,
                'media': list(w.media_bin.paths), 'unsaved': w.has_unsaved_changes(),
                'signature': w._saved_signature, 'pending': w._pending_project, 'undo': list(w._edit_undo),
                'undo_enabled': w.undo_edit_button.isEnabled(), 'title': w.windowTitle(),
                'project_title': w.project_title.text(), 'publish': w.publish_title.text(),
                'aspect': w.aspect.currentText(), 'speed': w.speed.currentText(), 'brightness': w.brightness.value(),
                'media_list': w.media_list.count()}

    def open(self, project):
        with patch('main.QFileDialog.getOpenFileName', return_value=(str(project), '')), \
             patch('main.QMessageBox.critical') as critical, patch('main.QMessageBox.warning') as warning:
            self.window.open_project()
        return critical, warning

    def assert_failed_open_left_a_intact(self, before, critical):
        critical.assert_called_once()
        after = self.picture()
        self.assertEqual(after, before)
        self.assertIs(self.window.multitrack_view.model, self.window.multitrack)
        # Saving now must write A's (edited) content into A's file, not B's.
        self.window.save_project()
        saved = json.loads(self.project_a.read_text(encoding='utf-8'))
        self.assertEqual(saved['state']['source'], str(self.video_a))
        self.assertEqual(saved['publish']['title'], 'A başlık (kaydedilmedi)')
        self.assertEqual(saved['state']['brightness'], 7)
        self.assertEqual([c['source'] for t in saved['timeline']['tracks'] for c in t['clips']], [str(self.video_a)])
        self.assertFalse(self.window.has_unsaved_changes())

    def test_failure_inside_apply_project_state_restores_previous_project(self):
        project_b, _ = write_project_b(self.tmp.name, speed='hızlı')  # breaks f"{speed:.2f}" in apply_project_state
        before = self.picture()
        critical, _ = self.open(project_b)
        self.assert_failed_open_left_a_intact(before, critical)

    def test_failure_inside_seek_timeline_restores_previous_project(self):
        project_b, _ = write_project_b(self.tmp.name, aspect='16:9 · YouTube')
        before = self.picture()
        self.preview.side_effect = RuntimeError('render crashed')
        with patch('sys.excepthook'):  # the same error raised inside Qt slots is only printed by PySide
            critical, _ = self.open(project_b)
        self.preview.side_effect = None
        self.assert_failed_open_left_a_intact(before, critical)

    def test_source_ratio_with_missing_first_clip_opens_with_status(self):
        project_b, video_b = write_project_b(self.tmp.name, aspect='Kaynak oranı')
        with patch('main.MediaService.dimensions', side_effect=ValueError('Video boyutları okunamadı.')), \
             patch.object(self.window, 'set_status', wraps=self.window.set_status) as status:
            critical, _ = self.open(project_b)
        critical.assert_not_called()
        self.assertTrue(any('Önizleme oluşturulamadı' in call.args[0] for call in status.call_args_list))
        self.assertEqual(self.window.project_path, str(project_b))
        self.assertEqual(self.window.state.source, str(video_b))
        self.assertEqual(self.window.aspect.currentText(), 'Kaynak oranı')
        self.assertFalse(self.window.has_unsaved_changes())

    def test_successful_open_switches_target_and_clears_ai_undo(self):
        project_b, video_b = write_project_b(self.tmp.name, aspect='16:9 · YouTube', brightness=3)
        critical, _ = self.open(project_b)
        critical.assert_not_called()
        w = self.window
        self.assertEqual(w.project_path, str(project_b))
        self.assertEqual(w.state.source, str(video_b))
        self.assertEqual(w.state.brightness, 3)
        self.assertEqual(w.aspect.currentText(), '16:9 · YouTube')
        self.assertEqual([c.source for t in w.multitrack.tracks for c in t.clips], [str(video_b)])
        self.assertIs(w.multitrack_view.model, w.multitrack)
        self.assertEqual(w.media_bin.paths, [str(video_b)])
        self.assertEqual(w.publish_title.text(), 'B başlık')
        self.assertFalse(w.has_unsaved_changes())
        self.assertIsNone(w._pending_project)
        self.assertEqual(w._edit_undo, [])
        self.assertFalse(w.undo_edit_button.isEnabled())

    def test_loading_new_main_video_clears_ai_undo(self):
        w = self.window
        w.state.source = ''  # as after closing the video: the next add_video becomes the main video
        other = Path(self.tmp.name) / 'other.mp4'
        other.touch()
        w.add_video(str(other))
        self.assertEqual(w.state.source, str(other))
        self.assertEqual(w._edit_undo, [])
        self.assertFalse(w.undo_edit_button.isEnabled())
        self.assertEqual(w.project_path, '')


if __name__ == '__main__': unittest.main()
