"""Export progress: ffmpeg's progress lines, the time-left estimate, the free-space check, a real export."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from akis import export_progress
from akis.export_progress import Estimator, parse, space_problem
from akis.media_service import MediaService
from akis.render_worker import TimelineRenderWorker
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')
Usage = namedtuple('Usage', 'total used free')
MB = 1024 * 1024


class ParseTests(unittest.TestCase):
    def test_only_the_output_time_lines_count(self):
        self.assertEqual(parse('out_time_us=2500000\n'), 2.5)
        self.assertEqual(parse(b'out_time_ms=1000000\r\n'), 1.0)      # microseconds despite the name
        for line in ('frame=12', 'out_time=00:00:02.500000', 'progress=continue', 'out_time_us=N/A', '', 'speed=1.2x'):
            self.assertIsNone(parse(line), line)
        self.assertEqual(parse('out_time_us=-33000'), 0.0)


class EstimateTests(unittest.TestCase):
    def test_time_left_follows_the_speed_so_far(self):
        moment = [100.0]
        estimator = Estimator(now=lambda: moment[0])
        self.assertEqual(estimator.update(0.0), (0, None))
        moment[0] = 101.0
        self.assertEqual(estimator.update(0.01), (1, None))           # too early to guess
        moment[0] = 110.0
        percent, remaining = estimator.update(0.25)
        self.assertEqual(percent, 25)
        self.assertAlmostEqual(remaining, 30.0)
        self.assertEqual(estimator.update(1.7)[0], 100)

    def test_status_text(self):
        self.assertEqual(export_progress.text(1, None), 'Dışa aktarılıyor… %1')
        self.assertEqual(export_progress.text(42, 70), 'Dışa aktarılıyor… %42 · yaklaşık 1:10 kaldı')
        self.assertEqual(export_progress.text(99, 2), 'Dışa aktarılıyor… %99 · bitmek üzere')
        self.assertEqual(export_progress.clock(3725), '1:02:05')


class SpaceTests(unittest.TestCase):
    def test_enough_room_is_no_problem(self):
        self.assertEqual(space_problem('C:/x/out.mp4', 100 * MB, lambda folder: Usage(0, 0, 200 * MB)), '')

    def test_tight_or_tiny_room_is_reported_with_both_numbers(self):
        message = space_problem('C:/x/out.mp4', 1000 * MB, lambda folder: Usage(0, 0, 300 * MB))
        self.assertIn('300 MB', message)
        self.assertIn('1.000 MB', message)
        self.assertTrue(space_problem('C:/x/out.mp4', 1 * MB, lambda folder: Usage(0, 0, 10 * MB)))

    def test_unmeasurable_drive_does_not_block(self):
        def broken(folder):
            raise OSError('no such drive')
        self.assertEqual(space_problem('Q:/x/out.mp4', 10 ** 12, broken), '')

    def test_estimate_is_generous(self):
        one_minute = export_progress.estimated_bytes((1080, 1920), 30, 60)
        self.assertTrue(40 * MB < one_minute < 80 * MB, one_minute)
        self.assertEqual(export_progress.estimated_bytes((1080, 1920), 30, 0), 0)


class FakeRunnerTests(unittest.TestCase):
    def test_injected_runner_gets_the_command_unchanged(self):
        seen = []
        runner = lambda command, **options: seen.append(command) or subprocess.CompletedProcess(command, 0, '', '')
        MediaService('ffmpeg', runner).run(['-i', 'a.mp4'], text=True, on_progress=lambda seconds: None)
        self.assertEqual(seen, [['ffmpeg', '-i', 'a.mp4']])


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=320x180:r=30:d=6',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6', '-shortest', str(self.source)], check=True)
        self.timeline = Timeline(fps_num=30, tracks=[Track('video', 'Video', [Clip(str(self.source), 0, 180)])])

    def test_media_service_reports_rising_seconds_and_keeps_the_error_text(self):
        seen = []
        media = MediaService(FFMPEG)
        result = media.run(['-y', '-i', self.source, '-c:v', 'libx264', '-preset', 'ultrafast', self.root / 'o.mp4'],
                           text=True, on_progress=seen.append)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(seen)
        self.assertEqual(seen, sorted(seen))
        self.assertAlmostEqual(seen[-1], 6.0, delta=0.3)
        failed = media.run(['-y', '-i', self.root / 'missing.mp4', self.root / 'x.mp4'], text=True, on_progress=seen.append)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('missing.mp4', failed.stderr)

    def test_export_reports_fractions_up_to_the_end(self):
        seen = []
        output = self.root / 'out.mp4'
        TimelineRenderer(MediaService(FFMPEG), (320, 180), speed=2.0).export(self.timeline, output, on_progress=seen.append)
        self.assertTrue(output.is_file())
        self.assertTrue(all(0 <= value <= 1 for value in seen))
        self.assertGreater(seen[-1], 0.9)                             # measured against the sped-up length

    def test_worker_emits_each_percent_once_and_cancel_still_works(self):
        worker = TimelineRenderWorker(self.timeline, str(self.root / 'w.mp4'), (320, 180), FFMPEG)
        percents, done = [], []
        worker.progress.connect(percents.append)
        worker.completed.connect(done.append)
        worker.start()
        self.assertTrue(worker.wait(60000))
        app.processEvents()
        self.assertEqual(len(done), 1)
        self.assertEqual(percents, sorted(set(percents)))
        self.assertGreater(percents[-1], 90)

        stopped = TimelineRenderWorker(self.timeline, str(self.root / 'c.mp4'), (320, 180), FFMPEG)
        cancelled = []
        stopped.cancelled.connect(lambda: cancelled.append(True))
        # Direct: cancel from the reporting thread at the first percent, before this short render can finish.
        stopped.progress.connect(lambda percent: stopped.cancel(), Qt.ConnectionType.DirectConnection)
        stopped.start()
        self.assertTrue(stopped.wait(60000))
        app.processEvents()
        self.assertEqual(cancelled, [True])
        self.assertFalse((self.root / 'c.mp4').exists())


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))

    def close_window(self):
        # A worker that has finished may not have told the window yet; a window that still
        # counts it refuses to close and keeps its recovery lock (seen on a slow CI runner).
        QApplication.processEvents()
        for _ in range(500):
            if not self.window._workers:
                break
            QApplication.processEvents()
            __import__("time").sleep(0.01)
        self.window._close_confirmed = True
        self.window.close()

    def test_progress_fills_the_bar_and_the_status_line(self):
        w = self.window
        moment = [0.0]
        w._export_estimator = Estimator(now=lambda: moment[0])
        moment[0] = 10.0
        w.on_export_progress(50)
        self.assertEqual((w.progress.maximum(), w.progress.value()), (100, 50))
        self.assertEqual(w.status_label.text(), 'Dışa aktarılıyor… %50 · yaklaşık 0:10 kaldı')

    def start_export(self, free, answer=QMessageBox.StandardButton.No):
        w = self.window
        started = []
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(self.root / 'out.mp4'), '')), \
             patch.object(w, 'export_canvas_size', return_value=(1080, 1920)), \
             patch('akis.export_progress.shutil.disk_usage', return_value=Usage(0, 0, free)), \
             patch('main.QMessageBox.question', return_value=answer) as question, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.export_video()
        return started, question

    def test_full_drive_asks_before_starting(self):
        started, question = self.start_export(free=1 * MB)
        self.assertEqual(started, [])
        self.assertIn('boş yer', question.call_args.args[2])
        self.assertEqual(self.window.status_label.text(), 'Dışa aktarma başlatılmadı.')
        started, _ = self.start_export(free=1 * MB, answer=QMessageBox.StandardButton.Yes)
        self.assertEqual(len(started), 1)

    def test_roomy_drive_starts_without_a_question(self):
        started, question = self.start_export(free=10 ** 12)
        self.assertEqual(len(started), 1)
        question.assert_not_called()


if __name__ == '__main__':
    unittest.main()
