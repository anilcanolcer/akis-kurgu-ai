"""Output quality: source frame rate, 4K canvas, still sharpness, caption re-apply, mix limiter, HDR."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from akis import timeline_service
from akis.media_service import MediaService
from akis.preview_controller import PreviewController
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import LIMITER, TONE_MAP, TimelineRenderer

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


def probing(report):
    return MediaService('ffmpeg', Mock(return_value=subprocess.CompletedProcess([], 1, '', report)))


def stream(detail):
    return f'Duration: 00:00:02.00, start: 0\n  Stream #0:0[0x1](und): Video: {detail}\n  Stream #0:1: Audio: aac, 48000 Hz'


class FrameRateTests(unittest.TestCase):
    def test_standard_and_uneven_rates(self):
        cases = {'h264, yuv420p, 1920x1080, 60 fps, 60 tbr': (60, 1),
                 'h264, yuv420p, 1920x1080, 23.98 fps, 23.98 tbr': (24000, 1001),
                 'h264, yuv420p, 1920x1080, 25 fps': (25, 1),
                 'h264, yuv420p, 1920x1080, 29.83 fps, 30 tbr': (30000, 1001),      # phone, slightly uneven
                 'hevc, yuv420p, 1920x1080, 59.94 fps': (60000, 1001),
                 'hevc, yuv420p, 1920x1080, 240 fps': (60, 1),                # slow motion plays at 60
                 'h264, yuv420p, 1920x1080, 15 fps': (15, 1),
                 'mjpeg, yuvj420p, 640x480, 25 tbr': (25, 1)}
        for detail, expected in cases.items():
            self.assertEqual(probing(stream(detail)).frame_rate('a.mp4'), expected, detail)

    def test_unknown_rate(self):
        self.assertIsNone(probing('Invalid data').frame_rate('a.mp4'))

    def test_new_timeline_adopts_the_rate(self):
        timeline = Timeline.from_legacy({'source': 'a.mp4', 'start': 1, 'end': 3}, (60, 1))
        self.assertEqual((timeline.fps_num, timeline.fps_den), (60, 1))
        clip = timeline.tracks[0].clips[0]
        self.assertEqual((clip.source_in, clip.length), (60, 120))
        self.assertEqual(Timeline.from_legacy({}).fps_num, 30)

    def test_loaded_video_sets_the_project_rate(self):
        from main import MainWindow
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'demo.mp4'
            video.touch()
            window = MainWindow()
            with patch('akis.media_service.MediaService.duration', return_value=2.0), \
                    patch('akis.media_service.MediaService.frame_rate', return_value=(50, 1)), patch.object(window, 'seek_timeline'):
                window.load_video(str(video))
            self.assertEqual((window.multitrack.fps_num, window.multitrack.fps_den), (50, 1))
            self.assertEqual(window.multitrack.tracks[0].clips[0].length, 100)
            window._close_confirmed = True
            window.close()


class CanvasTests(unittest.TestCase):
    def canvas(self, size, profile='4K UHD · 3840×2160'):
        media = Mock()
        media.dimensions.return_value = size
        timeline = Timeline(tracks=[Track('video', 'V', [Clip('a.mp4', 0, 30)])])
        return timeline_service.output_canvas_size('Kaynak oranı', timeline, media, profile)

    def test_source_ratio_never_exceeds_4k(self):
        self.assertEqual(self.canvas((3840, 2160)), (3840, 2160))
        self.assertEqual(self.canvas((1920, 1080)), (3840, 2160))
        self.assertEqual(self.canvas((2560, 1440)), (3840, 2160))
        self.assertEqual(self.canvas((1280, 720)), (2560, 1440))
        self.assertEqual(self.canvas((2160, 3840)), (2160, 3840))
        self.assertEqual(self.canvas((3840, 2160), 'YouTube · 1080p'), (3840, 2160))

    def test_fixed_canvases_still_double(self):
        timeline = Timeline()
        self.assertEqual(timeline_service.output_canvas_size('16:9 · YouTube', timeline, Mock(), '4K UHD'), (3840, 2160))
        self.assertEqual(timeline_service.output_canvas_size('9:16 · Reels', timeline, Mock(), 'Reels'), (1080, 1920))


class StillSizeTests(unittest.TestCase):
    def test_limit_decides_the_size(self):
        self.assertEqual(PreviewController.preview_size((1920, 1080)), (480, 270))
        self.assertEqual(PreviewController.preview_size((1920, 1080), 1280), (1280, 720))
        self.assertEqual(PreviewController.preview_size((1080, 1920), 960), (540, 960))
        self.assertEqual(PreviewController.preview_size((640, 360), 1920), (640, 360))  # never enlarged

    def test_controller_renders_at_its_limit(self):
        factory = Mock()
        controller = PreviewController('ffmpeg', worker_factory=factory)
        controller.limit = 960
        controller.request(Timeline(), 0, (1920, 1080), {})
        self.assertEqual(factory.call_args.args[2], (960, 540))
        controller.worker = None
        controller.close()

    def test_window_asks_for_what_the_view_shows(self):
        from main import MainWindow
        window = MainWindow()
        ratio = window.video.devicePixelRatioF()
        window.video.resize(1000, 600)
        self.assertEqual(window.preview_limit(), min(PreviewController.MAX_LIMIT, -(-1000 * ratio // 160) * 160))
        window.video.zoom = 4.0
        self.assertEqual(window.preview_limit(), PreviewController.MAX_LIMIT)
        window.video.resize(100, 100)
        window.video.zoom = 1.0
        self.assertEqual(window.preview_limit(), PreviewController.DEFAULT_LIMIT)
        window.close()


class CaptionReapplyTests(unittest.TestCase):
    def test_applying_twice_keeps_one_caption_track(self):
        from main import MainWindow
        window = MainWindow()
        window.multitrack = Timeline(tracks=[Track('video', 'V', [Clip('a.mp4', 0, 90)]), Track('text', 'Benim yazım')])
        window.caption_source = 'a.mp4'
        window.caption_segments = [{'start': 0.1, 'end': 1.0, 'text': 'merhaba'}]
        with patch.object(window, 'seek_timeline'):
            window.apply_local_captions()
            window.apply_local_captions()
        names = [track.name for track in window.multitrack.tracks]
        self.assertEqual(names.count('Altyazı / Captions'), 1)
        self.assertIn('Benim yazım', names)  # the user's own text track is left alone
        window._close_confirmed = True
        window.close()


class GraphRecorder:
    """Stands in for MediaService: keeps the filter graph FFmpeg would have been given."""
    def __init__(self, hdr=False, filters=('zscale', 'tonemap')):
        self.hdr, self.filters, self.graph = hdr, filters, ''

    def has_audio(self, path):
        return True

    def is_hdr(self, path):
        return self.hdr

    def has_filter(self, name):
        return name in self.filters

    def run(self, args, text=False):
        self.graph = Path(args[args.index('-/filter_complex') + 1]).read_text(encoding='utf-8')
        Path(args[-1]).write_bytes(b'x')
        return subprocess.CompletedProcess(args, 0, '', '')


def video_track():
    return Track('video', 'V', [Clip('v.mp4', 0, 30)])


class GraphTests(unittest.TestCase):
    def render(self, media, tracks):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('v.mp4', 'm.mp3'):
                (Path(tmp) / name).touch()
            for track in tracks:
                for clip in track.clips:
                    clip.source = str(Path(tmp) / clip.source)
            TimelineRenderer(media, (640, 360)).export(Timeline(tracks=tracks), str(Path(tmp) / 'out.mp4'))
        return media.graph

    def test_mix_of_several_sources_is_limited(self):
        graph = self.render(GraphRecorder(), [video_track(), Track('audio', 'A', [Clip('m.mp3', 0, 30)])])
        self.assertIn(f'amix=inputs=2:duration=longest:normalize=0,{LIMITER}[aout]', graph)

    def test_single_source_is_left_untouched(self):
        self.assertNotIn('alimiter', self.render(GraphRecorder(), [video_track()]))

    def test_hdr_source_is_tone_mapped_after_scaling(self):
        graph = self.render(GraphRecorder(hdr=True), [video_track()])
        self.assertIn(f'force_original_aspect_ratio=decrease,{TONE_MAP},pad=', graph)

    def test_sdr_source_and_builds_without_zscale_are_not(self):
        self.assertNotIn('tonemap', self.render(GraphRecorder(), [video_track()]))
        self.assertNotIn('tonemap', self.render(GraphRecorder(hdr=True, filters=()), [video_track()]))

    def test_hdr_is_recognised_from_the_stream_line(self):
        self.assertTrue(probing(stream('hevc (Main 10), yuv420p10le(tv, bt2020nc/bt2020/smpte2084), 3840x2160, 30 fps')).is_hdr('a'))
        self.assertTrue(probing(stream('hevc (Main 10), yuv420p10le(tv, bt2020nc/bt2020/arib-std-b67), 1920x1080, 30 fps')).is_hdr('a'))
        self.assertFalse(probing(stream('h264 (High), yuv420p(tv, bt709), 1920x1080, 30 fps')).is_hdr('a'))


@unittest.skipUnless(FFMPEG, 'needs FFmpeg')
class RealRenderTests(unittest.TestCase):
    def make(self, tmp, name, args):
        path = Path(tmp) / name
        subprocess.run([FFMPEG, '-y', '-loglevel', 'error', *args, str(path)], check=True)
        return str(path)

    def peak(self, path):
        report = subprocess.run([FFMPEG, '-hide_banner', '-i', path, '-af', 'volumedetect', '-f', 'null', '-'],
                                capture_output=True, text=True, encoding='utf-8', errors='replace').stderr
        return float(re.search(r'max_volume: (-?\d+(?:\.\d+)?) dB', report).group(1))

    def test_two_loud_sources_do_not_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            loud = ['-f', 'lavfi', '-i', 'sine=f=440:d=2', '-af', 'volume=17dB']  # about -1 dBFS each
            video = self.make(tmp, 'v.mp4', ['-f', 'lavfi', '-i', 'color=c=blue:s=320x180:r=30:d=2', *loud,
                                             '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest'])
            music = self.make(tmp, 'm.wav', loud)
            media = MediaService(FFMPEG)
            timeline = Timeline(tracks=[Track('video', 'V'), Track('audio', 'A')])
            timeline_service.append_media(timeline, 0, video, 2.0)
            timeline_service.append_media(timeline, 1, music, 2.0)
            out = str(Path(tmp) / 'out.mp4')
            TimelineRenderer(media, (320, 180)).export(timeline, out)
            self.assertLess(self.peak(out), -0.2)   # summed they would reach +5 dB and clip at 0
            self.assertGreater(self.peak(out), -3)  # held at the limit, not turned down

    def test_hdr_clip_renders_as_sdr(self):
        media = MediaService(FFMPEG)
        if not (media.has_filter('zscale') and media.has_filter('tonemap')):
            self.skipTest('this FFmpeg has no zscale/tonemap')
        with tempfile.TemporaryDirectory() as tmp:
            hdr = self.make(tmp, 'hdr.mp4', ['-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=30:d=1', '-vf',
                                             'format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=smpte2084'
                                             ':colorspace=bt2020nc', '-c:v', 'libx264', '-preset', 'ultrafast'])
            self.assertTrue(media.is_hdr(hdr))
            timeline = Timeline(tracks=[Track('video', 'V')])
            timeline_service.append_media(timeline, 0, hdr, 1.0)
            out = str(Path(tmp) / 'out.mp4')
            TimelineRenderer(media, (640, 360)).export(timeline, out)
            self.assertFalse(MediaService(FFMPEG).is_hdr(out))
            self.assertEqual(MediaService(FFMPEG).dimensions(out), (640, 360))


if __name__ == '__main__':
    unittest.main()
