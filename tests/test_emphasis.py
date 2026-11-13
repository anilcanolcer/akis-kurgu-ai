"""Punch-in zoom: finding loud moments, storing them on clips, and the zoom in real renders."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import emphasis
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


def levels(seconds, loud_at=(), base=-30.0, peak=-12.0, window=0.02):
    """A loudness curve at `base` dB with short peaks at the given seconds."""
    curve = [base] * int(seconds / window)
    for second in loud_at:
        for i in range(int(second / window), int((second + 0.3) / window)):
            if i < len(curve):
                curve[i] = peak - abs(i - int(second / window) - 7) * 0.5
    return curve


class FindTests(unittest.TestCase):
    def test_loud_moments_are_found_in_order(self):
        found = emphasis.find_moments(levels(60, (8, 21, 40)))
        self.assertEqual(len(found), 3)
        for got, wanted in zip(found, (8, 21, 40)):
            self.assertAlmostEqual(got, wanted + 0.14, delta=0.1)

    def test_moments_are_kept_apart_and_limited(self):
        found = emphasis.find_moments(levels(30, (5, 6, 7, 12, 13, 20, 25)))
        self.assertTrue(all(b - a >= emphasis.MIN_GAP for a, b in zip(found, found[1:])))
        self.assertLessEqual(len(found), 30 / emphasis.MIN_PER_PUNCH)

    def test_steady_or_short_sound_has_none(self):
        self.assertEqual(emphasis.find_moments(levels(60)), [])
        self.assertEqual(emphasis.find_moments(levels(2, (1,))), [])
        self.assertEqual(emphasis.find_moments(levels(60, (10,), peak=-26)), [])      # a small rise only


class ClipTests(unittest.TestCase):
    def timeline(self):
        return Timeline(fps_num=30, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 150, source_in=0),
                                                                 Clip('a.mp4', 150, 150, source_in=300)]),
                                            Track('video', 'B', [Clip('a.mp4', 0, 60)])])

    def test_punches_go_on_the_clips_that_show_the_moment_in_source_frames(self):
        cut = self.timeline()
        placed = emphasis.apply(cut, {'a.mp4': [2.0, 7.0, 12.0]})       # 7 s is cut out of the edit
        self.assertEqual(placed, 2)
        first, second = cut.tracks[0].clips
        self.assertEqual(first.style['punch'], [[60, 36]])
        self.assertEqual(second.style['punch'], [[360, 36]])
        self.assertNotIn('punch', cut.tracks[1].clips[0].style)          # only the main track

    def test_applying_again_replaces_and_clear_removes(self):
        cut = self.timeline()
        cut.tracks[0].clips[0].style['transition'] = 'fade'
        emphasis.apply(cut, {'a.mp4': [2.0]})
        emphasis.apply(cut, {'a.mp4': [3.0]})
        self.assertEqual(cut.tracks[0].clips[0].style, {'transition': 'fade', 'punch': [[90, 36]]})
        self.assertEqual(emphasis.clear(cut), 1)
        self.assertEqual(cut.tracks[0].clips[0].style, {'transition': 'fade'})

    def test_split_keeps_the_punch_on_the_picture_it_belongs_to(self):
        cut = self.timeline()
        emphasis.apply(cut, {'a.mp4': [2.0]})
        right = cut.tracks[0].split(cut.tracks[0].clips[0].id, 100)
        self.assertEqual(right.style['punch'], [[60, 36]])                 # source frames: still at 2 s
        self.assertEqual(emphasis.zoom_filter(right, 30, 1, 0, 160, 90) != '', True)

    def test_filter_text(self):
        clip = Clip('a.mp4', 0, 150, source_in=30, style={'punch': [[60, 36]]})
        text = emphasis.zoom_filter(clip, 30, 1, 0.5, 160, 90)
        self.assertTrue(text.startswith('fps=30/1,zoompan=z='))
        self.assertIn('(it+1.500000)', text)                               # source_in 1 s + skip 0.5 s
        self.assertIn(':d=1:s=160x90:fps=30/1', text)
        self.assertEqual(emphasis.zoom_filter(Clip('a.mp4', 0, 10), 30, 1, 0, 160, 90), '')
        broken = Clip('a.mp4', 0, 10, style={'punch': [['x', 'y']]})
        self.assertEqual(emphasis.zoom_filter(broken, 30, 1, 0, 160, 90), '')


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'pattern.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=160x90:r=10:d=6', '-pix_fmt', 'yuv420p',
                        str(cls.source)], check=True)
        cls.media = MediaService(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def frame(self, style, at, source_in=0):
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip(str(self.source), 0, 40, source_in=source_in, style=style)])])
        picture = self.root / 'frame.png'
        TimelineRenderer(self.media, (160, 90)).preview(timeline, at, picture)
        return subprocess.run([FFMPEG, '-v', 'error', '-i', str(picture), '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                              capture_output=True, check=True).stdout

    def difference(self, a, b):
        return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

    def test_picture_is_zoomed_during_the_punch_only(self):
        punch = {'punch': [[15, 12]]}                                       # source 1.5 s to 2.7 s
        self.assertGreater(self.difference(self.frame(punch, 21), self.frame({}, 21)), 5)
        self.assertLess(self.difference(self.frame(punch, 35), self.frame({}, 35)), 1)
        self.assertLess(self.difference(self.frame(punch, 5), self.frame({}, 5)), 1)

    def test_punch_follows_the_source_when_the_clip_starts_later(self):
        punch = {'punch': [[25, 12]]}                                       # source 2.5 s; the clip starts at 1 s
        self.assertGreater(self.difference(self.frame(punch, 20, source_in=10), self.frame({}, 20, source_in=10)), 5)

    def test_export_keeps_its_length(self):
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip(str(self.source), 0, 40, style={'punch': [[15, 12]]})])])
        output = self.root / 'out.mp4'
        TimelineRenderer(self.media, (160, 90)).export(timeline, output)
        self.assertAlmostEqual(self.media.duration(output), 4.0, delta=0.15)


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.MediaService.duration', return_value=60.0).start()
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

    def punches(self):
        return sum(len(c.style.get('punch', [])) for t in self.window.multitrack.tracks for c in t.clips)

    def test_add_then_remove_each_in_one_undo_step(self):
        w = self.window
        with patch('main.silence_cut.measure', return_value=levels(60, (8, 21, 40))):
            w.punch_in_on_emphasis()
        self.assertEqual(self.punches(), 3)
        self.assertIn('3 vurgu anında yakınlaştırma eklendi', w.status_label.text())
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            w.punch_in_on_emphasis()
        self.assertEqual(self.punches(), 0)
        self.assertTrue(w.undo())
        self.assertEqual(self.punches(), 3)
        self.assertTrue(w.undo())
        self.assertEqual(self.punches(), 0)

    def test_nothing_loud_says_so(self):
        with patch('main.silence_cut.measure', return_value=levels(60)), \
             patch('main.QMessageBox.information') as told:
            self.window.punch_in_on_emphasis()
        self.assertEqual(told.call_args.args[2], 'Belirgin bir vurgu anı bulunamadı.')
        self.assertFalse(self.window.undo())


if __name__ == '__main__':
    unittest.main()
