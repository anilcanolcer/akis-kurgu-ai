"""Qt multimedia adapter for simple timeline audio playback."""
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer

from timeline_service import audio_target


class TimelineAudio(QObject):
    failed = Signal(str)

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.source = None
        self.pending = None
        self.active = False
        self.unavailable_reported = False
        player.mediaStatusChanged.connect(self._status_changed)
        if hasattr(player, "errorOccurred"):
            player.errorOccurred.connect(self._error)

    def stop(self):
        self.active = False
        self.pending = None
        self.player.pause()

    def sync(self, timeline, frame, speed, force=False):
        if hasattr(self.player, "isAvailable") and not self.player.isAvailable():
            if not self.unavailable_reported:
                self.failed.emit("Ses önizlemesi kullanılamıyor: Qt medya arka ucu yüklenemedi.")
                self.unavailable_reported = True
            return
        self.unavailable_reported = False
        self.active = True
        target = audio_target(timeline, frame, speed)
        if target is None:
            self.pending = None
            self.player.pause()
            self.source = None
            return
        source, position, rate = target
        self.pending = position
        self.player.setPlaybackRate(rate)
        if source != self.source:
            self.source = source
            self.player.setSource(QUrl.fromLocalFile(source))
            # Windows media loads asynchronously. Seek only after LoadedMedia.
            return
        if self.player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.NoMedia):
            return
        if force or abs(self.player.position() - position) > 120:
            self.player.setPosition(position)
        self.pending = None
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.player.play()

    def _status_changed(self, status):
        if (self.active and self.pending is not None and status in
                (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)):
            self.player.setPosition(self.pending)
            self.pending = None
            self.player.play()

    def _error(self, error, message):
        if self.active and error != QMediaPlayer.Error.NoError:
            self.failed.emit(f"Ses önizlemesi: {message or str(error)}")
