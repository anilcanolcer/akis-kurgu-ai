"""App-wide undo/redo, ripple delete across tracks, cancelling work, closing during work, startup cleanup."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QEvent, QPointF, Qt, QThread, Signal
from PySide6.QtGui import QImage, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

import main
from akis import i18n
from akis.ai_workers import TranscriptWorker
from akis.timeline_model import Clip, Timeline, Track
from main import MainWindow

app = QApplication.instance() or QApplication([])
YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


def wait_until(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    app.processEvents()
    return condition()


class WindowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def load(self):
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))
        return video

    def clips(self, kind='video'):
        return [(c.start, c.length) for t in self.window.multitrack.tracks if t.kind == kind for c in t.clips]

    def select_first_video_clip(self):
        w = self.window
        index = next(i for i, t in enumerate(w.multitrack.tracks) if t.kind == 'video')
        clip = w.multitrack.tracks[index].clips[0]
        w.multitrack_view.selected, w.multitrack_view.selected_track = (index, clip.id), index
        return index, clip


class UndoRedoTests(WindowCase):
    def split_at(self, frame):
        self.select_first_video_clip()
        self.window.multitrack_view.playhead = frame
        self.window.split_clip()

    def test_split_undo_redo(self):
        self.load()
        w = self.window
        self.assertFalse(w.undo_action.isEnabled())
        self.split_at(20)
        self.assertEqual(self.clips(), [(0, 20), (20, 40)])
        self.assertTrue(w.undo_action.isEnabled() and w.undo_button.isEnabled() and w.undo_edit_button.isEnabled())
        self.assertFalse(w.redo_action.isEnabled())
        self.assertTrue(w.undo())
        self.assertEqual(self.clips(), [(0, 60)])
        self.assertIs(w.multitrack_view.model, w.multitrack)
        self.assertTrue(w.redo_action.isEnabled() and w.redo_button.isEnabled())
        self.assertTrue(w.redo())
        self.assertEqual(self.clips(), [(0, 20), (20, 40)])
        self.assertFalse(w.redo())  # nothing left to redo

    def test_new_step_clears_redo_and_noop_is_not_recorded(self):
        self.load()
        w = self.window
        self.split_at(20)
        w.undo()
        with w.history_step():
            pass  # nothing changed
        self.assertEqual(len(w._redo_stack), 1)
        self.assertEqual(w._undo_stack, [])
        self.split_at(30)
        self.assertEqual(w._redo_stack, [])
        self.assertEqual(len(w._undo_stack), 1)

    def test_history_is_capped(self):
        self.load()
        w = self.window
        with patch('main.QInputDialog.getItem', return_value=('text', True)):
            for _ in range(main.UNDO_LIMIT + 7):
                w.add_track()
        self.assertEqual(len(w._undo_stack), main.UNDO_LIMIT)
        tracks = len(w.multitrack.tracks)
        while w.undo():
            pass
        self.assertEqual(len(w.multitrack.tracks), tracks - main.UNDO_LIMIT)

    def test_undoing_a_timeline_step_keeps_later_colour_change(self):
        self.load()
        w = self.window
        self.split_at(20)
        w.brightness.setValue(10)  # not a history step
        w.undo()
        self.assertEqual(self.clips(), [(0, 60)])
        self.assertEqual((w.brightness.value(), w.state.brightness), (10, 10))

    def test_ai_edit_is_one_step_and_later_manual_edits_survive_its_undo_order(self):
        self.load()
        w = self.window
        w.apply_preset(3, 4, 5)
        result = Timeline(tracks=[Track('video', 'Video', [Clip(w.state.source, 0, 30)]), Track('text', 'Text')])
        with patch('main.edit_plan.apply_plan', return_value=result), patch('main.edit_plan.describe', return_value='özet'):
            w.on_prompt_edit({'color': {'brightness': 12}, 'aspect': '16:9', 'speed': 1.25, 'title': 'AI başlık'},
                             [(w.state.source, 2.0)])
        self.assertEqual(len(w._undo_stack), 1)
        with patch('main.QInputDialog.getItem', return_value=('audio', True)):
            w.add_track()  # a manual edit after the AI edit
        self.assertEqual(len(w._undo_stack), 2)
        w.undo()  # only the manual edit
        self.assertEqual(self.clips(), [(0, 30)])
        self.assertEqual(w.brightness.value(), 12)
        self.assertEqual(w.publish_title.text(), 'AI başlık')
        w.undo()  # the AI edit with its settings
        self.assertEqual(self.clips(), [(0, 60)])
        self.assertEqual((w.brightness.value(), w.contrast.value(), w.saturation.value()), (3, 4, 5))
        self.assertEqual(w.aspect.currentData(), i18n.DEFAULT_ASPECT)
        self.assertEqual(w.state.speed, 1.0)
        self.assertEqual(w.publish_title.text(), '')
        w.redo()
        self.assertEqual(self.clips(), [(0, 30)])
        self.assertEqual((w.brightness.value(), w.aspect.currentData(), w.state.speed), (12, '16:9 · YouTube', 1.25))
        # The AI-tab button undoes the last step too.
        w.undo_edit_button.click()
        self.assertEqual(self.clips(), [(0, 60)])

    def test_unsaved_flag_follows_undo_and_redo(self):
        self.load()
        w = self.window
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(self.root / 'p.akis.json'), '')):
            w.save_project()
        self.assertFalse(w.has_unsaved_changes())
        self.split_at(20)
        self.assertTrue(w.has_unsaved_changes())
        w.undo()
        self.assertFalse(w.has_unsaved_changes())
        w.redo()
        self.assertTrue(w.has_unsaved_changes())

    def test_drag_is_one_step_and_click_without_change_is_none(self):
        self.load()
        w = self.window
        view = w.multitrack_view

        def mouse(kind, x, y=50):
            point = QPointF(x, y)
            buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
            return QMouseEvent(kind, point, point, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)

        view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, 150))  # frame 25 of the 0..60 clip: a move
        view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, 150))
        self.assertEqual(w._undo_stack, [])
        view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, 150))
        for x in (160, 170, 180, 190):
            view.mouseMoveEvent(mouse(QEvent.Type.MouseMove, x))
        view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, 190))
        self.assertEqual(self.clips(), [(20, 60)])
        self.assertEqual(len(w._undo_stack), 1)
        w.undo()
        self.assertEqual(self.clips(), [(0, 60)])

    def test_clip_and_track_edits_are_undoable(self):
        self.load()
        w = self.window
        w.multitrack.tracks[2].add(Clip('', 0, 10, text='merhaba'))
        text_clip = w.multitrack.tracks[2].clips[0]
        with patch('main.QInputDialog.getMultiLineText', return_value=('güle güle', True)):
            w.edit_clip(2, text_clip.id)
        self.assertEqual(w.multitrack.tracks[2].clips[0].text, 'güle güle')
        index, clip = self.select_first_video_clip()
        with patch('main.QInputDialog.getInt', return_value=(40, True)):
            w.set_clip_volume()
        self.assertEqual(w.multitrack.tracks[index].clips[0].volume, 0.4)
        w.multitrack_view.selected_track = 0
        with patch('main.QMessageBox.question', return_value=YES) as ask:
            w.remove_track()
        self.assertNotIn('geri alınamaz', ask.call_args.args[2])
        self.assertNotIn('video', [t.kind for t in w.multitrack.tracks])
        w.undo()
        self.assertEqual(self.clips(), [(0, 60)])
        w.undo()
        self.assertEqual(w.multitrack.tracks[index].clips[0].volume, 1.0)
        w.undo()
        self.assertEqual(w.multitrack.tracks[2].clips[0].text, 'merhaba')

    def test_shortcuts(self):
        self.load()
        w = self.window
        self.assertEqual(w.undo_action.shortcut(), QKeySequence('Ctrl+Z'))
        self.assertEqual(set(w.redo_action.shortcuts()), {QKeySequence('Ctrl+Y'), QKeySequence('Ctrl+Shift+Z')})
        self.split_at(20)
        w.undo_action.trigger()
        self.assertEqual(self.clips(), [(0, 60)])
        w.redo_action.trigger()
        self.assertEqual(self.clips(), [(0, 20), (20, 40)])

    def test_history_cleared_on_new_video_and_restored_by_failed_open(self):
        self.load()
        w = self.window
        self.split_at(20)
        self.split_at(10)
        w.undo()
        undo, redo = list(w._undo_stack), list(w._redo_stack)
        snapshot = w.open_snapshot()
        other = self.root / 'b.mp4'
        other.touch()
        w.load_video(str(other))
        self.assertEqual((w._undo_stack, w._redo_stack), ([], []))
        self.assertFalse(w.undo_action.isEnabled() or w.redo_action.isEnabled())
        w.restore_open_snapshot(snapshot)
        self.assertEqual((w._undo_stack, w._redo_stack), (undo, redo))
        self.assertTrue(w.undo_action.isEnabled() and w.redo_action.isEnabled())


class RippleDeleteTests(WindowCase):
    def test_ripple_delete_shifts_other_tracks_and_markers_and_undoes(self):
        self.load()
        w = self.window
        index, first = self.select_first_video_clip()
        w.multitrack.tracks[index].clips[0].length = 30
        w.multitrack.tracks[index].add(Clip(w.state.source, 30, 30))
        w.multitrack.tracks[2].add(Clip('', 40, 10, text='altyazı'))
        w.multitrack.markers.append({'frame': 45, 'label': 'm'})
        w.ripple_delete()
        self.assertEqual(self.clips(), [(0, 30)])
        self.assertEqual(self.clips('text'), [(10, 10)])
        self.assertEqual(w.multitrack.markers[0]['frame'], 15)
        self.assertIsNone(w.multitrack_view.selected)
        self.assertEqual(len(w._undo_stack), 1)
        w.undo()
        self.assertEqual(self.clips(), [(0, 30), (30, 30)])
        self.assertEqual(self.clips('text'), [(40, 10)])
        self.assertEqual(w.multitrack.markers[0]['frame'], 45)

    def test_ripple_delete_error_is_reported_without_a_step(self):
        self.load()
        w = self.window
        self.select_first_video_clip()
        with patch.object(Timeline, 'ripple_delete', side_effect=ValueError('Clips on the same track overlap')):
            w.ripple_delete()
        self.assertIn('Klip silinemedi', w.status_label.text())
        self.assertEqual(w._undo_stack, [])
        self.assertEqual(self.clips(), [(0, 60)])


class FakeRender(QThread):
    """Stands in for TimelineRenderWorker: runs until cancel(), then emits cancelled."""
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.stop = threading.Event()

    def cancel(self):
        self.stop.set()

    def run(self):
        if self.stop.wait(5):
            self.cancelled.emit()
        else:
            self.completed.emit('out.mp4')


class Uncancellable(QThread):
    failed = Signal(str)

    def run(self):
        self.msleep(150)


class CancelTests(WindowCase):
    def test_export_cancel_button(self):
        self.load()
        w = self.window
        self.assertTrue(w.cancel_button.isHidden())
        with patch('main.TimelineRenderWorker', FakeRender), \
             patch.object(w, 'export_canvas_size', return_value=(1080, 1920)), \
             patch('main.QFileDialog.getSaveFileName', return_value=(str(self.root / 'out.mp4'), '')):
            w.export_video()
        worker = w.worker
        self.assertIsInstance(worker, FakeRender)
        self.assertFalse(w.cancel_button.isHidden())
        self.assertTrue(w.cancel_button.isEnabled())
        w.cancel_button.click()
        self.assertFalse(w.cancel_button.isEnabled())
        self.assertTrue(wait_until(lambda: not w._workers))
        self.assertEqual(w.status_label.text(), 'Dışa aktarma iptal edildi.')
        self.assertTrue(w.progress.isHidden())
        self.assertTrue(w.cancel_button.isHidden())

    def test_uncancellable_worker_leaves_button_disabled(self):
        w = self.window
        w.worker = Uncancellable()
        w.start_worker()
        self.assertFalse(w.cancel_button.isHidden())
        self.assertFalse(w.cancel_button.isEnabled())
        w.cancel_work()  # nothing to cancel: no error
        self.assertTrue(wait_until(lambda: not w._workers))
        self.assertTrue(w.cancel_button.isHidden())

    def test_transcript_worker_cancel_discards_result(self):
        audio_ready = threading.Event()
        release = threading.Event()

        def fake_extract(video, destination):
            Path(destination).write_bytes(b'x')
            audio_ready.set()
            return type('R', (), {'returncode': 0})()

        def fake_transcribe(*args):
            release.wait(5)
            return 'metin'

        worker = TranscriptWorker('k', 'v.mp4', 'ffmpeg')
        worker.media.extract_audio = fake_extract
        seen = []
        worker.completed.connect(lambda text: seen.append('completed'))
        worker.failed.connect(lambda message: seen.append('failed'))
        worker.cancelled.connect(lambda: seen.append('cancelled'))
        with patch('akis.ai_workers.transcribe', fake_transcribe):
            worker.start()
            self.assertTrue(audio_ready.wait(5))
            worker.cancel()
            release.set()
            self.assertTrue(worker.wait(5000))
        app.processEvents()
        self.assertEqual(seen, ['cancelled'])

    def test_cancelled_before_ffmpeg_runs_never_starts_it(self):
        worker = TranscriptWorker('k', 'v.mp4', 'ffmpeg-that-does-not-exist')
        seen = []
        worker.cancelled.connect(lambda: seen.append('cancelled'))
        worker.failed.connect(lambda message: seen.append(message))
        worker.cancel()
        worker.run()  # MediaService refuses to start a process once cancelled
        self.assertEqual(seen, ['cancelled'])


class CloseDuringWorkTests(WindowCase):
    def start_render(self):
        w = self.window
        w.show()
        w.worker = FakeRender()
        w.worker.failed.connect(w.on_worker_error)
        w.worker.cancelled.connect(w.on_export_cancelled)
        w.start_worker()
        return w.worker

    def test_no_keeps_window_and_work(self):
        worker = self.start_render()
        with patch('main.QMessageBox.question', return_value=NO) as ask:
            self.assertFalse(self.window.close())
        self.assertEqual(ask.call_args.args[2], main.CANCEL_ON_CLOSE_QUESTION)
        self.assertTrue(worker.isRunning())
        self.assertFalse(self.window._shutting_down)
        worker.cancel()
        self.assertTrue(wait_until(lambda: not self.window._workers))

    def test_yes_cancels_waits_and_ignores_late_signals(self):
        worker = self.start_render()
        with patch('main.QMessageBox.question', return_value=YES), \
             patch('main.QMessageBox.critical') as critical, patch('main.QMessageBox.information') as info:
            self.assertTrue(self.window.close())
            self.assertTrue(self.window._shutting_down)
            self.assertTrue(worker.isFinished())  # cancelled and waited for, not left running
            status = self.window.status_label.text()
            app.processEvents()  # the queued `cancelled` arrives after shutdown began
            self.window.on_worker_error('geç gelen hata')
            self.window.on_exported('out.mp4')
            critical.assert_not_called()
            info.assert_not_called()
        self.assertEqual(self.window.status_label.text(), status)

    def test_hidden_window_still_refuses_without_asking(self):
        w = self.window
        w.worker = FakeRender()
        w.start_worker()
        with patch('main.QMessageBox.question') as ask:
            self.assertFalse(w.close())
        ask.assert_not_called()
        w.worker.cancel()
        self.assertTrue(wait_until(lambda: not w._workers))


class StartupTests(unittest.TestCase):
    def test_temp_cleanup_runs_off_the_gui_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / 'akis_render_old'
            stale.mkdir()
            os.utime(stale, (time.time() - 3 * 86400,) * 2)
            fresh = Path(tmp) / 'akis_render_new'
            fresh.mkdir()
            thread = main.start_temp_cleanup(tmp)
            self.assertTrue(thread.daemon)
            thread.join(5)
            self.assertFalse(stale.exists())
            self.assertTrue(fresh.exists())

    def test_main_starts_cleanup_before_the_window(self):
        order = []
        with patch('main.start_temp_cleanup', side_effect=lambda: order.append('cleanup')), \
             patch('main.QApplication') as application, patch('main.MainWindow', side_effect=lambda: order.append('window') or MagicMock()), \
             patch('main.setup_logging', return_value=None), patch('main.wait_for_background_threads'):
            application.return_value.platformName.return_value = 'offscreen'
            application.return_value.exec.return_value = 0
            with patch('sys.excepthook'):
                main.main()
        self.assertEqual(order[:2], ['cleanup', 'window'])


class PreviewImageTests(WindowCase):
    def test_preview_still_is_loaded_as_qimage(self):
        path = self.root / 'frame.png'
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(0xff0000)
        self.assertTrue(image.save(str(path)))
        self.window.show_timeline_frame(str(path))
        self.assertIsInstance(self.window.video.image, QImage)
        self.assertEqual(self.window.video.image.size(), image.size())


if __name__ == '__main__':
    unittest.main()
