"""Batch export: one timeline per video, real exports of several files, the dialog and the button."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import batch_export, i18n
from akis.batch_dialog import BatchDialog
from akis.media_service import MediaService

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
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.app_data_dir', return_value=self.root / 'data').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def start(self, existing=(), answer=QMessageBox.StandardButton.Yes):
        w = self.window
        for name in existing:
            (self.root / name).write_bytes(b'old')
        started = []
        selection = (['C:/v/a.mp4', 'C:/v/b.mp4'], str(self.root), True, None)
        with patch('main.BatchDialog.exec', new=lambda dialog: 1), \
             patch('main.BatchDialog.selection', return_value=selection), \
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

    def test_report_is_shown_when_done(self):
        with patch('main.QMessageBox.information') as shown:
            self.window.on_batch_exported('2 / 2 video dışa aktarıldı:')
        self.assertIn('2 / 2', shown.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
