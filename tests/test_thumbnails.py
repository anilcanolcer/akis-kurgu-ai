"""Film strips on the timeline: the layout, a real strip from a video, and drawing it in a clip."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from akis import thumbnail_service
from akis.multitrack_widget import MultitrackWidget
from akis.thumbnail_service import Strip, layout, make_strip
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


class LayoutTests(unittest.TestCase):
    def test_one_frame_a_second_until_the_cap(self):
        self.assertEqual(layout(10), (10, 1.0))
        self.assertEqual(layout(0.4), (1, 1.0))
        self.assertEqual(layout(3600), (120, 30.0))
        for nothing in (0, -1, None, float('nan')):
            self.assertEqual(layout(nothing), (0, 0.0))

    def test_tile_for_a_moment(self):
        strip = Strip(QImage(300, 32, QImage.Format.Format_RGB32), 10, 2.0)
        self.assertEqual(strip.tile_width, 30)
        self.assertEqual([strip.tile_for(s) for s in (0, 1.9, 2.0, 19.9, 500, -3)], [0, 0, 1, 9, 9, 0])

    def test_unreadable_file_has_no_strip(self):
        failed = lambda *a, **k: subprocess.CompletedProcess([], 1, b'', b'')
        self.assertIsNone(make_strip('ffmpeg', 'x.mp4', 5.0, failed))
        self.assertIsNone(make_strip('ffmpeg', 'x.mp4', 0, failed))

        def missing(*a, **k):
            raise OSError('no ffmpeg')
        self.assertIsNone(make_strip('ffmpeg', 'x.mp4', 5.0, missing))


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealStripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.tmp.name) / 'colours.mp4'
        # Red for two seconds, then blue for two: the strip must show both in that order.
        graph = 'color=c=red:s=160x90:r=10:d=2[a];color=c=blue:s=160x90:r=10:d=2[b];[a][b]concat=n=2:v=1:a=0'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-filter_complex', graph, '-pix_fmt', 'yuv420p', str(cls.source)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_strip_has_the_frames_in_order(self):
        strip = make_strip(FFMPEG, self.source, 4.0)
        self.assertEqual((strip.count, strip.step, strip.image.height()), (4, 1.0, thumbnail_service.HEIGHT))
        self.assertGreater(strip.tile_width, 40)
        middle = lambda index: QColor(strip.image.pixel(index * strip.tile_width + strip.tile_width // 2, 16))
        self.assertGreater(middle(0).red(), 180)
        self.assertGreater(middle(3).blue(), 180)

    def test_worker_delivers_the_strip(self):
        worker = thumbnail_service.ThumbnailWorker(FFMPEG, str(self.source))
        got = []
        worker.ready.connect(lambda source, strip: got.append((source, strip)))
        worker.start()
        self.assertTrue(worker.wait(60000))
        app.processEvents()
        self.assertEqual(got[0][0], str(self.source))
        self.assertEqual(got[0][1].count, 4)

    def test_clip_shows_the_frame_of_its_own_source_time(self):
        strip = make_strip(FFMPEG, self.source, 4.0)
        clip = Clip(str(self.source), 0, 20, source_in=20)        # starts two seconds in: blue
        widget = MultitrackWidget(Timeline(fps_num=10, tracks=[Track('video', 'Video', [clip])]))
        widget.resize(400, 210)
        widget.thumbnails[str(self.source)] = strip
        picture = widget.grab().toImage()
        colour = QColor(picture.pixel(QPoint(120, 30 + 10)))
        self.assertGreater(colour.blue(), colour.red())
        widget.close()


class WidgetTests(unittest.TestCase):
    def test_strips_are_requested_for_video_clips_only_once_each(self):
        timeline = Timeline(tracks=[Track('video', 'V', [Clip('a.mp4', 0, 10), Clip('a.mp4', 10, 10)]),
                                    Track('audio', 'A', [Clip('m.mp3', 0, 10)])])
        widget = MultitrackWidget(timeline)
        started = []

        class FakeWorker:
            def __init__(self, executable, source):
                started.append(source)
                self.ready, self.finished = _Signal(), _Signal()

            def start(self):
                pass

        class _Signal:
            def connect(self, slot):
                pass
        thumbnail_service_worker = 'akis.multitrack_widget.ThumbnailWorker'
        from unittest.mock import patch
        with patch(thumbnail_service_worker, FakeWorker), patch('akis.multitrack_widget.WaveformWorker', FakeWorker):
            widget.waveform_executable = 'ffmpeg'
            widget.refresh_thumbnails()
            widget.thumbnail_worker = None
            widget.refresh_thumbnails()
        self.assertEqual(started, ['a.mp4'])
        self.assertNotIn('m.mp3', widget.thumbnails)

    def test_clip_without_a_strip_paints_as_before(self):
        widget = MultitrackWidget(Timeline(tracks=[Track('video', 'V', [Clip('a.mp4', 0, 50)])]))
        widget.resize(400, 210)
        widget.thumbnails['a.mp4'] = None
        self.assertFalse(widget.grab().isNull())
        widget.close()


if __name__ == '__main__':
    unittest.main()
