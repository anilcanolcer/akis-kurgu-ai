"""Frame-by-frame playback plays every sound at the moment, not only one."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from akis.timeline_audio import MAX_EXTRA, TimelineAudio
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_service import audio_targets

app = QApplication.instance() or QApplication([])


class FakePlayer(QObject):
    mediaStatusChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.status = QMediaPlayer.MediaStatus.NoMedia
        self.state = QMediaPlayer.PlaybackState.StoppedState
        self.offset, self.rate, self.source = 0, 1, None

    def setSource(self, source):
        self.source = source.toLocalFile()
        self.status = QMediaPlayer.MediaStatus.LoadingMedia

    def load(self):
        self.status = QMediaPlayer.MediaStatus.LoadedMedia
        self.mediaStatusChanged.emit(self.status)

    def setPosition(self, value): self.offset = value
    def setPlaybackRate(self, value): self.rate = value
    def mediaStatus(self): return self.status
    def playbackState(self): return self.state
    def position(self): return self.offset
    def play(self): self.state = QMediaPlayer.PlaybackState.PlayingState
    def pause(self): self.state = QMediaPlayer.PlaybackState.PausedState


class FakeOutput:
    def __init__(self):
        self.volume = None

    def setVolume(self, value):
        self.volume = value


def timeline():
    return Timeline(fps_num=30, tracks=[
        Track('video', 'Video', [Clip('talk.mp4', 0, 300, source_in=60, volume=0.8)]),
        Track('audio', 'Müzik', [Clip('music.mp3', 30, 300, volume=0.5)]),
        Track('audio', 'Efekt', [Clip('whoosh.wav', 90, 15)]),
        Track('text', 'Yazı', [Clip('', 0, 60, text='Merhaba')])])


class TargetTests(unittest.TestCase):
    def test_every_sound_at_the_moment_in_track_order(self):
        found = audio_targets(timeline(), 95, 1.0)
        self.assertEqual([(t.track_index, t.source, t.position, t.volume) for t in found],
                         [(0, 'talk.mp4', 5167, 0.8), (1, 'music.mp3', 2167, 0.5), (2, 'whoosh.wav', 167, 1.0)])

    def test_silent_and_muted_clips_are_left_out(self):
        cut = timeline()
        cut.tracks[0].clips[0].volume = 0
        cut.tracks[1].muted = True
        self.assertEqual([t.source for t in audio_targets(cut, 95, 1.0)], ['whoosh.wav'])
        self.assertEqual(audio_targets(cut, 10, 1.0), [])


class MixTests(unittest.TestCase):
    def make(self):
        self.made = []

        def factory():
            player, output = FakePlayer(), FakeOutput()
            self.made.append((player, output))
            return player, output
        self.main = FakePlayer()
        return TimelineAudio(self.main, player_factory=factory)

    def test_main_sound_is_the_music_and_the_voice_plays_alongside(self):
        audio = self.make()
        audio.sync(timeline(), 40, 1.0, master=0.5)
        self.assertEqual(self.main.source, 'music.mp3')          # the main player is unchanged in behaviour
        self.assertEqual([(p.source, o.volume) for p, o in self.made], [('talk.mp4', 0.4)])
        voice, _ = self.made[0]
        voice.load()
        self.assertEqual(voice.offset, round((60 + 40) * 1000 / 30))
        self.assertEqual(voice.state, QMediaPlayer.PlaybackState.PlayingState)

    def test_players_are_reused_and_follow_what_starts_and_stops(self):
        audio = self.make()
        audio.sync(timeline(), 40, 1.0, master=1.0)
        audio.sync(timeline(), 95, 1.0, master=1.0)              # the whoosh starts
        self.assertEqual(len(self.made), 2)
        audio.sync(timeline(), 200, 1.0, master=1.0)             # the whoosh has ended: its player is spare
        self.assertEqual(len(audio.spare), 1)
        whoosh, _ = audio.spare[0]
        self.assertEqual(whoosh.player.state, QMediaPlayer.PlaybackState.PausedState)
        audio.sync(timeline(), 95, 1.0, master=1.0)              # back again: no new player
        self.assertEqual(len(self.made), 2)

    def test_stop_pauses_every_player(self):
        audio = self.make()
        audio.sync(timeline(), 95, 1.0, master=1.0)
        for player, _ in self.made:
            player.load()
        audio.stop()
        self.assertTrue(all(p.state == QMediaPlayer.PlaybackState.PausedState for p, _ in self.made))
        self.assertEqual(self.main.state, QMediaPlayer.PlaybackState.PausedState)

    def test_without_a_factory_only_the_main_sound_plays(self):
        main = FakePlayer()
        audio = TimelineAudio(main)
        audio.sync(timeline(), 95, 1.0, master=1.0)
        self.assertEqual(main.source, 'music.mp3')
        self.assertEqual(audio.extra, {})

    def test_number_of_extra_players_is_bounded(self):
        many = Timeline(fps_num=30, tracks=[Track('audio', f'A{i}', [Clip(f'{i}.wav', 0, 30)]) for i in range(8)])
        audio = self.make()
        audio.sync(many, 5, 1.0, master=1.0)
        self.assertEqual(len(self.made), MAX_EXTRA)


class WindowTests(unittest.TestCase):
    def test_window_gives_each_extra_player_its_own_output(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from main import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        window = MainWindow()
        player, output = window.new_preview_player()
        self.assertIs(player.audioOutput(), output)
        self.assertIsNot(output, window.preview_audio_output)
        self.assertIsNotNone(window.timeline_audio.player_factory)
        window._close_confirmed = True
        window.close()


if __name__ == '__main__':
    unittest.main()
