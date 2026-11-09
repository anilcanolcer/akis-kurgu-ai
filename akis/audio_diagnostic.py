"""Opt-in diagnostic for the packaged Qt multimedia backend."""
import tempfile
import wave
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import QApplication


def _wait(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def diagnose():
    app = QApplication.instance() or QApplication([])
    player = QMediaPlayer()
    result = {'backend_available': player.isAvailable(), 'audio_output_count': len(QMediaDevices.audioOutputs())}
    if not player.isAvailable():
        result.update(status='unavailable', reason=player.errorString())
        return result
    if not QMediaDevices.audioOutputs():
        result.update(status='unavailable', reason='No audio output device')
        return result
    output = QAudioOutput()
    output.setMuted(True)
    player.setAudioOutput(output)
    with tempfile.TemporaryDirectory(prefix='akis_audio_check_') as folder:
        path = Path(folder) / 'silence.wav'
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((1, 2, 48000, 48000 * 6, 'NONE', 'not compressed'))
            stream.writeframes(b'\0\0' * 48000 * 6)
        player.setSource(QUrl.fromLocalFile(str(path)))
        deadline = monotonic() + 5
        while player.mediaStatus() not in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia) and monotonic() < deadline:
            _wait(25)
        if player.mediaStatus() not in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            result.update(status='failed', reason=player.errorString() or 'Media did not load')
            return result
        player.setPosition(1000)
        player.setPlaybackRate(1.5)
        player.play()
        _wait(1000)
        position = player.position()
        result.update(status='passed' if 1900 < position < 3100 else 'failed',
                      measured_position_ms=position, target_rate=1.5,
                      reported_rate=player.playbackRate(), reason=player.errorString())
        player.stop()
        player.setSource(QUrl())
    return result
