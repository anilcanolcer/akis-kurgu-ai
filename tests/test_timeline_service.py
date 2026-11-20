import unittest
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer
from akis.timeline_audio import TimelineAudio
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_service import (PlaybackClock, append_media_to_kind, audio_target, infer_media_kind,
                                   media_track_index, selected_clip, split_selected, validate_track_media)


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

    def test_rejects_incompatible_media_streams(self):
        from unittest.mock import Mock
        media = Mock()
        media.dimensions.side_effect = ValueError('no video')
        with self.assertRaisesRegex(ValueError, 'görüntü'):
            validate_track_media(media, 'video', 'sound.wav')
        media.has_audio.return_value = False
        with self.assertRaisesRegex(ValueError, 'ses'):
            validate_track_media(media, 'audio', 'silent.mp4')
        media.has_audio.return_value = True
        validate_track_media(media, 'audio', 'audio.wav')

    def test_media_import_routes_by_kind_and_creates_missing_tracks(self):
        from unittest.mock import Mock
        media = Mock()
        media.dimensions.return_value = (640, 360)
        self.assertEqual(infer_media_kind(media, 'clip.mp4'), 'video')
        media.dimensions.side_effect = ValueError('no video')
        media.has_audio.return_value = True
        self.assertEqual(infer_media_kind(media, 'music.flac'), 'audio')
        media.has_audio.return_value = False
        with self.assertRaisesRegex(ValueError, 'görüntü veya ses'):
            infer_media_kind(media, 'broken.dat')

        timeline = Timeline(fps_num=30, tracks=[Track('video', 'Video')])
        index, clip = append_media_to_kind(timeline, 'audio', 'music.flac', 2.0)
        self.assertEqual((index, timeline.tracks[index].kind, clip.source, clip.length), (1, 'audio', 'music.flac', 60))
        self.assertEqual(media_track_index(timeline, 'audio'), index)
        other = Timeline(tracks=[Track('audio', 'Music 1'), Track('audio', 'Music 2')])
        self.assertEqual(media_track_index(other, 'audio', preferred_track=1), 1)

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

    def test_ready_player_resumes_without_another_load_notification(self):
        player = FakePlayer()
        audio = TimelineAudio(player)
        audio.sync(self.timeline, 25, 2)
        player.status = QMediaPlayer.MediaStatus.LoadedMedia
        audio.sync(self.timeline, 28, 2)
        self.assertEqual(player.offset, 600)
        self.assertIsNone(audio.pending)
        self.assertEqual(player.state, QMediaPlayer.PlaybackState.PlayingState)

    def test_async_audio_load_and_drift_correction(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        player = FakePlayer()
        audio = TimelineAudio(player)
        audio.sync(self.timeline, 25, 2)
        self.assertFalse(any(call[0] == 'position' for call in player.calls))
        audio.sync(self.timeline, 28, 2)
        player.status = QMediaPlayer.MediaStatus.LoadedMedia
        player.mediaStatusChanged.emit(player.status)
        QCoreApplication.processEvents()
        self.assertEqual(player.offset, 600)
        self.assertEqual(player.rate, 2)
        audio.sync(self.timeline, 34, .5)
        self.assertEqual(player.offset, 800)
        self.assertEqual(player.rate, .5)
        audio.stop()
        self.assertEqual(player.state, QMediaPlayer.PlaybackState.PausedState)

if __name__ == '__main__': unittest.main()
