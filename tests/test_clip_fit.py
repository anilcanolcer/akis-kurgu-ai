"""Fit or fill: the filter text, real renders checked pixel by pixel, the tool button and its undo step."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import clip_fit
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


class FilterTests(unittest.TestCase):
    def test_a_clip_without_the_option_is_fitted_as_before(self):
        self.assertEqual(clip_fit.filters({}, 1080, 1920),
                         ('scale=1080:1920:force_original_aspect_ratio=decrease',
                          'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black'))
        self.assertEqual(clip_fit.filters({'fit': 'nonsense'}, 1080, 1920), clip_fit.filters({}, 1080, 1920))

    def test_fill_scales_up_and_crops_around_the_focus(self):
        scale, place = clip_fit.filters({'fit': 'fill'}, 1080, 1920)
        self.assertEqual(scale, 'scale=1080:1920:force_original_aspect_ratio=increase')
        self.assertEqual(place, 'crop=1080:1920:(iw-1080)*0.5000:(ih-1920)*0.5000')
        self.assertIn('*1.0000', clip_fit.filters({'fit': 'fill', 'focus': 7}, 1080, 1920)[1])      # clamped
        self.assertIn('*0.5000', clip_fit.filters({'fit': 'fill', 'focus': 'left'}, 1080, 1920)[1])  # unreadable

    def test_apply_sets_and_clears_the_keys_and_keeps_the_rest(self):
        clip = Clip('a.mp4', 0, 10, style={'transition': 'fade'})
        clip_fit.apply(clip, 'fill', 0.0)
        self.assertEqual(clip.style, {'transition': 'fade', 'fit': 'fill', 'focus': 0.0})
        self.assertEqual(clip_fit.choice_index(clip.style), 2)
        clip_fit.apply(clip, 'fit')
        self.assertEqual(clip.style, {'transition': 'fade'})
        self.assertEqual(clip_fit.choice_index(clip.style), 0)
        with self.assertRaises(ValueError):
            clip_fit.apply(clip, 'stretch')

    def test_split_keeps_the_framing_on_both_halves(self):
        clip = Clip('a.mp4', 0, 10, style={'fit': 'fill', 'focus': 1.0})
        track = Track('video', 'Video', [clip])
        right = track.split(clip.id, 4)
        self.assertEqual(right.style, {'fit': 'fill', 'focus': 1.0})


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealRenderTests(unittest.TestCase):
    """A wide picture (left half red, right half blue) on a tall canvas."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'wide.mp4'
        graph = 'color=c=red:s=160x180:r=10:d=1[l];color=c=blue:s=160x180:r=10:d=1[r];[l][r]hstack'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-filter_complex', graph, '-pix_fmt', 'yuv420p', str(cls.source)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def pixels(self, style):
        """(top centre, middle left, middle right) RGB of the rendered 180x320 frame."""
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'Video', [Clip(str(self.source), 0, 10, style=style)])])
        picture = self.root / 'frame.png'
        TimelineRenderer(MediaService(FFMPEG), (180, 320)).preview(timeline, 2, picture)
        raw = subprocess.run([FFMPEG, '-v', 'error', '-i', str(picture), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             capture_output=True, check=True).stdout
        self.assertEqual(len(raw), 180 * 320 * 3)
        at = lambda x, y: tuple(raw[(y * 180 + x) * 3:(y * 180 + x) * 3 + 3])
        return at(90, 10), at(20, 160), at(160, 160)

    def colour(self, rgb):
        r, g, b = rgb
        return 'red' if r > 150 and b < 100 else 'blue' if b > 150 and r < 100 else 'black' if max(rgb) < 40 else 'other'

    def test_fitted_clip_leaves_bars_and_shows_the_whole_picture(self):
        top, left, right = map(self.colour, self.pixels({}))
        self.assertEqual((top, left, right), ('black', 'red', 'blue'))

    def test_filled_clip_has_no_bars_and_keeps_the_chosen_side(self):
        for focus, expected in ((0.0, ('red', 'red', 'red')), (1.0, ('blue', 'blue', 'blue')), (0.5, ('other', 'red', 'blue'))):
            top, left, right = map(self.colour, self.pixels({'fit': 'fill', 'focus': focus}))
            self.assertNotEqual(top, 'black', focus)
            self.assertEqual((left, right), expected[1:], focus)


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))
        w = self.window
        self.index = next(i for i, t in enumerate(w.multitrack.tracks) if t.kind == 'video')
        self.clip = lambda: w.multitrack.tracks[self.index].clips[0]

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def choose(self, label, ok=True):
        with patch('PySide6.QtWidgets.QInputDialog.getItem', return_value=(label, ok)) as dialog:
            self.window.set_clip_fit()
        return dialog

    def test_needs_a_selected_video_clip(self):
        dialog = self.choose(clip_fit.CHOICES[1][0])
        dialog.assert_not_called()
        self.assertIn('video klibi seçin', self.window.status_label.text())

    def test_choice_is_applied_shown_as_current_and_undoable(self):
        w = self.window
        w.multitrack_view.selected, w.multitrack_view.selected_track = (self.index, self.clip().id), self.index
        self.choose(clip_fit.CHOICES[3][0])
        self.assertEqual(self.clip().style, {'fit': 'fill', 'focus': 1.0})
        dialog = self.choose(clip_fit.CHOICES[0][0], ok=False)          # dismissed: nothing changes
        self.assertEqual(dialog.call_args.args[4], 3)                   # opens on the current choice
        self.assertEqual(self.clip().style, {'fit': 'fill', 'focus': 1.0})
        self.assertTrue(w.undo())
        self.assertEqual(self.clip().style, {})
        self.assertFalse(w.undo())

    def test_project_file_keeps_the_framing(self):
        w = self.window
        w.multitrack_view.selected, w.multitrack_view.selected_track = (self.index, self.clip().id), self.index
        self.choose(clip_fit.CHOICES[2][0])
        restored = Timeline.from_dict(w.project_document()['timeline'])
        self.assertEqual(restored.tracks[self.index].clips[0].style, {'fit': 'fill', 'focus': 0.0})


if __name__ == '__main__':
    unittest.main()
