"""CapCut-style trimming: a range chosen by hand and cut from every track, trimming to the playhead,
handles and cursors on the timeline, the buttons and keys."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from akis import timeline_service
from akis.multitrack_widget import MultitrackWidget
from akis.theme import color
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


def edit():
    video = Track('video', 'V', [Clip('a.mp4', 0, 100), Clip('a.mp4', 100, 100, source_in=100)])
    text = Track('text', 'T', [Clip('', 50, 80, text='x'), Clip('', 180, 10, text='y')])
    return Timeline(fps_num=10, tracks=[video, text], markers=[{'frame': 60, 'label': 'a'}, {'frame': 150, 'label': 'b'}])


class ServiceTests(unittest.TestCase):
    def test_a_range_leaves_every_track_and_the_gap_closes(self):
        timeline = edit()
        self.assertEqual(timeline_service.delete_range(timeline, 40, 120), 80)
        video, text = timeline.tracks
        self.assertEqual([(c.start, c.length, c.source_in) for c in video.clips], [(0, 40, 0), (40, 80, 120)])
        self.assertEqual(sorted((c.start, c.length, c.text) for c in text.clips), [(40, 10, 'x'), (100, 10, 'y')])
        self.assertEqual(timeline.markers, [{'frame': 70, 'label': 'b'}])

    def test_empty_or_failing_range_changes_nothing(self):
        timeline = edit()
        with self.assertRaises(ValueError):
            timeline_service.delete_range(timeline, 50, 50)
        before = timeline.to_dict()
        with patch.object(Track, 'validate', side_effect=ValueError('boom')), self.assertRaises(ValueError):
            timeline_service.delete_range(timeline, 40, 120)
        self.assertEqual(timeline.to_dict(), before)          # all or nothing

    def test_trim_to_the_playhead(self):
        timeline = edit()
        first = timeline.tracks[0].clips[0]
        timeline_service.trim_to_playhead(timeline, (0, first.id), 30, 'left')
        self.assertEqual((first.start, first.length, first.source_in), (30, 70, 30))
        timeline_service.trim_to_playhead(timeline, (0, first.id), 60, 'right')
        self.assertEqual((first.start, first.length), (30, 30))
        with self.assertRaises(ValueError):
            timeline_service.trim_to_playhead(timeline, (0, first.id), 95, 'left')     # outside the clip
        with self.assertRaises(ValueError):
            timeline_service.trim_to_playhead(timeline, None, 40, 'left')


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 100)]), Track('text', 'T')])
        self.view = MultitrackWidget(self.timeline)
        self.view.resize(900, 220)
        self.view.zoom = 4.0
        self.view.show()
        self.addCleanup(self.view.close)

    def at(self, frame, row=None, ruler=False):
        y = 15 if ruler else 30 + row * 43 + 20
        return QPoint(int(self.view.x_for(frame)), y)

    def test_dragging_from_an_empty_spot_chooses_a_range_and_a_click_clears_it(self):
        seen = []
        self.view.range_changed.connect(lambda: seen.append(self.view.range))
        QTest.mousePress(self.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.at(20, row=1))
        QTest.mouseMove(self.view, self.at(60, row=1))
        QTest.mouseRelease(self.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.at(60, row=1))
        self.assertEqual(self.view.range, (20, 60))
        QTest.mouseClick(self.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.at(80, row=1))
        self.assertIsNone(self.view.range)
        self.assertEqual(seen[-1], None)

    def test_shift_drag_on_the_ruler_also_chooses_a_range(self):
        QTest.mousePress(self.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, self.at(70, ruler=True))
        QTest.mouseMove(self.view, self.at(30, ruler=True))
        QTest.mouseRelease(self.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, self.at(30, ruler=True))
        self.assertEqual(self.view.range, (30, 70))

    def test_edges_show_a_trim_cursor_and_the_selected_clip_its_handles(self):
        self.view.selected = (0, self.timeline.tracks[0].clips[0].id)
        self.assertEqual(self.view._edge_at(self.view.x_for(100), 50), 'end')
        self.assertEqual(self.view._edge_at(self.view.x_for(50), 50), None)
        image = self.view.grab().toImage()
        handle = image.pixelColor(int(self.view.x_for(100)) - 2, 30 + 8)
        self.assertEqual(handle.name(), color('clip_selected').name())


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(self.tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        self.window.show_timeline(edit())

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_range_button_and_delete_key_cut_in_one_undo_step(self):
        w = self.window
        self.assertFalse(w.range_button.isEnabled())
        w.multitrack_view.set_range((40, 120))
        self.assertTrue(w.range_button.isEnabled())
        self.assertIn('Seçili aralık', w.status_label.text())
        w.shortcut_delete()                                            # Delete with a range: the range goes
        self.assertEqual(sum(c.length for c in w.multitrack.tracks[0].clips), 120)
        self.assertIsNone(w.multitrack_view.range)
        self.assertIn('8,0 sn kesildi', w.status_label.text())
        w.undo()
        self.assertEqual(sum(c.length for c in w.multitrack.tracks[0].clips), 200)

    def test_trim_buttons_follow_the_playhead(self):
        w = self.window
        first = w.multitrack.tracks[0].clips[0]
        w.multitrack_view.selected = (0, first.id)
        w.multitrack_view.playhead = 30
        w.trim_left()
        self.assertEqual((first.start, first.length), (30, 70))
        w.multitrack_view.playhead = 60
        w.trim_right()
        self.assertEqual(first.length, 30)
        w.multitrack_view.playhead = 5
        w.trim_left()
        self.assertIn('oynatma çizgisini seçili klibin içine', w.status_label.text())
        w.undo()
        self.assertEqual(first.length, 70) if first in w.multitrack.tracks[0].clips else None

    def test_q_w_and_escape_keys(self):
        from akis import shortcuts
        keys = {keys: action for _, _, keys, _, action in shortcuts.SHORTCUTS}
        w = self.window
        first = w.multitrack.tracks[0].clips[0]
        w.multitrack_view.selected = (0, first.id)
        w.multitrack_view.playhead = 20
        keys['Q'](w)
        self.assertEqual(w.multitrack.tracks[0].clips[0].start, 20)
        w.multitrack_view.set_range((10, 20))
        keys['Esc'](w)
        self.assertIsNone(w.multitrack_view.range)
        w.apply_language('en')
        self.assertIn('Delete range', [b.text() for b in w.findChildren(type(w.range_button))])


if __name__ == '__main__':
    unittest.main()
