"""Trimming a clip from its start: the model rule and dragging the left edge on the timeline."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from akis.multitrack_widget import MultitrackWidget
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


def state(clip):
    return clip.start, clip.length, clip.source_in


class ModelTests(unittest.TestCase):
    def test_right_edge_and_the_picture_under_it_stay_put(self):
        clip = Clip('a.mp4', 100, 60, source_in=30, source_length=300)
        track = Track('video', 'Video', [clip])
        track.trim_start(clip.id, 120)                  # hide the first 20 frames
        self.assertEqual(state(clip), (120, 40, 50))
        self.assertEqual(clip.end, 160)
        track.trim_start(clip.id, 90)                   # bring back those and 10 more
        self.assertEqual(state(clip), (90, 70, 20))
        self.assertEqual(clip.end, 160)

    def test_cannot_reveal_more_than_the_source_has_or_empty_the_clip(self):
        clip = Clip('a.mp4', 100, 60, source_in=30)
        track = Track('video', 'Video', [clip])
        for start in (60, 160, 200, -5):                # 40 frames earlier than the source begins; no length left
            with self.assertRaises(ValueError):
                track.trim_start(clip.id, start)
            self.assertEqual(state(clip), (100, 60, 30))
        track.trim_start(clip.id, 70)                   # exactly to the source's first frame
        self.assertEqual(state(clip), (70, 90, 0))

    def test_cannot_run_into_the_previous_clip(self):
        first, second = Clip('a.mp4', 0, 50), Clip('a.mp4', 50, 50, source_in=100)
        track = Track('video', 'Video', [first, second])
        with self.assertRaises(ValueError):
            track.trim_start(second.id, 40)
        self.assertEqual(state(second), (50, 50, 100))

    def test_text_clip_extends_freely_and_keyframes_keep_their_frames(self):
        clip = Clip('', 100, 60, text='Merhaba', keyframes={'x': [{'frame': 0, 'value': 1}, {'frame': 30, 'value': 2}]})
        track = Track('text', 'Yazı', [clip])
        track.trim_start(clip.id, 80)
        self.assertEqual(state(clip), (80, 80, 0))
        self.assertEqual([p['frame'] for p in clip.keyframes['x']], [20, 50])
        track.trim_start(clip.id, 110)                  # the first keyframe now lies before the clip
        self.assertEqual([p['frame'] for p in clip.keyframes['x']], [20])
        self.assertEqual(clip.end, 160)


class WidgetTests(unittest.TestCase):
    """Default zoom is 2 px per frame and frame 0 is at x = 100."""

    def widget(self, clip):
        widget = MultitrackWidget(Timeline(tracks=[Track('video', 'Video', [clip])]))
        widget.resize(600, 210)
        widget.show()
        self.addCleanup(widget.close)
        self.changes = []
        widget.changed.connect(lambda: self.changes.append(True))
        return widget

    def drag(self, widget, start_x, end_x):
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(start_x, 45))
        QTest.mouseMove(widget, QPoint(end_x, 45))
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(end_x, 45))

    def test_dragging_the_left_edge_trims_the_start(self):
        clip = Clip('a.mp4', 50, 100, source_in=40)     # drawn from x=200 to x=400
        widget = self.widget(clip)
        self.drag(widget, 203, 243)                     # 20 frames to the right
        self.assertEqual(state(clip), (70, 80, 60))
        self.assertEqual(self.changes, [True])
        self.drag(widget, 243, 163)                     # 40 frames to the left
        self.assertEqual(state(clip), (30, 120, 20))
        self.assertEqual(clip.end, 150)

    def test_middle_still_moves_and_right_edge_still_trims_the_end(self):
        clip = Clip('a.mp4', 50, 100, source_in=40)
        widget = self.widget(clip)
        self.drag(widget, 300, 320)
        self.assertEqual(state(clip), (60, 100, 40))
        self.drag(widget, 417, 397)                     # right edge is now at x=420
        self.assertEqual(state(clip), (60, 90, 40))

    def test_drag_past_the_source_start_stops_at_the_last_valid_frame(self):
        clip = Clip('a.mp4', 50, 100, source_in=10)
        widget = self.widget(clip)
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(203, 45))
        QTest.mouseMove(widget, QPoint(190, 45))        # 6 frames left: fine
        QTest.mouseMove(widget, QPoint(120, 45))        # far beyond the source start: refused
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(120, 45))
        self.assertGreaterEqual(clip.source_in, 0)
        self.assertEqual(clip.end, 150)
        self.assertLess(clip.start, 50)


if __name__ == '__main__':
    unittest.main()
