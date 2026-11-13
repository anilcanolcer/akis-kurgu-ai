"""A clip's own speed: model, mapping to the source, preview sound, captions, render, the button."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import caption_service, edit_plan, emphasis, timeline_service
from akis.frame_plan import plan_frame
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track, clip_speed
from akis.timeline_render import TimelineRenderer, atempo_chain
from akis.timeline_slice import slice_timeline

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


def fast(start=0, length=30, source_in=60, speed=2.0, **kw):
    return Clip('a.mp4', start, length, source_in=source_in, style={'speed': speed}, **kw)


class ModelTests(unittest.TestCase):
    def test_speed_maps_timeline_frames_to_source_frames(self):
        clip = fast(start=10)
        self.assertEqual((clip.speed, clip.source_frames, clip.source_end), (2.0, 60, 120))
        self.assertEqual(clip.source_frame(10), 60)
        self.assertEqual(clip.source_frame(25), 90)
        self.assertEqual(clip.timeline_frame(90), 25)
        self.assertEqual(Clip('a.mp4', 0, 30).speed, 1.0)
        for bad in ('x', None, float('nan')):
            self.assertEqual(clip_speed(Clip('a.mp4', 0, 3, style={'speed': bad})), 1.0)
        self.assertEqual(clip_speed(Clip('a.mp4', 0, 3, style={'speed': 99})), 4.0)

    def test_source_length_counts_the_footage_played(self):
        with self.assertRaises(ValueError):
            fast(source_in=0, source_length=59)           # 30 frames at 2× need 60
        fast(source_in=0, source_length=60)
        Clip('a.mp4', 0, 40, style={'speed': 0.5}, source_length=20)  # slow motion needs less

    def test_split_halves_never_need_more_footage_than_the_whole(self):
        for speed in (0.25, 0.75, 1.5, 3.0):
            length = 37
            clip = Clip('a.mp4', 0, length, style={'speed': speed},
                        source_length=int(length * speed + 1e-6))
            track = Track('video', 'V', [clip])
            right = track.split(clip.id, 13)
            self.assertEqual(right.source_in, clip.source_end)
            self.assertLessEqual(right.source_end, clip.source_length)
            self.assertEqual(right.speed, speed)

    def test_frame_plan_and_slice_follow_the_speed(self):
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', [fast()])])
        self.assertEqual(plan_frame(timeline, 10)[0].source_frame, 80)
        part = slice_timeline(timeline, 10, 30)
        piece = part.tracks[0].clips[0]
        self.assertEqual((piece.start, piece.length, piece.source_in, piece.speed), (0, 20, 80, 2.0))


class ServiceTests(unittest.TestCase):
    def timeline(self):
        clips = [Clip('a.mp4', 0, 30, source_in=0, keyframes={'zoom': [{'frame': 20, 'value': 1.2}]}),
                 Clip('a.mp4', 30, 30, source_in=100), Clip('a.mp4', 90, 10, source_in=200)]
        return Timeline(fps_num=30, tracks=[Track('video', 'V', clips), Track('text', 'T', [Clip('', 40, 10, text='x')])])

    def test_setting_a_speed_keeps_the_footage_and_ripples_its_track(self):
        timeline = self.timeline()
        first = timeline.tracks[0].clips[0]
        delta = timeline_service.set_clip_speed(timeline, (0, first.id), 0.5)
        self.assertEqual((delta, first.length, first.source_frames), (30, 60, 30))
        self.assertEqual([c.start for c in timeline.tracks[0].clips], [0, 60, 120])
        self.assertEqual(timeline.tracks[1].clips[0].start, 40)            # other tracks stay
        self.assertEqual(first.keyframes['zoom'][0]['frame'], 40)          # stretched along
        timeline_service.set_clip_speed(timeline, (0, first.id), 1.0)
        self.assertNotIn('speed', first.style)
        self.assertEqual([c.start for c in timeline.tracks[0].clips], [0, 30, 90])

    def test_text_clips_and_bad_speeds_are_refused(self):
        timeline = self.timeline()
        with self.assertRaises(ValueError):
            timeline_service.set_clip_speed(timeline, (1, timeline.tracks[1].clips[0].id), 2.0)
        with self.assertRaises(ValueError):
            timeline_service.set_clip_speed(timeline, (0, timeline.tracks[0].clips[0].id), 8.0)

    def test_preview_sound_plays_at_the_clip_speed(self):
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', [fast()])])
        self.assertEqual(timeline_service.audio_target(timeline, 15, 1.25), ('a.mp4', 3000, 2.5))
        self.assertEqual(timeline_service.audio_targets(timeline, 15, 1.0)[0].rate, 2.0)

    def test_captions_land_where_the_clip_shows_the_words(self):
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip('a.mp4', 50, 20, source_in=100,
                                                                          style={'speed': 2.0})])])
        caption_service.caption_track(timeline, 'a.mp4', [{'start': 12.0, 'end': 13.0, 'text': 'Merhaba'}])
        caption = timeline.tracks[-1].clips[0]
        self.assertEqual((caption.start, caption.end), (60, 65))

    def test_a_plan_recut_does_not_carry_the_speed_over(self):
        old = [fast(source_in=0, length=30)]
        pieces = edit_plan._recut_pieces(old, 'a.mp4', 0, 60)
        self.assertTrue(all('speed' not in style for _, _, _, style, _ in pieces))

    def test_punches_inside_the_played_footage(self):
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', [fast(source_in=0)])])
        emphasis.apply(timeline, {'a.mp4': [1.5]})          # source frame 45: inside a 2× clip of 30 frames
        self.assertTrue(timeline.tracks[0].clips[0].style.get('punch'))
        self.assertIn('it*2.000000', emphasis.zoom_filter(timeline.tracks[0].clips[0], 30, 1, 0.0, 320, 180))


class TempoTests(unittest.TestCase):
    def test_atempo_chain_stays_inside_each_instance_range(self):
        self.assertEqual(atempo_chain(1.0), '')
        self.assertEqual(atempo_chain(4.0), ',atempo=2.000000,atempo=2.000000')
        self.assertEqual(atempo_chain(0.25), ',atempo=0.500000,atempo=0.500000')
        self.assertEqual(atempo_chain(3.0), ',atempo=2.000000,atempo=1.500000')


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'source.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=160x90:r=10:d=12', '-f', 'lavfi',
                        '-i', 'sine=frequency=440:duration=12', '-pix_fmt', 'yuv420p', '-shortest', str(cls.source)],
                       check=True)
        cls.media = MediaService(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def grab(self, path, second):
        return subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{second:.3f}', '-i', str(path), '-frames:v', '1',
                               '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True, check=True).stdout

    def differs(self, a, b):
        return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

    def test_fast_and_slow_clips_keep_their_length_and_show_the_right_footage(self):
        clips = [Clip(str(self.source), 0, 20, source_in=0, style={'speed': 2.0}),     # 4 s of footage in 2 s
                 Clip(str(self.source), 20, 20, source_in=60, style={'speed': 0.5})]   # 1 s of footage in 2 s
        output = self.root / 'speed.mp4'
        TimelineRenderer(self.media, (160, 90)).export(Timeline(fps_num=10, tracks=[Track('video', 'V', clips)]), output)
        self.assertAlmostEqual(self.media.duration(output), 4.0, delta=0.15)
        self.assertTrue(self.media.has_audio(output))
        # 1.5 s into the edit the fast clip shows source second 3; 3.0 s in, the slow one shows 6.5.
        self.assertLess(self.differs(self.grab(output, 1.5), self.grab(self.source, 3.0)), 6)
        self.assertGreater(self.differs(self.grab(output, 1.5), self.grab(self.source, 1.5)), 6)
        self.assertLess(self.differs(self.grab(output, 3.0), self.grab(self.source, 6.5)), 6)

    def test_a_preview_frame_of_a_fast_clip(self):
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip(str(self.source), 0, 30, source_in=10,
                                                                          style={'speed': 3.0})])])
        output = self.root / 'frame.png'
        TimelineRenderer(self.media, (160, 90)).preview(timeline, 10, output)
        picture = subprocess.run([FFMPEG, '-v', 'error', '-i', str(output), '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                                 capture_output=True, check=True).stdout
        self.assertLess(self.differs(picture, self.grab(self.source, 4.0)), 6)   # source frame 10 + 10 × 3


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch('main.recovery_dir', return_value=Path(self.tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_button_sets_the_speed_in_one_undo_step(self):
        w = self.window
        clips = [Clip('a.mp4', 0, 30), Clip('a.mp4', 30, 30, source_in=30)]
        w.show_timeline(Timeline(fps_num=30, tracks=[Track('video', 'V', clips)]))
        w.multitrack_view.selected = (0, w.multitrack.tracks[0].clips[0].id)
        with patch('main.QInputDialog.getItem', return_value=('2×', True)):
            w.set_clip_speed()
        first, second = w.multitrack.tracks[0].clips
        self.assertEqual((first.length, first.speed, second.start), (15, 2.0, 15))
        self.assertIn('2×', w.status.text() if hasattr(w, 'status') else '2×')
        w.undo()
        self.assertEqual([c.length for c in w.multitrack.tracks[0].clips], [30, 30])
        self.assertEqual(w.multitrack.tracks[0].clips[0].speed, 1.0)

    def test_text_clips_are_not_offered(self):
        w = self.window
        w.show_timeline(Timeline(fps_num=30, tracks=[Track('text', 'T', [Clip('', 0, 30, text='a')])]))
        w.multitrack_view.selected = (0, w.multitrack.tracks[0].clips[0].id)
        with patch('main.QInputDialog.getItem') as asked:
            w.set_clip_speed()
        asked.assert_not_called()


if __name__ == '__main__':
    unittest.main()


class FcpxmlTests(unittest.TestCase):
    def test_speeds_are_reported_as_left_out(self):
        from akis import fcpxml_export, i18n
        text = fcpxml_export.describe({'clips': 3, 'texts': 0, 'transitions': 0, 'speeds': 2})
        self.assertIn('2 klibin hızı aktarılmadı', text)
        english = fcpxml_export.describe({'clips': 3, 'texts': 0, 'transitions': 0, 'speeds': 2},
                                         lambda t: i18n.translate(t, 'en'))
        self.assertIn('The speed of 2 clips was left out', english)
