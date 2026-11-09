import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
import wave
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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

if __name__ == '__main__': unittest.main()
