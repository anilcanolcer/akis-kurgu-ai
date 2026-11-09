import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.platform == 'win32':
    os.environ.setdefault('QT_MEDIA_BACKEND', 'windows')
import tempfile
import unittest
import wave
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from timeline_audio import TimelineAudio
from timeline_model import Timeline, Track, Clip

app = QApplication.instance() or QApplication([])


def wait_for(predicate, timeout_ms=5000):
    deadline = monotonic() + timeout_ms / 1000
    while monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(20)
    return False


class ActualAudioTests(unittest.TestCase):
    def test_player_seek_and_rate_on_actual_backend(self):
        output = QAudioOutput()
        player = QMediaPlayer()
        if not player.isAvailable():
            self.skipTest('Qt multimedia backend unavailable: ' + player.errorString())
        if not QMediaDevices.audioOutputs():
            self.skipTest('No audio output device is available')
        output.setMuted(True)
        player.setAudioOutput(output)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'silence.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 48000, 48000 * 6, 'NONE', 'not compressed'))
                stream.writeframes(b'\0\0' * 48000 * 6)
            player.setSource(QUrl.fromLocalFile(str(path)))
            self.assertTrue(wait_for(lambda: player.mediaStatus() in (
                QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)),
                player.errorString())
            player.setPosition(1000)
            player.setPlaybackRate(1.5)
            player.play()
            self.assertTrue(wait_for(lambda: player.position() >= 1000), player.errorString())
            QTest.qWait(1000)
            position = player.position()
            self.assertGreater(position, 1900, f'position did not advance at expected speed: {position}')
            self.assertLess(position, 3100, f'position advanced too far: {position}')
            player.pause()
            player.setSource(QUrl())

    def test_timeline_audio_follows_seek_and_speed_on_actual_backend(self):
        output, player = QAudioOutput(), QMediaPlayer()
        if not player.isAvailable():
            self.skipTest('Qt multimedia backend unavailable: ' + player.errorString())
        if not QMediaDevices.audioOutputs():
            self.skipTest('No audio output device is available')
        output.setMuted(True)
        player.setAudioOutput(output)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'silence.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 48000, 48000 * 6, 'NONE', 'not compressed'))
                stream.writeframes(b'\0\0' * 48000 * 6)
            timeline = Timeline(fps_num=30, tracks=[Track('audio', 'Audio', [Clip(str(path), 0, 180)])])
            audio = TimelineAudio(player)
            audio.sync(timeline, 30, 1.5, force=True)
            self.assertTrue(wait_for(lambda: player.playbackState() == QMediaPlayer.PlaybackState.PlayingState), player.errorString())
            start = monotonic()
            while monotonic() - start < 0.8:
                frame = 30 + round((monotonic() - start) * 45)
                audio.sync(timeline, frame, 1.5)
                QTest.qWait(50)
            expected_ms = 1000 + (monotonic() - start) * 1500
            self.assertLess(abs(player.position() - expected_ms), 300)
            audio.sync(timeline, 60, 0.75, force=True)
            self.assertTrue(wait_for(lambda: abs(player.position() - 2000) < 150), player.errorString())
            self.assertAlmostEqual(player.playbackRate(), 0.75, delta=0.01)
            audio.stop()
            player.setSource(QUrl())

if __name__ == '__main__': unittest.main()
