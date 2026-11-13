"""Split into Shorts: the part plan, slicing the timeline, a real run of parts, the dialog and the button."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import i18n, shorts_split
from akis.media_service import MediaService
from akis.shorts_dialog import ShortsDialog
from akis.shorts_split import plan_parts, slice_timeline
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


class PlanTests(unittest.TestCase):
    def check(self, parts, total, limit):
        self.assertEqual(parts[0][0], 0)
        self.assertEqual(parts[-1][1], total)
        self.assertTrue(all(abs(a[1] - b[0]) < 1e-9 for a, b in zip(parts, parts[1:])))     # nothing left out
        self.assertTrue(all(b - a <= limit + 1e-9 for a, b in parts))

    def test_seven_minutes_in_sixty_second_parts(self):
        parts = plan_parts(420, 60)
        self.check(parts, 420, 60)
        self.assertEqual(len(parts), 7)

    def test_no_tiny_last_part(self):
        parts = plan_parts(125, 60)
        self.check(parts, 125, 60)
        self.assertEqual(len(parts), 3)
        self.assertGreater(min(b - a for a, b in parts), 40)

    def test_cuts_land_on_pauses_near_the_plan(self):
        pauses = [58, 61, 118, 175, 230, 282, 335]
        parts = plan_parts(390, 60, pauses)
        self.check(parts, 390, 60)
        self.assertEqual([round(b) for a, b in parts[:-1]], [58, 118, 175, 230, 282, 335])

    def test_far_pauses_are_ignored(self):
        parts = plan_parts(120, 60, [5, 115])
        self.assertEqual(parts, [(0.0, 60.0), (60.0, 120)])

    def test_short_video_is_one_part_and_nothing_is_none(self):
        self.assertEqual(plan_parts(45, 60), [(0.0, 45)])
        self.assertEqual(plan_parts(0, 60), [])

    def test_twenty_minutes_in_three_minute_parts(self):
        parts = plan_parts(1200, 180)
        self.check(parts, 1200, 180)
        self.assertEqual(len(parts), 7)


class SliceTests(unittest.TestCase):
    def timeline(self):
        return Timeline(fps_num=10, tracks=[
            Track('video', 'V', [Clip('a.mp4', 0, 100, source_in=50), Clip('b.mp4', 100, 100, style={'transition': 'fade'})]),
            Track('audio', 'M', [Clip('m.mp3', 0, 200, volume=0.4)]),
            Track('text', 'T', [Clip('', 80, 40, text='Altyazı')])])

    def test_every_track_is_cut_to_the_range_and_moved_to_zero(self):
        part = slice_timeline(self.timeline(), 90, 150)
        video, music, text = part.tracks
        self.assertEqual([(c.source, c.start, c.length, c.source_in) for c in video.clips],
                         [('a.mp4', 0, 10, 140), ('b.mp4', 10, 50, 0)])
        self.assertEqual(video.clips[1].style, {'transition': 'fade'})        # starts inside: keeps its entrance
        self.assertEqual([(c.start, c.length, c.source_in, c.volume) for c in music.clips], [(0, 60, 90, 0.4)])
        self.assertEqual([(c.start, c.length, c.text) for c in text.clips], [(0, 30, 'Altyazı')])

    def test_a_clip_cut_at_its_start_loses_its_entrance(self):
        part = slice_timeline(self.timeline(), 120, 200)
        self.assertEqual(part.tracks[0].clips[0].style, {})

    def test_the_original_is_untouched(self):
        timeline = self.timeline()
        slice_timeline(timeline, 90, 150)
        self.assertEqual(timeline.tracks[0].clips[0].length, 100)

    def test_prepare_fills_the_frame_and_adds_the_label(self):
        part = slice_timeline(self.timeline(), 0, 100)
        shorts_split.prepare(part, 2, 5)
        self.assertEqual(part.tracks[0].clips[0].style, {'fit': 'fill', 'focus': 0.5})
        label = part.tracks[-1]
        self.assertEqual((label.name, label.clips[0].text, label.clips[0].length), (shorts_split.LABEL_TRACK, 'Bölüm 2/5', 30))
        english = shorts_split.prepare(slice_timeline(self.timeline(), 0, 100), 1, 3, say=lambda t: i18n.translate(t, 'en'))
        self.assertEqual(english.tracks[-1].clips[0].text, 'Part 1/3')
        alone = shorts_split.prepare(slice_timeline(self.timeline(), 0, 100), 1, 1, fill=False)
        self.assertEqual([t.name for t in alone.tracks], ['V', 'M', 'T'])        # one part needs no number
        self.assertNotIn('fit', alone.tracks[0].clips[0].style)

    def test_output_names_are_numbered_in_order(self):
        self.assertEqual(Path(shorts_split.output_for('C:/v/vlog.mp4', 3, 7)).name, 'vlog_short_03.mp4')
        self.assertEqual(Path(shorts_split.output_for('C:/v/vlog', 12, 120)).name, 'vlog_short_012.mp4')

    def test_pauses_are_mapped_to_the_timeline(self):
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 100, source_in=50),
                                                                     Clip('a.mp4', 100, 100, source_in=300)])])
        window = 0.02
        levels = [-10.0] * int(40 / window)
        for second in (7, 32):                         # silences in the source at 7 s and 32 s
            for i in range(int(second / window), int((second + 1) / window)):
                levels[i] = -90.0
        reads = []
        found = shorts_split.timeline_pauses(timeline, lambda source: reads.append(source) or levels)
        self.assertEqual(reads, ['a.mp4'])
        self.assertEqual([round(p, 1) for p in found], [2.5, 12.5])


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealRunTests(unittest.TestCase):
    def test_a_long_landscape_video_becomes_numbered_vertical_parts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'vlog.mp4'
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=320x180:r=10:d=50', '-f', 'lavfi',
                            '-i', 'sine=frequency=300:duration=50', '-pix_fmt', 'yuv420p', '-shortest', str(source)], check=True)
            timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip(str(source), 0, 500)])])
            parts = plan_parts(50, 20)
            worker = shorts_split.ShortsExportWorker(timeline, parts, str(root / 'vlog_out.mp4'), FFMPEG, canvas=(90, 160))
            done, failed = [], []
            worker.completed.connect(done.append)
            worker.failed.connect(failed.append)
            worker.start()
            self.assertTrue(worker.wait(180000))
            app.processEvents()
            self.assertEqual(failed, [])
            outputs = done[0].split('\n')
            self.assertEqual([Path(p).name for p in outputs], ['vlog_out_short_01.mp4', 'vlog_out_short_02.mp4', 'vlog_out_short_03.mp4'])
            media = MediaService(FFMPEG)
            lengths = [media.duration(p) for p in outputs]
            self.assertAlmostEqual(sum(lengths), 50, delta=0.6)                     # nothing left out
            self.assertTrue(all(abs(length - 50 / 3) < 0.4 for length in lengths), lengths)
            self.assertTrue(all(tuple(media.dimensions(p)) == (90, 160) for p in outputs))
            self.assertTrue(all(media.has_audio(p) for p in outputs))


class DialogTests(unittest.TestCase):
    def test_count_and_lengths_follow_the_limit(self):
        dialog = ShortsDialog(total=420, pauses=[])
        self.assertIn('7:00 sürelik video 7 parçaya bölünecek: 1:00, 1:00', dialog.summary.text())
        dialog.limit.setValue(180)
        self.assertIn('3 parçaya', dialog.summary.text())
        parts, fill, label = dialog.selection()
        self.assertEqual((len(parts), fill, label), (3, True, True))

    def test_english(self):
        dialog = ShortsDialog(total=125, language='en')
        self.assertEqual(dialog.windowTitle(), 'Split into Shorts')
        self.assertIn('will be split into 3 parts', dialog.summary.text())


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.MediaService.duration', return_value=130.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'vlog.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_button_starts_one_worker_for_all_parts(self):
        w = self.window
        started = []
        with patch('main.silence_cut.measure', return_value=[]), \
             patch('main.ShortsDialog.exec', new=lambda dialog: 1), \
             patch('main.QFileDialog.getSaveFileName', return_value=(str(self.root / 'vlog.mp4'), '')), \
             patch('akis.export_progress.space_problem', return_value=''), \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.export_shorts()
        worker = started[0]
        self.assertIsInstance(worker, shorts_split.ShortsExportWorker)
        self.assertEqual(len(worker.parts), 3)
        self.assertEqual(Path(worker.outputs[-1]).name, 'vlog_short_03.mp4')
        self.assertEqual(worker.canvas, shorts_split.CANVAS)


if __name__ == '__main__':
    unittest.main()
