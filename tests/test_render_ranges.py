"""Long edits render their picture in ranges, so ffmpeg never holds hundreds of decoders at once."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akis import timeline_render
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer
from akis.timeline_slice import plan_ranges

FFMPEG = shutil.which('ffmpeg')


class PlanTests(unittest.TestCase):
    def test_ranges_cover_everything_and_respect_the_limit(self):
        clips = [Clip('a.mp4', i * 90, 90, source_in=i * 150) for i in range(120)]
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', clips)])
        ranges = plan_ranges(timeline, 16, 10800)
        self.assertEqual((ranges[0][0], ranges[-1][1]), (0, 10800))
        self.assertTrue(all(a[1] == b[0] for a, b in zip(ranges, ranges[1:])))
        for a, b in ranges:
            self.assertLessEqual(sum(1 for c in clips if c.start < b and c.end > a), 16)

    def test_never_starts_a_range_on_a_transition(self):
        clips = [Clip('a.mp4', i * 90, 90, style={'transition': 'fade'} if i % 2 else {}) for i in range(40)]
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', clips)])
        starts = {a for a, _ in plan_ranges(timeline, 8, 3600)} - {0}
        transition_starts = {c.start for c in clips if c.style}
        self.assertTrue(starts and not starts & transition_starts)

    def test_few_clips_is_one_range(self):
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 90)])])
        self.assertEqual(plan_ranges(timeline, 16, 90), [(0, 90)])

    def test_overlays_count_and_muted_tracks_do_not(self):
        main = Track('video', 'V', [Clip('a.mp4', i * 30, 30) for i in range(10)])
        overlay = Track('overlay', 'O', [Clip('b.mp4', 0, 300)])
        muted = Track('video', 'M', [Clip('c.mp4', i * 10, 10) for i in range(30)], muted=True)
        ranges = plan_ranges(Timeline(fps_num=30, tracks=[main, overlay, muted]), 4, 300)
        self.assertGreater(len(ranges), 2)
        for a, b in ranges:
            count = sum(1 for c in main.clips + overlay.clips if c.start < b and c.end > a)
            self.assertLessEqual(count, 4 if b - a > 30 else 5)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'source.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=160x90:r=10:d=12', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=12', '-pix_fmt', 'yuv420p', '-shortest', str(cls.source)], check=True)
        cls.music = cls.root / 'music.wav'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=12', str(cls.music)], check=True)
        cls.media = MediaService(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def timeline(self, speed_music=True):
        clips = [Clip(str(self.source), i * 10, 10, source_in=i * 12) for i in range(9)]
        tracks = [Track('video', 'V', clips), Track('text', 'T', [Clip('', 25, 30, text='Yazı')])]
        if speed_music:
            tracks.append(Track('audio', 'M', [Clip(str(self.music), 0, 90)]))
        return Timeline(fps_num=10, tracks=tracks)

    def frames(self, path):
        text = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path), '-map', '0:v', '-f', 'null', '-'],
                              capture_output=True, text=True).stderr
        return int(re.findall(r'frame=\s*(\d+)', text)[-1])

    def export(self, name, timeline, **options):
        output = self.root / name
        seen = []
        TimelineRenderer(self.media, (160, 90), **options).export(timeline, output, on_progress=seen.append)
        return output, seen

    def test_ranges_give_the_same_length_frames_and_sound_as_one_pass(self):
        one, _ = self.export('one.mp4', self.timeline())
        with patch.object(timeline_render, 'MAX_PICTURE_INPUTS', 2):
            with patch.object(TimelineRenderer, '_render', autospec=True, side_effect=TimelineRenderer._render) as render:
                ranged, seen = self.export('ranged.mp4', self.timeline())
        modes = [call.kwargs.get('streams', 'both') for call in render.call_args_list]
        self.assertGreater(modes.count('video'), 3)
        self.assertEqual(modes.count('audio'), 1)
        self.assertEqual(self.frames(ranged), self.frames(one))
        self.assertAlmostEqual(self.media.duration(ranged), self.media.duration(one), delta=0.05)
        self.assertTrue(self.media.has_audio(ranged))
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(seen[-1], 1.0)
        self.assertFalse((self.root / 'ranged.part.mp4').exists())

    def test_speed_and_a_silent_edit(self):
        with patch.object(timeline_render, 'MAX_PICTURE_INPUTS', 2):
            fast, _ = self.export('fast.mp4', self.timeline(), speed=2.0)
            silent_timeline = self.timeline(speed_music=False)
            for clip in silent_timeline.tracks[0].clips:
                clip.volume = 0.0
            silent, _ = self.export('silent.mp4', silent_timeline)
        self.assertAlmostEqual(self.media.duration(fast), 4.5, delta=0.15)
        self.assertTrue(self.media.has_audio(fast))
        self.assertAlmostEqual(self.media.duration(silent), 9.0, delta=0.15)

    def test_failure_in_a_range_leaves_no_partial_file(self):
        broken = self.timeline()
        broken.tracks[0].clips[5].source = str(self.root / 'gone.mp4')
        output = self.root / 'broken.mp4'
        with patch.object(timeline_render, 'MAX_PICTURE_INPUTS', 2), self.assertRaises(FileNotFoundError):
            TimelineRenderer(self.media, (160, 90)).export(broken, output)
        self.assertFalse(output.exists())
        self.assertFalse((self.root / 'broken.part.mp4').exists())


if __name__ == '__main__':
    unittest.main()
