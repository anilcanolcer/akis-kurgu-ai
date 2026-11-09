import unittest
from unittest.mock import Mock

from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer
from timeline_audio import TimelineAudio
from timeline_model import Clip, Timeline, Track
from timeline_service import PlaybackClock, audio_target, selected_clip, split_selected


class FakePlayer(QObject):
    mediaStatusChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.status = QMediaPlayer.MediaStatus.NoMedia
        self.state = QMediaPlayer.PlaybackState.StoppedState
        self.offset = 0
        self.rate = 1
        self.calls = []

    def setSource(self, source):
        self.calls.append(('source', source.toLocalFile()))
        self.status = QMediaPlayer.MediaStatus.LoadingMedia

    def setPosition(self, value):
        self.calls.append(('position', value))
        self.offset = value

    def setPlaybackRate(self, value):
        self.rate = value

    def mediaStatus(self): return self.status
    def playbackState(self): return self.state
    def position(self): return self.offset
    def play(self): self.state = QMediaPlayer.PlaybackState.PlayingState
    def pause(self): self.state = QMediaPlayer.PlaybackState.PausedState


class TimelineServiceTests(unittest.TestCase):
    def setUp(self):
        self.clip = Clip('video.mp4', 10, 60, source_in=30)
        self.audio = Clip('audio.wav', 20, 30, source_in=10)
        self.timeline = Timeline(fps_num=30, tracks=[Track('video', 'Video', [self.clip]), Track('audio', 'Audio', [self.audio])])

    def test_selection_and_split(self):
        selection = (0, self.clip.id)
        self.assertIs(selected_clip(self.timeline, selection)[1], self.clip)
        right = split_selected(self.timeline, selection, 25)
        self.assertEqual((self.clip.length, right.start, right.source_in), (15, 25, 45))
        self.assertIsNone(selected_clip(self.timeline, (8, 'missing'))[1])
        with self.assertRaises(ValueError): split_selected(self.timeline, None, 25)

    def test_audio_mapping_prefers_audio_and_preserves_source_time(self):
        self.assertEqual(audio_target(self.timeline, 25, 2), ('audio.wav', 500, 2))
        self.assertEqual(audio_target(self.timeline, 15, .5), ('video.mp4', 1167, .5))
        self.assertIsNone(audio_target(self.timeline, 0, 1))

    def test_monotonic_clock_speed_changes_and_seek(self):
        now = [10.0]
        clock = PlaybackClock(lambda: now[0])
        clock.start(5, 1)
        now[0] += 1
        self.assertEqual(clock.position(self.timeline), 35)
        clock.set_speed(self.timeline, 2)
        now[0] += .5
        self.assertEqual(clock.position(self.timeline), 65)
        clock.seek(20)
        now[0] += .25
        self.assertEqual(clock.position(self.timeline), 35)

    def test_unavailable_backend_is_reported_once(self):
        player = FakePlayer()
        player.isAvailable = lambda: False
        audio = TimelineAudio(player)
        errors = []
        audio.failed.connect(errors.append)
        audio.sync(self.timeline, 25, 1)
        audio.sync(self.timeline, 26, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn('arka ucu', errors[0])
        self.assertEqual(player.calls, [])

    def test_async_audio_load_and_drift_correction(self):
        player = FakePlayer()
        audio = TimelineAudio(player)
        audio.sync(self.timeline, 25, 2)
        self.assertFalse(any(call[0] == 'position' for call in player.calls))
        audio.sync(self.timeline, 28, 2)
        player.status = QMediaPlayer.MediaStatus.LoadedMedia
        player.mediaStatusChanged.emit(player.status)
        self.assertEqual(player.offset, 600)
        self.assertEqual(player.rate, 2)
        audio.sync(self.timeline, 34, .5)
        self.assertEqual(player.offset, 800)
        self.assertEqual(player.rate, .5)
        audio.stop()
        self.assertEqual(player.state, QMediaPlayer.PlaybackState.PausedState)

if __name__ == '__main__': unittest.main()
