"""Dragging a clip onto another track of the same kind on the timeline."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from akis.multitrack_widget import MultitrackWidget
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
ROW = lambda index: 30 + index * 43 + 15        # a y inside the given track's row


class DragTests(unittest.TestCase):
    """Default zoom is 2 px per frame and frame 0 is at x = 100."""

    def widget(self, *tracks):
        widget = MultitrackWidget(Timeline(tracks=list(tracks)))
        widget.resize(700, 260)
        widget.show()
        self.addCleanup(widget.close)
        self.changes = []
        widget.changed.connect(lambda: self.changes.append(True))
        return widget

    def drag(self, widget, start, end):
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(*start))
        QTest.mouseMove(widget, QPoint(*end))
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(*end))

    def test_clip_moves_to_another_video_track_and_keeps_its_time(self):
        clip = Clip('a.mp4', 50, 60)
        widget = self.widget(Track('video', 'Ana', [clip]), Track('video', 'B-roll'))
        self.drag(widget, (250, ROW(0)), (250, ROW(1)))
        self.assertEqual(widget.model.tracks[0].clips, [])
        self.assertEqual(widget.model.tracks[1].clips, [clip])
        self.assertEqual(clip.start, 50)
        self.assertEqual(widget.selected, (1, clip.id))
        self.assertEqual(self.changes, [True])           # one undo step, even without a change in time

    def test_clip_can_change_track_and_time_in_one_drag(self):
        clip = Clip('a.mp4', 50, 60)
        widget = self.widget(Track('video', 'Ana', [clip]), Track('video', 'B-roll'))
        self.drag(widget, (250, ROW(0)), (290, ROW(1)))
        self.assertEqual(widget.model.tracks[1].clips, [clip])
        self.assertEqual(clip.start, 70)

    def test_other_kinds_of_track_are_not_a_target(self):
        clip = Clip('a.mp4', 50, 60)
        widget = self.widget(Track('video', 'Ana', [clip]), Track('audio', 'Müzik'), Track('text', 'Yazı'))
        self.drag(widget, (250, ROW(0)), (250, ROW(1)))
        self.drag(widget, (250, ROW(0)), (250, ROW(2)))
        self.assertEqual(widget.model.tracks[0].clips, [clip])
        self.assertEqual(self.changes, [])

    def test_occupied_place_keeps_the_clip_where_it_was(self):
        clip, other = Clip('a.mp4', 50, 60), Clip('b.mp4', 40, 100)
        widget = self.widget(Track('video', 'Ana', [clip]), Track('video', 'B-roll', [other]))
        self.drag(widget, (250, ROW(0)), (250, ROW(1)))
        self.assertEqual(widget.model.tracks[0].clips, [clip])
        self.assertEqual(widget.model.tracks[1].clips, [other])
        self.assertEqual(widget.selected, (0, clip.id))
        self.assertEqual(self.changes, [])

    def test_audio_clips_move_between_audio_tracks(self):
        clip = Clip('m.mp3', 0, 40)
        widget = self.widget(Track('audio', 'Müzik', [clip]), Track('audio', 'Efekt'))
        self.drag(widget, (130, ROW(0)), (130, ROW(1)))
        self.assertEqual(widget.model.tracks[1].clips, [clip])

    def test_a_drag_within_its_own_track_is_unchanged(self):
        clip = Clip('a.mp4', 50, 60)
        widget = self.widget(Track('video', 'Ana', [clip]), Track('video', 'B-roll'))
        self.drag(widget, (250, ROW(0)), (270, ROW(0)))
        self.assertEqual((widget.model.tracks[0].clips, clip.start), ([clip], 60))
        self.assertEqual(self.changes, [True])


class WindowTests(unittest.TestCase):
    def test_moving_to_another_track_is_one_undo_step(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from main import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        window = MainWindow()
        patch.object(window.preview, 'request').start()
        clip = Clip('a.mp4', 50, 60)
        window.show_timeline(Timeline(tracks=[Track('video', 'Ana', [clip]), Track('video', 'B-roll')]))
        view = window.multitrack_view
        view.resize(700, 260)
        QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(250, ROW(0)))
        QTest.mouseMove(view, QPoint(250, ROW(1)))
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(250, ROW(1)))
        self.assertEqual([len(t.clips) for t in window.multitrack.tracks], [0, 1])
        self.assertTrue(window.undo())
        self.assertEqual([len(t.clips) for t in window.multitrack.tracks], [1, 0])
        window._close_confirmed = True
        window.close()


if __name__ == '__main__':
    unittest.main()
