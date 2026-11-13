"""Three formats in one go: the file names, a real triple render, and the button's checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import multi_export
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


class TargetTests(unittest.TestCase):
    def test_three_names_next_to_the_chosen_one(self):
        found = multi_export.targets('C:/Videos/tatil.mp4')
        self.assertEqual([Path(path).name for _, _, path in found], ['tatil_dikey.mp4', 'tatil_kare.mp4', 'tatil_yatay.mp4'])
        self.assertEqual([canvas for _, canvas, _ in found], [(1080, 1920), (1080, 1080), (1920, 1080)])
        self.assertEqual({Path(path).parent for _, _, path in found}, {Path('C:/Videos')})

    def test_choosing_an_earlier_result_does_not_pile_up_suffixes(self):
        names = [Path(path).name for _, _, path in multi_export.targets('C:/Videos/tatil_kare.mp4')]
        self.assertEqual(names, ['tatil_dikey.mp4', 'tatil_kare.mp4', 'tatil_yatay.mp4'])


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=320x180:r=10:d=1', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=1', '-pix_fmt', 'yuv420p', '-shortest', str(self.source)], check=True)
        self.timeline = Timeline(fps_num=10, tracks=[Track('video', 'Video', [Clip(str(self.source), 0, 10)])])
        # Small canvases of the three shapes keep the test quick.
        self.outputs = [('Dikey', (90, 160), str(self.root / 'o_dikey.mp4')), ('Kare', (120, 120), str(self.root / 'o_kare.mp4')),
                        ('Yatay', (160, 90), str(self.root / 'o_yatay.mp4'))]

    def test_three_files_of_three_shapes_and_rising_progress(self):
        worker = multi_export.MultiExportWorker(self.timeline, self.outputs, FFMPEG)
        done, percents, failed = [], [], []
        worker.completed.connect(done.append)
        worker.progress.connect(percents.append)
        worker.failed.connect(failed.append)
        worker.start()
        self.assertTrue(worker.wait(120000))
        app.processEvents()
        self.assertEqual(failed, [])
        self.assertEqual(done, ['\n'.join(path for _, _, path in self.outputs)])
        media = MediaService(FFMPEG)
        self.assertEqual([tuple(media.dimensions(path)) for _, _, path in self.outputs], [(90, 160), (120, 120), (160, 90)])
        self.assertTrue(all(media.has_audio(path) for _, _, path in self.outputs))
        self.assertEqual(percents, sorted(set(percents)))
        self.assertGreater(percents[-1], 90)

    def test_failure_is_reported_once_and_cancel_is_not_a_failure(self):
        broken = Timeline(fps_num=10, tracks=[Track('video', 'Video', [Clip(str(self.root / 'gone.mp4'), 0, 10)])])
        worker = multi_export.MultiExportWorker(broken, self.outputs, FFMPEG)
        failed, cancelled = [], []
        worker.failed.connect(failed.append)
        worker.cancelled.connect(lambda: cancelled.append(True))
        worker.start()
        self.assertTrue(worker.wait(60000))
        app.processEvents()
        self.assertEqual((len(failed), cancelled), (1, []))
        stopped = multi_export.MultiExportWorker(self.timeline, self.outputs, FFMPEG)
        stopped.cancelled.connect(lambda: cancelled.append(True))
        stopped.cancel()
        stopped.start()
        self.assertTrue(stopped.wait(60000))
        app.processEvents()
        self.assertEqual(cancelled, [True])
        self.assertFalse(Path(self.outputs[0][2]).exists())


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
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
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def start(self, answer=QMessageBox.StandardButton.Yes):
        w = self.window
        started = []
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(self.root / 'tatil'), '')), \
             patch('akis.export_progress.space_problem', return_value=''), \
             patch('main.QMessageBox.question', return_value=answer) as question, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.export_three_formats()
        return started, question

    def test_button_starts_one_worker_for_the_three_files(self):
        started, question = self.start()
        question.assert_not_called()
        self.assertIsInstance(started[0], multi_export.MultiExportWorker)
        self.assertEqual([Path(path).name for _, _, path in started[0].outputs],
                         ['tatil_dikey.mp4', 'tatil_kare.mp4', 'tatil_yatay.mp4'])

    def test_existing_files_are_named_before_they_are_overwritten(self):
        (self.root / 'tatil_kare.mp4').write_bytes(b'old')
        started, question = self.start(QMessageBox.StandardButton.No)
        self.assertEqual(started, [])
        self.assertIn('tatil_kare.mp4', question.call_args.args[2])
        self.assertNotIn('tatil_dikey.mp4', question.call_args.args[2])
        started, _ = self.start(QMessageBox.StandardButton.Yes)
        self.assertEqual(len(started), 1)

    def test_all_three_paths_are_shown_when_done(self):
        w = self.window
        with patch('main.QMessageBox.information') as shown:
            w.on_exported('a_dikey.mp4\na_kare.mp4\na_yatay.mp4')
        for name in ('a_dikey.mp4', 'a_kare.mp4', 'a_yatay.mp4'):
            self.assertIn(name, shown.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
