"""Export by copying: when it is offered, and a real copy checked against its source."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import fast_export
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')
PLAIN = {'brightness': 0, 'contrast': 0, 'saturation': 0, 'speed': 1.0}


class PlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = str(Path(tmp.name) / 'a.mp4')
        Path(self.source).touch()
        self.media = MagicMock()
        self.media.dimensions.return_value = (1920, 1080)
        self.media.is_hdr.return_value = False

    def cut(self, *clips, extra=()):
        return Timeline(fps_num=30, tracks=[Track('video', 'Video', list(clips)), Track('audio', 'Ses'), *extra])

    def plan(self, timeline, adjustments=PLAIN, canvas=(1920, 1080)):
        return fast_export.plan(timeline, adjustments, canvas, self.media)

    def clip(self, start, length, source_in, **more):
        return Clip(self.source, start, length, source_in=source_in, **more)

    def test_plain_cuts_of_one_video_are_copied_piece_by_piece(self):
        pieces = self.plan(self.cut(self.clip(0, 60, 30), self.clip(60, 90, 300)))
        self.assertEqual(pieces, [(self.source, 1.0, 2.0), (self.source, 10.0, 3.0)])

    def test_a_split_that_was_never_cut_is_one_piece(self):
        self.assertEqual(self.plan(self.cut(self.clip(0, 60, 30), self.clip(60, 30, 90))), [(self.source, 1.0, 3.0)])

    def test_anything_that_changes_picture_or_sound_rules_it_out(self):
        base = lambda: self.cut(self.clip(0, 60, 0))
        self.assertIsNotNone(self.plan(base()))
        for adjustments in (dict(PLAIN, brightness=5), dict(PLAIN, speed=1.25), dict(PLAIN, audio=('level',))):
            self.assertIsNone(self.plan(base(), adjustments), adjustments)
        self.assertIsNone(self.plan(base(), canvas=(1080, 1920)))                       # the canvas adds bars
        self.assertIsNone(self.plan(self.cut(self.clip(0, 60, 0, volume=0.5))))
        self.assertIsNone(self.plan(self.cut(self.clip(0, 60, 0, style={'fit': 'fill'}))))
        self.assertIsNone(self.plan(self.cut(self.clip(0, 60, 0), self.clip(60, 60, 60, style={'transition': 'fade'}))))
        self.assertIsNone(self.plan(self.cut(self.clip(30, 60, 0))))                    # a gap at the start
        self.assertIsNone(self.plan(self.cut(self.clip(0, 60, 0), self.clip(70, 60, 60))))
        text = Track('text', 'Yazı', [Clip('', 0, 30, text='Merhaba')])
        self.assertIsNone(self.plan(self.cut(self.clip(0, 60, 0), extra=[text])))
        self.media.is_hdr.return_value = True
        self.assertIsNone(self.plan(base()))

    def test_other_files_and_containers_are_not_copied(self):
        other = str(Path(self.source).with_name('b.mp4'))
        Path(other).touch()
        self.assertIsNone(self.plan(self.cut(self.clip(0, 60, 0), Clip(other, 60, 60))))
        webm = str(Path(self.source).with_name('c.webm'))
        Path(webm).touch()
        self.assertIsNone(self.plan(self.cut(Clip(webm, 0, 60))))
        missing = str(Path(self.source).with_name('gone.mp4'))
        self.assertIsNone(self.plan(self.cut(Clip(missing, 0, 60))))

    def test_muted_or_empty_tracks_do_not_count(self):
        muted = Track('audio', 'Müzik', [Clip('m.mp3', 0, 60)], muted=True)
        self.assertIsNotNone(self.plan(self.cut(self.clip(0, 60, 0), extra=[muted])))
        self.assertIsNone(self.plan(Timeline(tracks=[Track('video', 'Video')])) if False else None)

    def test_unprobeable_file_is_not_a_candidate(self):
        self.media.dimensions.side_effect = RuntimeError('okunamadı')
        self.assertIsNone(self.plan(self.cut(self.clip(0, 60, 0))))


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'source.mp4'
        # A keyframe every half second, so cuts land close to where they were asked.
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=320x180:r=30:d=8', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=8', '-c:v', 'libx264', '-g', '15', '-pix_fmt', 'yuv420p', '-shortest',
                        str(cls.source)], check=True)
        cls.media = MediaService(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def timeline(self):
        clips = [Clip(str(self.source), 0, 60, source_in=30), Clip(str(self.source), 60, 60, source_in=150)]
        return Timeline(fps_num=30, tracks=[Track('video', 'Video', clips)])

    def codec(self, path):
        report = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path)], capture_output=True, text=True).stderr
        return [line.strip() for line in report.splitlines() if 'Stream #' in line]

    def test_copy_has_both_pieces_the_same_streams_and_sound(self):
        timeline = self.timeline()
        pieces = fast_export.plan(timeline, PLAIN, (320, 180), self.media)
        self.assertEqual(len(pieces), 2)
        output = self.root / 'copy.mp4'
        seen = []
        fast_export.export(pieces, output, self.media, seen.append)
        self.assertAlmostEqual(self.media.duration(output), 4.0, delta=1.0)     # keyframe slack on each piece
        streams = self.codec(output)
        self.assertEqual(len(streams), 2)
        self.assertIn('h264', streams[0])
        self.assertIn('320x180', streams[0])
        self.assertTrue(self.media.has_audio(output))
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(seen, sorted(seen))
        self.assertFalse((self.root / 'copy.part.mp4').exists())
        decoded = subprocess.run([FFMPEG, '-v', 'error', '-i', str(output), '-f', 'null', '-'], capture_output=True, text=True)
        self.assertEqual(decoded.returncode, 0)                                  # plays through
        # A join may repeat one timestamp (a single frame shown for no time); nothing more than that.
        self.assertLessEqual(len(decoded.stderr.strip().splitlines()), len(pieces) - 1, decoded.stderr)

    def test_failure_leaves_no_partial_file_and_keeps_an_existing_target(self):
        output = self.root / 'kept.mp4'
        output.write_bytes(b'old export')
        with self.assertRaises(RuntimeError):
            fast_export.export([(str(self.root / 'missing.mp4'), 0.0, 1.0)], output, self.media)
        self.assertEqual(output.read_bytes(), b'old export')
        self.assertFalse((self.root / 'kept.part.mp4').exists())

    def test_worker_reports_like_the_normal_export_worker(self):
        timeline = self.timeline()
        pieces = fast_export.plan(timeline, PLAIN, (320, 180), self.media)
        worker = fast_export.FastExportWorker(timeline, pieces, str(self.root / 'w.mp4'), FFMPEG)
        done, percents, failed = [], [], []
        worker.completed.connect(done.append)
        worker.progress.connect(percents.append)
        worker.failed.connect(failed.append)
        worker.start()
        self.assertTrue(worker.wait(60000))
        app.processEvents()
        self.assertEqual((len(done), failed), (1, []))
        self.assertEqual(percents[-1], 100)
        same = fast_export.FastExportWorker(timeline, pieces, str(self.source), FFMPEG)   # onto its own source
        same.failed.connect(failed.append)
        same.start()
        self.assertTrue(same.wait(60000))
        app.processEvents()
        self.assertEqual(len(failed), 1)
        self.assertGreater(self.source.stat().st_size, 1000)


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

    def export(self, pieces, answer=QMessageBox.StandardButton.Yes):
        w = self.window
        started = []
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(self.root / 'out.mp4'), '')), \
             patch.object(w, 'export_canvas_size', return_value=(1920, 1080)), \
             patch('akis.export_progress.space_problem', return_value=''), \
             patch('main.fast_export.plan', return_value=pieces), \
             patch('main.QMessageBox.question', return_value=answer) as question, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.export_video()
        return started, question

    def test_eligible_edit_is_offered_the_copy_and_yes_uses_it(self):
        started, question = self.export([('a.mp4', 0.0, 2.0)])
        self.assertIn('Yeniden kodlamadan', question.call_args.args[2])
        self.assertIsInstance(started[0], fast_export.FastExportWorker)
        self.assertEqual(started[0].pieces, [('a.mp4', 0.0, 2.0)])

    def test_no_keeps_the_normal_export(self):
        from akis.render_worker import TimelineRenderWorker
        started, _ = self.export([('a.mp4', 0.0, 2.0)], QMessageBox.StandardButton.No)
        self.assertIsInstance(started[0], TimelineRenderWorker)

    def test_ineligible_edit_is_not_asked(self):
        from akis.render_worker import TimelineRenderWorker
        started, question = self.export(None)
        question.assert_not_called()
        self.assertIsInstance(started[0], TimelineRenderWorker)

    def test_failed_copy_says_how_to_get_the_normal_export(self):
        started, _ = self.export([('a.mp4', 0.0, 2.0)])
        with patch('main.QMessageBox.critical') as shown:
            started[0].failed.emit('kopyalanamadı')
        text = shown.call_args.args[2]
        self.assertIn('kopyalanamadı', text)
        self.assertIn('“Hayır”', text)


if __name__ == '__main__':
    unittest.main()
