"""Regression coverage for mixed audio, layered captions and reversible trim gestures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import Mock

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from akis import word_captions
from akis.caption_service import caption_track
from akis.multitrack_widget import MultitrackWidget
from akis.timeline_audio import TimelineAudio
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_service import canvas_size
from tests.test_mixed_preview_audio import FakePlayer, FakeOutput

app = QApplication.instance() or QApplication([])


class EditorRegressionTests(unittest.TestCase):
    def test_identical_source_positions_keep_both_audio_layers(self):
        timeline = Timeline(tracks=[Track('audio', 'A', [Clip('same.wav', 0, 30)]),
                                    Track('audio', 'B', [Clip('same.wav', 0, 30, volume=.4)])])
        extra, output = FakePlayer(), FakeOutput()
        audio = TimelineAudio(FakePlayer(), player_factory=lambda: (extra, output))
        audio.sync(timeline, 5, 1, master=.5)
        self.assertEqual(list(audio.extra), [1])
        self.assertEqual(extra.source, 'same.wav')
        self.assertAlmostEqual(output.volume, .2)
        audio.stop()

    def test_word_captions_use_all_unmuted_video_tracks_in_time_order(self):
        timeline = Timeline(fps_num=30, tracks=[
            Track('video', 'Later', [Clip('speech.mp4', 60, 30)]),
            Track('video', 'Earlier', [Clip('speech.mp4', 0, 30)]),
            Track('video', 'Muted', [Clip('speech.mp4', 120, 30)], muted=True)])
        segment = {'start': 0, 'end': 1, 'text': 'Hello',
                   'words': [{'start': 0, 'end': 1, 'text': 'Hello'}]}
        self.assertEqual(caption_track(timeline, 'speech.mp4', [segment], 'vurgu'), 2)
        self.assertEqual([(c.start, c.end) for c in timeline.tracks[-1].clips], [(0, 30), (60, 90)])

    def test_source_ratio_uses_overlay_when_base_video_empty(self):
        timeline = Timeline(tracks=[Track('video', 'Video'),
                                    Track('overlay', 'Overlay', [Clip('picture.mp4', 0, 150)])])
        media = Mock()
        media.dimensions.return_value = (1600, 900)
        self.assertEqual(canvas_size('Source ratio', timeline, media), (1600, 900))
        media.dimensions.assert_called_once_with('picture.mp4')

    def test_left_trim_backtracking_preserves_words_and_keyframes(self):
        clip = Clip('', 50, 30, text='a b c',
                    style={'look': 'vurgu', 'words': [[0, 8, 'a'], [10, 18, 'b'], [20, 28, 'c']]},
                    keyframes={'opacity': [{'frame': 12, 'value': .5}, {'frame': 22, 'value': 1}]})
        widget = MultitrackWidget(Timeline(tracks=[Track('text', 'Captions', [clip])]))
        widget.resize(600, 210)
        widget.show()
        self.addCleanup(widget.close)
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(203, 45))
        QTest.mouseMove(widget, QPoint(233, 45))
        QTest.mouseMove(widget, QPoint(223, 45))
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(223, 45))
        self.assertEqual((clip.start, clip.length), (60, 20))
        # The word trimmed off the start keeps its time (dragging back brings it back) and is not drawn.
        self.assertEqual(clip.style['words'], [[-10, -2, 'a'], [0, 8, 'b'], [10, 18, 'c']])
        self.assertEqual([w[2] for w in word_captions.visible(clip)[0]], ['b', 'c'])
        self.assertEqual(clip.keyframes['opacity'], [{'frame': 2, 'value': .5}, {'frame': 12, 'value': 1}])


if __name__ == '__main__':
    unittest.main()
