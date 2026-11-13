"""The playback copy in stored pieces: where pieces start, what makes a piece new, reuse, and the proxy."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from akis import chunk_preview
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer
from akis.timeline_slice import slice_timeline

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


def edit(count=12, length=60, fade_every=3):
    clips = [Clip('a.mp4', i * length, length, source_in=i * 70,
                  style={'transition': 'fade', 'transition_frames': 12} if i % fade_every == 1 else {})
             for i in range(count)]
    return Timeline(fps_num=30, tracks=[Track('video', 'V', clips)])


class BoundTests(unittest.TestCase):
    def test_pieces_cover_the_edit_and_never_start_inside_an_entrance(self):
        timeline = edit()
        total = 12 * 60
        bounds = chunk_preview.chunk_bounds(timeline, total, 16, seconds=2.0)
        self.assertEqual((bounds[0][0], bounds[-1][1]), (0, total))
        self.assertTrue(all(a[1] == b[0] for a, b in zip(bounds, bounds[1:])))
        entrances = [(c.start, c.start + 12) for c in timeline.tracks[0].clips if c.style]
        for start, _ in bounds[1:]:
            self.assertFalse(any(a <= start < b for a, b in entrances), start)
        self.assertTrue(all(b - a <= 2 * 30 + 12 for a, b in bounds))

    def test_crowded_pieces_are_cut_finer(self):
        clips = [Clip('a.mp4', i * 3, 3) for i in range(40)]      # 40 clips in 4 s
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', clips)])
        bounds = chunk_preview.chunk_bounds(timeline, 120, 8)
        for a, b in bounds:
            self.assertLessEqual(sum(1 for c in clips if c.start < b and c.end > a), 8)

    def test_key_follows_the_picture_only(self):
        timeline = edit(count=2)
        size, look = (854, 480), {'fast': True}
        key = chunk_preview.piece_key(slice_timeline(timeline, 0, 60), size, look)
        same = edit(count=2)                                  # new clip ids, same content
        same.tracks[0].clips[0].volume = 0.3                  # sound only
        same.tracks.append(Track('audio', 'M', [Clip('music.mp3', 0, 60)]))
        self.assertEqual(chunk_preview.piece_key(slice_timeline(same, 0, 60), size, look), key)
        moved = edit(count=2)
        moved.tracks[0].clips[0].source_in = 5
        self.assertNotEqual(chunk_preview.piece_key(slice_timeline(moved, 0, 60), size, look), key)
        self.assertNotEqual(chunk_preview.piece_key(slice_timeline(timeline, 0, 60), size, {'fast': True, 'brightness': 5}), key)

    def test_tidy_keeps_used_and_recent_pieces(self):
        with tempfile.TemporaryDirectory() as folder:
            for index in range(chunk_preview.KEEP_UNUSED + 5):
                path = Path(folder) / f'k{index}.mp4'
                path.write_bytes(b'x')
                os.utime(path, (index, index))
            chunk_preview.tidy(folder, {'k0'})
            left = {p.stem for p in Path(folder).glob('*.mp4')}
            self.assertIn('k0', left)                         # in use, however old
            self.assertNotIn('k1', left)                      # old and unused
            self.assertEqual(len(left), chunk_preview.KEEP_UNUSED + 1)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'source.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=20', '-f', 'lavfi',
                        '-i', 'sine=frequency=330:duration=20', '-pix_fmt', 'yuv420p', '-shortest', str(cls.source)], check=True)
        cls.media = MediaService(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def timeline(self):
        clips = [Clip(str(self.source), i * 45, 45, source_in=i * 50,
                      style={'transition': 'fade', 'transition_frames': 10} if i == 3 else {}) for i in range(8)]
        return Timeline(fps_num=30, tracks=[Track('video', 'V', clips), Track('text', 'T', [Clip('', 30, 60, text='Yazı')])])

    def grab(self, path, second):
        return subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{second:.3f}', '-i', str(path), '-frames:v', '1',
                               '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True, check=True).stdout

    def frames(self, path):
        text = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path), '-map', '0:v', '-f', 'null', '-'],
                              capture_output=True, text=True).stderr
        return int(re.findall(r'frame=\s*(\d+)', text)[-1])

    def test_pieces_match_one_render_and_only_changed_pieces_are_drawn(self):
        renderer = TimelineRenderer(self.media, (320, 180), fast=True)
        store = self.root / 'store'
        whole = renderer.export(self.timeline(), self.root / 'whole.mp4')
        timeline = self.timeline()
        original = chunk_preview.CHUNK_SECONDS
        chunk_preview.CHUNK_SECONDS = 2.0
        try:
            first, drawn, reused = renderer.export_pieces(timeline, self.root / 'p1.mp4', store)
            self.assertEqual((reused, drawn > 3), (0, True))
            self.assertEqual(self.frames(first), self.frames(whole))
            self.assertTrue(self.media.has_audio(first))
            for second in (1.0, 2.0, 4.0, 4.5, 6.0, 8.0, 11.0):  # piece edges included
                a, b = self.grab(whole, second), self.grab(first, second)
                self.assertLess(sum(abs(x - y) for x, y in zip(a, b)) / len(a), 4, second)
            _, again, kept = renderer.export_pieces(timeline, self.root / 'p2.mp4', store)
            self.assertEqual((again, kept), (0, drawn))
            timeline.tracks[0].trim_end(timeline.tracks[0].clips[-1].id, timeline.tracks[0].clips[-1].end - 15)
            third, redrawn, _ = renderer.export_pieces(timeline, self.root / 'p3.mp4', store)
            self.assertEqual(redrawn, 1)
            self.assertAlmostEqual(self.media.duration(third), 11.5, delta=0.1)
        finally:
            chunk_preview.CHUNK_SECONDS = original

    def test_proxy_worker_uses_the_store(self):
        from akis.render_worker import TimelineRenderWorker
        store = self.root / 'proxy-store'
        worker = TimelineRenderWorker(self.timeline(), str(self.root / 'proxy.mp4'), (320, 180), FFMPEG,
                                      adjustments={'fast': True, 'speed': 1.0, 'pieces': str(store)})
        seen = []
        worker.completed.connect(seen.append)
        worker.run()
        self.assertEqual(seen, [str(self.root / 'proxy.mp4')])
        self.assertTrue(list(store.glob('*.mp4')))
        started = time.time()
        TimelineRenderWorker(self.timeline(), str(self.root / 'proxy2.mp4'), (320, 180), FFMPEG,
                             adjustments={'fast': True, 'speed': 1.0, 'pieces': str(store)}).run()
        self.assertTrue((self.root / 'proxy2.mp4').is_file())
        self.assertLess(time.time() - started, 30)


class ProxyTests(unittest.TestCase):
    def test_proxy_asks_for_stored_pieces(self):
        from akis.preview_widget import ProxyPlayback
        made = []

        class Fake:
            def __init__(self, timeline, output, size, executable, adjustments=None):
                made.append(adjustments)
                for name in ('completed', 'failed', 'finished'):
                    setattr(self, name, type('S', (), {'connect': lambda *_: None})())

            def start(self):
                pass

            def cancel(self):
                pass

            def wait(self, *_):
                return True

        proxy = ProxyPlayback('ffmpeg', worker_factory=Fake)
        self.addCleanup(proxy.close)
        proxy.prepare(edit(count=2), (640, 360), {}, 'sig')
        self.assertTrue(made[0]['pieces'].endswith('pieces'))
        self.assertEqual((made[0]['fast'], made[0]['speed']), (True, 1.0))


if __name__ == '__main__':
    unittest.main()
