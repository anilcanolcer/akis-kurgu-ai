import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from akis.timeline_model import Clip, Timeline, Track
from akis.multitrack_widget import MultitrackWidget

app = QApplication.instance() or QApplication([])

class TimelineWidgetTests(unittest.TestCase):
    def test_select_empty_track_and_scrub_ruler(self):
        clip = Clip('demo.mp4', 0, 60)
        model = Timeline(tracks=[Track('video', 'Video', [clip]), Track('audio', 'Audio')])
        widget = MultitrackWidget(model)
        widget.resize(600, 210)
        widget.show()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(120, 45))
        self.assertEqual(widget.selected, (0, clip.id))
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(120, 85))
        self.assertIsNone(widget.selected)
        self.assertEqual(widget.selected_track, 1)
        positions = []
        widget.seek.connect(positions.append)
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(110, 10))
        QTest.mouseMove(widget, QPoint(150, 10))
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(150, 10))
        self.assertEqual(positions[-1], 25)
        widget.close()

    def test_offset_allows_selecting_late_clips(self):
        clip = Clip('later.mp4', 2400, 300)
        widget = MultitrackWidget(Timeline(tracks=[Track('video', 'Video', [clip])]))
        widget.resize(600, 210)
        widget.set_offset(4600)
        widget.show()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(350, 45))
        self.assertEqual(widget.selected, (0, clip.id))
        self.assertEqual(widget.frame_for(widget.x_for(2475)), 2475)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(30, 45))
        self.assertIsNone(widget.selected)
        self.assertEqual(widget.selected_track, 0)
        widget.close()

if __name__ == '__main__': unittest.main()
