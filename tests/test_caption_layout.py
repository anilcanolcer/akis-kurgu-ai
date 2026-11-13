"""Captions follow the picture: where it sits on the canvas, how large they are, how long each one is."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from akis import caption_layout
from akis.caption_layout import font_px, picture_rect, split_caption
from akis.caption_service import caption_track
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

FFMPEG = shutil.which('ffmpeg')
LONG = ('Bugün sizlerle birlikte uzun zamandır üzerinde çalıştığım bu projenin bütün ayrıntılarını, nasıl '
        'başladığımı, hangi zorluklarla karşılaştığımı ve sonunda neler öğrendiğimi tek tek konuşacağız.')


class RectTests(unittest.TestCase):
    def test_fitted_picture_is_centred_with_bars(self):
        self.assertEqual(picture_rect((1080, 1920), (1920, 1080)), (0, 656, 1080, 608))     # landscape on vertical
        self.assertEqual(picture_rect((1920, 1080), (1080, 1920)), (656, 0, 608, 1080))     # vertical on landscape
        self.assertEqual(picture_rect((1920, 1080), (1920, 1080)), (0, 0, 1920, 1080))
        self.assertEqual(picture_rect((1080, 1080), (1920, 1080)), (0, 236, 1080, 608))

    def test_filled_or_unknown_picture_is_the_whole_canvas(self):
        self.assertEqual(picture_rect((1080, 1920), (1920, 1080), fill=True), (0, 0, 1080, 1920))
        for size in (None, (0, 0), ('a', 'b'), (1920,)):
            self.assertEqual(picture_rect((1080, 1920), size), (0, 0, 1080, 1920), size)

    def test_size_follows_the_picture_but_stays_readable(self):
        self.assertEqual(font_px((0, 0, 1920, 1080), (1920, 1080)), 60)
        self.assertEqual(font_px((0, 0, 1080, 1920), (1080, 1920)), 72)
        self.assertEqual(font_px((0, 656, 1080, 608), (1080, 1920)), 45)      # a small band: the readable minimum
        self.assertEqual(font_px((656, 0, 608, 1080), (1920, 1080)), 45)
        self.assertEqual(font_px((0, 0, 160, 90), (160, 90)), 12)


class SplitTests(unittest.TestCase):
    def test_short_text_is_one_caption(self):
        self.assertEqual(split_caption('Merhaba   dünya', 1.0, 2.0), [(1.0, 2.0, 'Merhaba dünya')])
        self.assertEqual(split_caption('x' * 200, 0, 5), [(0, 5, 'x' * 200)])      # one long word cannot be cut

    def test_long_text_becomes_short_captions_that_share_the_time(self):
        pieces = split_caption(LONG, 10.0, 20.0)
        self.assertGreaterEqual(len(pieces), 3)
        self.assertEqual(' '.join(piece for _, _, piece in pieces), LONG)
        self.assertTrue(all(len(piece) <= caption_layout.MAX_CHARS * 1.3 for _, _, piece in pieces), pieces)
        self.assertEqual(pieces[0][0], 10.0)
        self.assertEqual(pieces[-1][1], 20.0)
        for (_, end, _), (start, _, _) in zip(pieces, pieces[1:]):
            self.assertEqual(end, start)
        longest = max(pieces, key=lambda piece: len(piece[2]))
        shortest = min(pieces, key=lambda piece: len(piece[2]))
        self.assertGreaterEqual(longest[1] - longest[0], shortest[1] - shortest[0])

    def test_break_prefers_punctuation(self):
        text = 'Önce videoyu yükleyin ve bekleyin, sonra da istediğiniz şablonu seçip uygulayın lütfen arkadaşlar.'
        first = split_caption(text, 0, 6)[0][2]
        self.assertTrue(first.endswith('bekleyin,'), first)

    def test_caption_track_uses_the_split(self):
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'Video', [Clip('a.mp4', 0, 300)])])
        count = caption_track(timeline, 'a.mp4', [{'start': 0, 'end': 9, 'text': LONG}, {'start': 9, 'end': 10, 'text': 'Kısa.'}])
        clips = timeline.tracks[-1].clips
        self.assertEqual(count, len(clips))
        self.assertGreaterEqual(count, 4)
        self.assertEqual(clips[-1].text, 'Kısa.')
        self.assertEqual((clips[0].start, clips[-2].end), (0, 270))
        self.assertTrue(all(a.end <= b.start for a, b in zip(clips, clips[1:])))


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealRenderTests(unittest.TestCase):
    """Render a caption over a plain red video and find where the white letters landed."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.media = MediaService(FFMPEG)
        cls.sources = {}
        for name, size in (('wide', '320x180'), ('tall', '180x320')):
            path = cls.root / f'{name}.mp4'
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=red:s={size}:r=10:d=1',
                            '-pix_fmt', 'yuv420p', str(path)], check=True)
            cls.sources[name] = str(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def letters(self, canvas, source, text='Merhaba arkadaşlar, bugün size yeni bir şey göstereceğim.', style=None):
        """Bounding box (left, top, right, bottom) of the white pixels in the rendered frame."""
        width, height = canvas
        video = Clip(self.sources[source], 0, 10, style=style or {})
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'Video', [video])])
        caption_track(timeline, self.sources[source], [{'start': 0, 'end': 1, 'text': text}])
        picture = self.root / 'frame.png'
        TimelineRenderer(self.media, canvas).preview(timeline, 2, picture)
        raw = subprocess.run([FFMPEG, '-v', 'error', '-i', str(picture), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             capture_output=True, check=True).stdout
        self.assertEqual(len(raw), width * height * 3)
        xs, ys = [], []
        for y in range(height):
            row = raw[y * width * 3:(y + 1) * width * 3]
            for x in range(width):
                if row[x * 3] > 200 and row[x * 3 + 1] > 200 and row[x * 3 + 2] > 200:
                    xs.append(x)
                    ys.append(y)
        self.assertTrue(xs, 'no caption letters were drawn')
        return min(xs), min(ys), max(xs), max(ys)

    def test_landscape_video_on_a_vertical_canvas_keeps_the_caption_on_the_picture(self):
        left, top, right, bottom = self.letters((270, 480), 'wide')
        x, y, w, h = picture_rect((270, 480), (320, 180))
        self.assertGreaterEqual(top, y)
        self.assertLessEqual(bottom, y + h)                 # not down in the black bar
        self.assertAlmostEqual((left + right) / 2, x + w / 2, delta=4)
        self.assertGreater(top, y + h / 2)                  # in the lower half of the picture

    def test_vertical_video_on_a_landscape_canvas_does_not_spill_into_the_bars(self):
        left, top, right, bottom = self.letters((480, 270), 'tall')
        x, y, w, h = picture_rect((480, 270), (180, 320))
        self.assertGreaterEqual(left, x)
        self.assertLessEqual(right, x + w)
        self.assertAlmostEqual((left + right) / 2, x + w / 2, delta=4)

    def test_filled_clip_uses_the_whole_canvas(self):
        left, top, right, bottom = self.letters((270, 480), 'wide', style={'fit': 'fill', 'focus': 0.5})
        self.assertGreater(top, 480 * 0.6)                  # near the bottom of the canvas, as on a full picture
        self.assertAlmostEqual((left + right) / 2, 135, delta=4)

    def test_caption_stays_inside_the_canvas_whatever_its_length(self):
        for canvas, source in (((270, 480), 'wide'), ((480, 270), 'tall'), ((270, 270), 'wide'), ((480, 270), 'wide')):
            left, top, right, bottom = self.letters(canvas, source, LONG)
            self.assertGreaterEqual(left, 0)
            self.assertGreaterEqual(top, 0)
            self.assertLess(right, canvas[0])
            self.assertLess(bottom, canvas[1])


if __name__ == '__main__':
    unittest.main()
