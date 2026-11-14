"""Taking the look of a sample video: shape, framing, loudness, colour, pace, the template and the button."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import clip_fit, i18n, style_sample, user_templates
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


class PureTests(unittest.TestCase):
    def test_nearest_ratio(self):
        self.assertEqual(style_sample.nearest_ratio(1080, 1920), '9:16')
        self.assertEqual(style_sample.nearest_ratio(1920, 1080), '16:9')
        self.assertEqual(style_sample.nearest_ratio(1080, 1350), '4:5')
        self.assertEqual(style_sample.nearest_ratio(720, 720), '1:1')
        self.assertEqual(style_sample.nearest_ratio(2560, 1080), '')      # 21:9: the source's own shape
        self.assertEqual(style_sample.nearest_ratio(0, 10), '')

    def test_colour_shift_moves_toward_the_sample_in_small_steps(self):
        self.assertEqual(style_sample.colour_shift((0.6, 0.3, 0.5), (0.5, 0.2, 0.3)), (10, 15, 25))
        self.assertEqual(style_sample.colour_shift((0.9, 0.2, 0.0), (0.1, 0.2, 0.9)), (20, 0, -25))   # capped
        self.assertEqual(style_sample.colour_shift(None, (0.5, 0.2, 0.3)), (0, 0, 0))

    def test_template_is_valid_and_keeps_its_framing(self):
        found = {'aspect': '9:16', 'framing': 'blur', 'colour': (0.6, 0.2, 0.4), 'own_colour': (0.5, 0.2, 0.4),
                 'lufs': -14.6, 'pace': 1.0, 'size': (1080, 1920)}
        item = user_templates._valid(style_sample.to_template(found, 'Örnek: a'))
        self.assertEqual((item['aspect'], item['framing'], item['audio'], item['color']), ('9:16', 'blur', ['level'], [10, 0, 0]))
        quiet = dict(found, lufs=-24.0)
        self.assertEqual(style_sample.to_template(quiet, 'x')['audio'], [])
        self.assertIn('Kadraj: bulanık arka plan', user_templates.describe(item))
        self.assertNotIn('framing', user_templates._valid(dict(item, framing='zoom')))

    def test_description_in_both_languages(self):
        found = {'aspect': '9:16', 'framing': 'blur', 'colour': (0.6, 0.2, 0.4), 'own_colour': None,
                 'lufs': -14.2, 'pace': 30.0, 'size': (1080, 1920)}
        item = style_sample.to_template(found, 'x')
        text = '\n'.join(style_sample.describe(found, item))
        for part in ('Oran: 9:16 (1080×1920)', 'bulanık arka plan üstünde', '-14,2 LUFS', 'ses eşitleme açılacak',
                     'önce kendi videonuzu ekleyin', 'dakikada 30 kesim (ortalama çekim 2,0 sn)', 'Hızlı bir kurgu'):
            self.assertIn(part, text)
        english = '\n'.join(style_sample.describe(found, item, lambda t: i18n.translate(t, 'en')))
        self.assertIn('on a blurred background', english)
        self.assertIn('30 cuts a minute', english)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class MeasureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.media = MediaService(FFMPEG)
        cls.wide = cls.root / 'wide.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=25:d=12', '-f', 'lavfi',
                        '-i', 'sine=frequency=300:duration=12', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ar', '48000',
                        '-pix_fmt', 'yuv420p', '-shortest', str(cls.wide)], check=True)
        cls.other = cls.root / 'other.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'mandelbrot=s=640x360:r=25', '-t', '12',
                        '-pix_fmt', 'yuv420p', str(cls.other)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def vertical(self, name, fit):
        """A 9:16 video of the wide one, framed `fit`, cutting between two sources every 2 s."""
        clips = []
        for index in range(6):
            clip = Clip(str(self.wide if index % 2 == 0 else self.other), index * 50, 50, source_in=index * 10)
            clip_fit.apply(clip, fit)
            clips.append(clip)
        output = self.root / name
        TimelineRenderer(self.media, (360, 640)).export(Timeline(fps_num=25, tracks=[Track('video', 'V', clips)]), output)
        return output

    def test_framing_shape_loudness_and_pace(self):
        for fit in (clip_fit.BLUR, clip_fit.FIT, clip_fit.FILL):
            found = style_sample.measure(self.media, self.vertical(f'{fit}.mp4', fit))
            self.assertEqual((found['aspect'], found['framing']), ('9:16', fit), fit)
        found = style_sample.measure(self.media, self.root / 'blur.mp4', self.wide)
        self.assertGreater(found['pace'], 15)                  # a cut every 2 s
        self.assertIsNotNone(found['own_colour'])
        wide = style_sample.measure(self.media, self.wide)
        self.assertEqual(wide['aspect'], '16:9')
        self.assertAlmostEqual(wide['lufs'], -14, delta=1.5)
        self.assertLess(wide['pace'], 5)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
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
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        self.sample = self.root / 'ornek.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=360x640:r=25:d=4',
                        '-pix_fmt', 'yuv420p', str(self.sample)], check=True)

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

    def test_sample_style_is_saved_and_applied(self):
        w = self.window
        w.show_timeline(Timeline(fps_num=25, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 100)])]))
        started = []
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(self.sample), '')), \
             patch('PySide6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes) as asked, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.style_from_sample()
            started[0].start()
            self.assertTrue(started[0].wait(60000))
            app.processEvents()
        self.assertIn('Oran: 9:16 (360×640)', asked.call_args.args[2])
        saved = user_templates.load(self.root / 'data')
        self.assertEqual([item['name'] for item in saved], ['Örnek: ornek'])
        self.assertTrue(w.aspect.currentData().startswith('9:16'))
        self.assertEqual(w.multitrack.tracks[0].clips[0].style.get('fit'), saved[0]['framing'])
        self.assertEqual(w.status_label.text(), 'Örnek: ornek stili bu projeye uygulandı.')
        w.undo()
        self.assertNotIn('fit', w.multitrack.tracks[0].clips[0].style)

    def test_cancelled_file_choice_does_nothing(self):
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=('', '')):
            self.window.style_from_sample()
        self.assertIsNone(self.window.worker)


if __name__ == '__main__':
    unittest.main()
