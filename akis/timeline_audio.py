"""Qt multimedia adapter for timeline audio when the pre-mixed playback copy is not available.

One player follows the main sound (an audio track, else the video's own sound), as before. Given a
`player_factory`, more players follow the other sounding layers at the same moment (the video's voice
under the music, a second music track…), each at its own clip volume, so what is heard matches the
export instead of only one of the sources.
"""
from time import monotonic

from PySide6.QtCore import QObject, QUrl, Qt, Signal
from PySide6.QtMultimedia import QMediaPlayer

from akis.timeline_service import audio_target, audio_targets
from akis.frame_plan import audio_at

MAX_EXTRA = 3   # other sounds played at once besides the main one


class _Lane:
    """One player following one source: loads it, seeks after loading, keeps its position close."""

    def __init__(self, player, owner):
        self.player = player
        self.owner = owner
        self.source = None
        self.pending = None
        self.rate = None
        self.last_seek = float("-inf")
        player.mediaStatusChanged.connect(self._status_changed, Qt.ConnectionType.QueuedConnection)
        if hasattr(player, "errorOccurred"):
            player.errorOccurred.connect(self._error)

    def stop(self):
        self.pending = None
        self.player.pause()

    def release(self):
        self.stop()
        self.source = None

    def follow(self, source, position, rate, force):
        rate_changed = rate != self.rate
        self.rate = rate
        if source != self.source:
            self.source = source
            self.pending = position
            self.player.setSource(QUrl.fromLocalFile(source))
            # Windows media loads asynchronously. Seek only after LoadedMedia.
            return
        if self.pending is not None:
            # Reusing an already-loaded URL need not emit another mediaStatusChanged.
            self.pending = position
            self._status_changed(self.player.mediaStatus())
            return
        if self.player.mediaStatus() in (
                QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.NoMedia):
            self.pending = position
            return
        # The backend can briefly report a stale position while a seek is in flight.
        if force or rate_changed or (monotonic() - self.last_seek >= 0.25 and abs(self.player.position() - position) > 120):
            self.last_seek = monotonic()
            self.player.setPosition(position)
        if rate_changed:
            self.player.setPlaybackRate(rate)
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.player.play()

    def _status_changed(self, status):
        if (status == self.player.mediaStatus() and self.owner.active and self.pending is not None and status in
                (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)):
            position = self.pending
            self.pending = None
            self.last_seek = monotonic()
            self.player.setPosition(position)
            self.player.setPlaybackRate(self.rate)
            self.player.play()

    def _error(self, error, message):
        if self.owner.active and error != QMediaPlayer.Error.NoError:
            self.owner.failed.emit(f"Ses önizlemesi: {message or str(error)}")


class TimelineAudio(QObject):
    failed = Signal(str)

    def __init__(self, player, parent=None, player_factory=None):
        """player_factory() -> (player, audio output), for the extra sounds; without one only the main
        sound is played."""
        super().__init__(parent)
        self.player = player
        self.player_factory = player_factory
        self.active = False
        self.unavailable_reported = False
        self.main = _Lane(player, self)
        self.extra = {}         # track index -> (_Lane, audio output)
        self.spare = []         # (_Lane, audio output) not following anything now

    # Kept for callers that look at the main player's state.
    @property
    def source(self):
        return self.main.source

    @property
    def pending(self):
        return self.main.pending

    @property
    def rate(self):
        return self.main.rate

    def stop(self):
        self.active = False
        self.main.stop()
        for lane, _ in list(self.extra.values()) + self.spare:
            lane.stop()

    def sync(self, timeline, frame, speed, force=False, master=None):
        """Follow the timeline at `frame`. `master` (0..1) sets the extra players' volume as
        master × clip volume; the main player's volume is the caller's, as before."""
        if hasattr(self.player, "isAvailable") and not self.player.isAvailable():
            if not self.unavailable_reported:
                self.failed.emit("Ses önizlemesi kullanılamıyor: Qt medya arka ucu yüklenemedi.")
                self.unavailable_reported = True
            return
        self.unavailable_reported = False
        self.active = True
        target = audio_target(timeline, frame, speed)
        if target is None:
            self.main.pending = None
            self.player.pause()
            self.main.source = None
        else:
            self.main.follow(*target, force)
        self._sync_extra(timeline, frame, speed, force, master, target)

    def _sync_extra(self, timeline, frame, speed, force, master, target):
        wanted = {}
        if self.player_factory is not None and target is not None:
            primary = audio_at(timeline, frame)
            others = [item for item in audio_targets(timeline, frame, speed)
                      if primary is None or item.track_index != primary.track_index]
            wanted = {item.track_index: item for item in others[:MAX_EXTRA]}
        for track_index in [index for index in self.extra if index not in wanted]:
            lane, output = self.extra.pop(track_index)
            lane.release()
            self.spare.append((lane, output))
        for track_index, item in wanted.items():
            if track_index not in self.extra:
                self.extra[track_index] = self.spare.pop() if self.spare else self._new_lane()
            lane, output = self.extra[track_index]
            if master is not None and output is not None:
                output.setVolume(max(0.0, min(1.0, master * item.volume)))
            lane.follow(item.source, item.position, item.rate, force)

    def _new_lane(self):
        player, output = self.player_factory()
        return _Lane(player, self), output
