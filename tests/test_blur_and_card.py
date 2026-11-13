"""The Shorts look: a picture over its own blurred copy, and the counter-and-title card at the top."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from akis import clip_fit
from akis.media_service import MediaService
from akis.shape_art import draw_shape
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

FFMPEG = shutil.which('ffmpeg')


class BlurFilterTests(unittest.TestCase):
    def test_blur_is_a_choice_and_round_trips(self):
        clip = Clip('a.mp4', 0, 10, style={'transition': 'fade'})
        clip_fit.apply(clip, clip_fit.BLUR)
        self.assertEqual(clip.style, {'transition': 'fade', 'fit': 'blur'})
        self.assertEqual(clip_fit.CHOICES[clip_fit.choice_index(clip.style)][1], clip_fit.BLUR)
        clip_fit.apply(clip, clip_fit.FILL, 1.0)
        self.assertEqual(clip_fit.choice_index(clip.style), 3)

    def test_labels_are_unique_per_layer(self):
        first, _ = clip_fit.filters({'fit': 'blur'}, 1080, 1920, 'k1')
        second, _ = clip_fit.filters({'fit': 'blur'}, 1080, 1920, 'k2')
        self.assertIn('[k1b]', first)
        self.assertNotIn('[k1', second)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class BlurRenderTests(unittest.TestCase):
    def test_bars_are_replaced_by_the_blurred_picture_and_the_middle_is_sharp(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'wide.mp4'
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=320x180:r=10:d=1',
                            '-pix_fmt', 'yuv420p', str(source)], check=True)

            def pixels(style, canvas):
                picture = root / 'f.png'
                timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip(str(source), 0, 10, style=style)])])
                TimelineRenderer(MediaService(FFMPEG), canvas).preview(timeline, 2, picture)
                raw = subprocess.run([FFMPEG, '-v', 'error', '-i', str(picture), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                     capture_output=True, check=True).stdout
                width = canvas[0]
                return lambda x, y: raw[(y * width + x) * 3:(y * width + x) * 3 + 3]
            for canvas in ((270, 480), (90, 160)):
                fitted, blurred = pixels({}, canvas), pixels({'fit': 'blur'}, canvas)
                top, middle = (canvas[0] // 2, canvas[1] // 12), (canvas[0] // 2, canvas[1] // 2)
                self.assertLess(max(fitted(*top)), 20, canvas)                 # a black bar
                self.assertGreater(blurred(*top)[0], 150, canvas)              # the red picture, blurred, fills it
                self.assertGreater(blurred(*middle)[0], 200, canvas)


class CardTests(unittest.TestCase):
    def test_card_sits_at_the_top_and_leaves_the_rest_clear(self):
        image = draw_shape({'shape': 'card', 'counter': '4 / 7', 'title': 'Dağ o ayetten beri ağlıyor', 'y': 0.05}, (540, 960))
        self.assertEqual(image.size, (540, 960))
        self.assertGreater(image.getpixel((270, 60))[3], 150)                 # the card
        self.assertEqual(image.getpixel((270, 600))[3], 0)                    # below it: see-through
        bbox = image.getbbox()
        self.assertLess(bbox[3], 960 * 0.25)
        self.assertGreater(bbox[0], 0)
        self.assertLess(bbox[2], 540)

    def test_long_titles_wrap_to_two_lines_at_most(self):
        short = draw_shape({'shape': 'card', 'counter': '1 / 2', 'title': 'Kısa'}, (540, 960)).getbbox()
        long = draw_shape({'shape': 'card', 'counter': '1 / 2', 'title': 'çok ' * 60}, (540, 960)).getbbox()
        self.assertGreater(long[3], short[3])
        self.assertLess(long[3] - long[1], (short[3] - short[1]) * 2.2)

    def test_counter_or_title_alone(self):
        self.assertIsNotNone(draw_shape({'shape': 'card', 'counter': '2 / 3', 'title': ''}, (540, 960)).getbbox())
        self.assertIsNotNone(draw_shape({'shape': 'card', 'counter': '', 'title': 'Başlık'}, (540, 960)).getbbox())


if __name__ == '__main__':
    unittest.main()
