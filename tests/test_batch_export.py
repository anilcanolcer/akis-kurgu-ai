"""Batch export: one timeline per video, real exports of several files, the dialog and the button."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import hashlib
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import batch_export, i18n
from akis.batch_dialog import BatchDialog
from akis.media_service import MediaService, RenderCancelled

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')
TEMPLATE = {'name': 'Benim', 'aspect': '', 'tracks': [['video', 'Video'], ['audio', 'Müzik'], ['text', 'Başlık']],
            'title': 'Merhaba', 'color': [0, 0, 0], 'speed': 1.0, 'audio': []}


def talk(path, rate=25):
    """A 5 s video whose sound is tone, 2 s of silence, tone."""
    graph = ('sine=frequency=300:duration=1.5,volume=0.5[a];anullsrc=r=44100:cl=mono,atrim=duration=2[b];'
             'sine=frequency=300:duration=1.5,volume=0.5[c];[a][b][c]concat=n=3:v=0:a=1[s]')
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc=s=160x90:r={rate}:d=5',
                    '-filter_complex', graph, '-map', '0:v', '-map', '[s]', '-pix_fmt', 'yuv420p', '-shortest', str(path)],
                   check=True)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'konusma.mp4'
        talk(cls.video)
        cls.media = MediaService(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_plain_timeline_at_the_videos_own_rate(self):
        timeline = batch_export.build(str(self.video), self.media)
        self.assertEqual((timeline.fps_num, timeline.fps_den), (25, 1))
        main = next(t for t in timeline.tracks if t.kind == 'video')
        self.assertAlmostEqual(sum(c.length for c in main.clips), 125, delta=2)

    def test_silences_cut_and_template_added(self):
        timeline = batch_export.build(str(self.video), self.media, cut_silences=True, template=TEMPLATE)
        main = next(t for t in timeline.tracks if t.kind == 'video')
        self.assertEqual(len(main.clips), 2)
        self.assertLess(sum(c.length for c in main.clips), 125 - 25)          # more than a second shorter
        self.assertIn(('text', 'Başlık'), [(t.kind, t.name) for t in timeline.tracks])
        self.assertIn('Merhaba', [c.text for t in timeline.tracks for c in t.clips])

    def test_worker_exports_each_and_reports_failures_without_stopping(self):
        second = self.root / 'ikinci.mp4'
        talk(second, rate=30)
        out = self.root / 'cikti'
        out.mkdir()
        worker = batch_export.BatchExportWorker([str(self.video), str(self.root / 'yok.mp4'), str(second)], str(out), FFMPEG,
                                                aspect='Kaynak oranı', profile='Reels · 1080×1920', cut_silences=True)
        reports, percents = [], []
        worker.completed.connect(reports.append)
        worker.progress.connect(percents.append)
        worker.start()
        self.assertTrue(worker.wait(180000))
        app.processEvents()
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['ikinci_akis.mp4', 'konusma_akis.mp4'])
        self.assertTrue(reports[0].startswith('2 / 3 video dışa aktarıldı:'))
        self.assertIn('✓ konusma_akis.mp4', reports[0])
        self.assertIn('✕ yok.mp4', reports[0])
        self.assertLess(self.media.duration(out / 'konusma_akis.mp4'), 4.2)   # the pause was cut
        self.assertEqual(tuple(self.media.dimensions(out / 'konusma_akis.mp4')), (160, 90))
        self.assertEqual(percents, sorted(percents))
        self.assertEqual(percents[-1], 100)

    def test_write_failure_preserves_old_output_and_reports_its_path(self):
        out = self.root / 'denied'
        out.mkdir()
        worker = batch_export.BatchExportWorker([str(self.video)], str(out), FFMPEG,
                                                aspect='Kaynak oranı', profile='Reels · 1080×1920')
        target = Path(worker.outputs[0])
        target.write_bytes(b'previous batch export')
        original = worker.media.run
        def denied(args, text=False, timeout=None, on_progress=None):
            arguments = list(map(str, args))
            if '-/filter_complex' in arguments:
                Path(arguments[-1]).write_bytes(b'partial render')
                return subprocess.CompletedProcess(arguments, 1, '', 'Permission denied')
            return original(args, text=text, timeout=timeout, on_progress=on_progress)
        worker.media.run = denied
        reports = []
        worker.completed.connect(reports.append)
        worker.start()
        self.assertTrue(worker.wait(60000))
        app.processEvents()
        self.assertEqual(target.read_bytes(), b'previous batch export')
        self.assertEqual(list(out.glob(f'{target.stem}.part-*.mp4')), [])
        self.assertEqual(len(reports), 1)
        self.assertIn(str(target), reports[0])
        self.assertIn('Permission denied', reports[0])
        self.assertIn('Denetimli klasör erişimi', reports[0])

    def test_cancel_preserves_old_output_and_removes_only_its_partial(self):
        out = self.root / 'cancelled'
        out.mkdir()
        worker = batch_export.BatchExportWorker([str(self.video)], str(out), FFMPEG,
                                                aspect='Kaynak oranı', profile='Reels · 1080×1920')
        target = Path(worker.outputs[0])
        target.write_bytes(b'previous batch export')
        original = worker.media.run
        def slow(args, text=False, timeout=None, on_progress=None):
            arguments = list(map(str, args))
            if '-/filter_complex' in arguments:
                arguments.insert(0, '-re')
            return original(arguments, text=text, timeout=timeout, on_progress=on_progress)
        worker.media.run = slow
        cancelled = []
        worker.cancelled.connect(lambda: cancelled.append(True))
        worker.start()
        deadline = __import__('time').monotonic() + 10
        while not list(out.glob(f'{target.stem}.part-*.mp4')) and __import__('time').monotonic() < deadline:
            __import__('time').sleep(0.01)
        worker.cancel()
        self.assertTrue(worker.wait(60000))
        app.processEvents()
        self.assertEqual(cancelled, [True])
        self.assertEqual(target.read_bytes(), b'previous batch export')
        self.assertEqual(list(out.glob(f'{target.stem}.part-*.mp4')), [])

    def test_cancel_before_start_reports_cancelled(self):
        worker = batch_export.BatchExportWorker([str(self.video)], str(self.root), FFMPEG, aspect='Kaynak oranı',
                                                profile='Reels · 1080×1920')
        cancelled = []
        worker.cancelled.connect(lambda: cancelled.append(True))
        worker.cancel()
        worker.start()
        self.assertTrue(worker.wait(60000))
        app.processEvents()
        self.assertEqual(cancelled, [True])

    def test_cancel_stops_a_running_silence_measurement_before_export(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = batch_export.BatchExportWorker([str(self.video)], folder, FFMPEG,
                                                    aspect='Kaynak oranı', profile='Reels · 1080×1920',
                                                    cut_silences=True)
            target = Path(worker.outputs[0])
            target.write_bytes(b'previous batch export')
            original = worker.media.run

            def realtime(args, **options):
                arguments = list(map(str, args))
                if arguments[-1] == 'pipe:1':
                    arguments.insert(0, '-re')
                return original(arguments, **options)

            worker.media.run = realtime
            cancelled, failed, reports = [], [], []
            worker.cancelled.connect(lambda: cancelled.append(True))
            worker.failed.connect(failed.append)
            worker.completed.connect(reports.append)
            worker.start()
            process = None
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with worker.media._lock:
                        candidate = worker.media._process
                    if candidate is not None and candidate.args[-1] == 'pipe:1':
                        process = candidate
                        break
                    time.sleep(0.01)
                self.assertIsNotNone(process, 'Silence measurement must use the worker-owned cancellable process')
                worker.cancel()
                self.assertTrue(worker.wait(3000))
                self.assertIsNotNone(process.poll())
            finally:
                worker.cancel()
                self.assertTrue(worker.wait(60000))
            app.processEvents()
            self.assertEqual((cancelled, failed, reports), ([True], [], []))
            self.assertEqual(worker.results, [])
            self.assertEqual(target.read_bytes(), b'previous batch export')

    def test_distinct_names_and_all_inputs_survive_in_place_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            other = root / 'other'
            other.mkdir()
            inputs = [root / 'a.mp4', other / 'a.mp4', root / 'a_akis.mp4']
            for path in inputs:
                shutil.copyfile(self.video, path)
            before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs]
            worker = batch_export.BatchExportWorker([str(p) for p in inputs], str(root), FFMPEG,
                                                    aspect='Kaynak oranı', profile='Reels · 1080×1920')
            worker.start()
            self.assertTrue(worker.wait(180000))
            app.processEvents()
            self.assertEqual([hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs], before)
            self.assertEqual(len({output for _, output, _ in worker.results}), 3)
            self.assertTrue(all(output and Path(output).is_file() for _, output, _ in worker.results))


class MeasurementTests(unittest.TestCase):
    def test_measurement_preserves_render_cancelled(self):
        media = MediaService('missing-ffmpeg')
        with patch.object(media, 'duration', return_value=2.0), \
             patch.object(media, 'frame_rate', return_value=(10, 1)), \
             patch.object(media, 'run', side_effect=RenderCancelled('cancelled')):
            with self.assertRaises(RenderCancelled):
                batch_export.build('source.mp4', media, cut_silences=True)

    def test_custom_measurement_keeps_its_two_argument_contract(self):
        media = MediaService('fake-ffmpeg')
        with patch.object(media, 'duration', return_value=2.0), \
             patch.object(media, 'frame_rate', return_value=(10, 1)), \
             patch.object(media, 'run') as run:
            measured = []
            timeline = batch_export.build('source.mp4', media, cut_silences=True,
                                          measure=lambda executable, source: measured.append((executable, source)) or [])
        self.assertEqual(measured, [('fake-ffmpeg', 'source.mp4')])
        self.assertEqual(timeline.tracks[0].clips[0].length, 20)
        run.assert_not_called()


class OutputPlanningTests(unittest.TestCase):
    def test_duplicate_names_are_numbered_and_future_sources_reserved(self):
        with tempfile.TemporaryDirectory() as folder:
            sources = [str(Path(folder) / 'a.mp4'), str(Path(folder) / 'other' / 'a.mp4'),
                       str(Path(folder) / 'a_akis.mp4')]
            names = [Path(p).name for p in batch_export.outputs_for(sources, folder)]
            self.assertEqual(names, ['a_akis_2.mp4', 'a_akis_3.mp4', 'a_akis_akis.mp4'])

    def test_hardlink_to_any_input_is_reserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'a.mp4'
            source.write_bytes(b'source')
            alias = root / 'a_akis.mp4'
            try:
                os.link(source, alias)
            except OSError as exc:
                self.skipTest(str(exc))
            self.assertEqual(Path(batch_export.outputs_for([str(source)], folder)[0]).name, 'a_akis_2.mp4')


class DialogTests(unittest.TestCase):
    def test_start_needs_videos_and_an_existing_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = BatchDialog(templates=[TEMPLATE], folder=folder)
            self.assertFalse(dialog.start_button.isEnabled())
            dialog.add_videos(['C:/v/a.mp4', 'C:/v/b.mp4', 'C:/v/a.mp4'])
            self.assertEqual(dialog.videos(), ['C:/v/a.mp4', 'C:/v/b.mp4'])
            self.assertTrue(dialog.start_button.isEnabled())
            dialog.folder.setText(folder + '/yok')
            self.assertFalse(dialog.start_button.isEnabled())
            dialog.folder.setText(folder)
            dialog.template.setCurrentIndex(1)
            videos, chosen, silences, template = dialog.selection()
            self.assertEqual((videos, chosen, silences, template['name']), (['C:/v/a.mp4', 'C:/v/b.mp4'], folder, True, 'Benim'))
            dialog.template.setCurrentIndex(0)
            self.assertIsNone(dialog.selection()[3])

    def test_english(self):
        dialog = BatchDialog(language='en')
        self.assertEqual(dialog.windowTitle(), 'Batch export')
        self.assertEqual(dialog.template.itemText(0), 'No template')
        self.assertEqual(dialog.start_button.text(), 'Start')


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.app_support.app_data_dir', return_value=self.root / 'data').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        self.addCleanup(self.close_window)

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

    def start(self, existing=(), answer=QMessageBox.StandardButton.Yes):
        w = self.window
        for name in existing:
            (self.root / name).write_bytes(b'old')
        started = []
        selection = (['C:/v/a.mp4', 'C:/v/b.mp4'], str(self.root), True, None)
        with patch('akis.batch_dialog.BatchDialog.exec', new=lambda dialog: 1), \
             patch('akis.batch_dialog.BatchDialog.selection', return_value=selection), \
             patch('main.QMessageBox.question', return_value=answer) as asked, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.export_batch()
        return started, asked

    def test_button_starts_one_worker_with_the_projects_settings(self):
        started, asked = self.start()
        asked.assert_not_called()
        worker = started[0]
        self.assertIsInstance(worker, batch_export.BatchExportWorker)
        self.assertEqual((worker.sources, worker.cut_silences), (['C:/v/a.mp4', 'C:/v/b.mp4'], True))
        self.assertEqual(worker.aspect, self.window.aspect.currentData())

    def test_existing_outputs_are_named_first(self):
        started, asked = self.start(existing=['b_akis.mp4'], answer=QMessageBox.StandardButton.No)
        self.assertEqual(started, [])
        self.assertIn('b_akis.mp4', asked.call_args.args[2])

    def test_overwrite_prompt_uses_the_collision_safe_worker_names(self):
        videos = [str(self.root / 'a.mp4'), str(self.root / 'a_akis.mp4')]
        (self.root / 'a_akis.mp4').write_bytes(b'input')
        (self.root / 'a_akis_2.mp4').write_bytes(b'existing output')
        with patch('akis.batch_dialog.BatchDialog.exec', return_value=1), \
             patch('akis.batch_dialog.BatchDialog.selection', return_value=(videos, str(self.root), False, None)), \
             patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as asked, \
             patch.object(self.window, 'start_worker') as start:
            self.window.export_batch()
        start.assert_not_called()
        self.assertIn('a_akis_2.mp4', asked.call_args.args[2])
        self.assertEqual((self.root / 'a_akis.mp4').read_bytes(), b'input')

    def test_report_is_shown_when_done(self):
        with patch('main.QMessageBox.information') as shown:
            self.window.on_batch_exported('2 / 2 video dışa aktarıldı:')
        self.assertIn('2 / 2', shown.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
