"""Zoomable preview surface and smooth proxy playback for the timeline."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from akis.render_worker import TimelineRenderWorker
from akis.theme import color

MAX_ZOOM = 8.0


class PreviewView(QWidget):
    """Shows the current frame. Ctrl+wheel zooms at the cursor, dragging pans, double-click edits."""
    double_clicked = Signal(float, float)  # position as fractions of the picture
    zoom_changed = Signal(float)
    resized = Signal()

    def __init__(self, placeholder=''):
        super().__init__()
        self.placeholder = placeholder
        self.image = None
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self._drag = None

    def setPixmap(self, pixmap):
        self.set_image(pixmap)

    def set_image(self, image):
        """Accepts a QPixmap or QImage; an empty one restores the placeholder."""
        self.image = None if image is None or image.isNull() else image
        self.update()

    def picture_rect(self):
        if self.image is None:
            return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height()) * self.zoom
        width, height = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - width) / 2 + self.pan.x(), (self.height() - height) / 2 + self.pan.y(), width, height)

    def _clamp_pan(self):
        if self.image is None or self.zoom <= 1.0:
            self.pan = QPointF(0, 0)
            return
        scale = min(self.width() / self.image.width(), self.height() / self.image.height()) * self.zoom
        limit_x = max(0.0, (self.image.width() * scale - self.width()) / 2)
        limit_y = max(0.0, (self.image.height() * scale - self.height()) / 2)
        self.pan = QPointF(max(-limit_x, min(limit_x, self.pan.x())), max(-limit_y, min(limit_y, self.pan.y())))

    def set_zoom(self, zoom, anchor=None):
        zoom = max(1.0, min(MAX_ZOOM, zoom))
        if self.image is None or zoom == self.zoom:
            return
        before = self.picture_rect()
        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        # Keep the picture point under the cursor fixed while the scale changes.
        fx = (anchor.x() - before.x()) / before.width()
        fy = (anchor.y() - before.y()) / before.height()
        self.zoom = zoom
        after = self.picture_rect()
        self.pan += QPointF(anchor.x() - (after.x() + fx * after.width()), anchor.y() - (after.y() + fy * after.height()))
        self._clamp_pan()
        self.zoom_changed.emit(self.zoom)
        self.update()

    def reset_zoom(self):
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and self.image is not None:
            self.set_zoom(self.zoom * (1.2 if event.angleDelta().y() > 0 else 1 / 1.2), event.position())
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.reset_zoom()
        elif event.button() == Qt.MouseButton.LeftButton and self.zoom > 1.0:
            self._drag = (event.position(), QPointF(self.pan))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag:
            start, pan = self._drag
            self.pan = pan + (event.position() - start)
            self._clamp_pan()
            self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event):
        rect = self.picture_rect()
        if event.button() == Qt.MouseButton.LeftButton and rect.contains(event.position()):
            self.double_clicked.emit((event.position().x() - rect.x()) / rect.width(),
                                     (event.position().y() - rect.y()) / rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._clamp_pan()
        self.resized.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), color('video_bg'))
        if self.image is None:
            painter.setPen(color('video_text'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = self.picture_rect()
        if isinstance(self.image, QPixmap):
            painter.drawPixmap(target, self.image, QRectF(self.image.rect()))
        else:
            painter.drawImage(target, self.image)
        if self.zoom > 1.0:
            label = f'%{round(self.zoom * 100)}  ·  orta tuş: sıfırla'
            box = QRectF(10, 10, painter.fontMetrics().horizontalAdvance(label) + 16, 24)
            painter.fillRect(box, QColor(0, 0, 0, 170))
            painter.setPen(color('video_caption'))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)


def timeline_signature(timeline, size, adjustments):
    """Changes whenever the rendered picture or sound would change."""
    payload = json.dumps([timeline.to_dict(), list(size), sorted(adjustments.items())], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


class ProxyPlayback(QObject):
    """Plays a pre-rendered low-resolution copy of the timeline so playback is smooth and all audio is mixed.

    Stills from FFmpeg stay the source of truth while paused; this only takes over between play and pause.
    """
    image_ready = Signal(QImage)
    frame_changed = Signal(int)
    ready = Signal()
    ended = Signal()
    failed = Signal(str)

    def __init__(self, executable, parent=None, worker_factory=TimelineRenderWorker):
        super().__init__(parent)
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
        self.executable = executable
        self.worker_factory = worker_factory
        self.directory = tempfile.TemporaryDirectory(prefix='akis_proxy_')
        self.counter = 0
        self.signature = None       # what the finished file shows
        self.path = None
        self.rendering = None       # signature being rendered
        self.worker = None
        self.pending = None         # newest request waiting for a cancelled render to stop
        self.fps = 30.0
        self.closing = False
        self._start_at = None
        self.audio = QAudioOutput(self)
        self.sink = QVideoSink(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._frame)
        self.player.positionChanged.connect(lambda ms: self.playing and self.frame_changed.emit(round(ms * self.fps / 1000)))
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(lambda error, message: self.failed.emit(message or str(error)))
        self._media = QMediaPlayer

    @staticmethod
    def proxy_size(size, limit=854):
        width, height = size
        scale = min(1.0, limit / max(width, height))
        return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)

    @property
    def available(self):
        return self.player.isAvailable()

    @property
    def playing(self):
        return self.player.playbackState() == self._media.PlaybackState.PlayingState

    def is_ready(self, signature):
        return self.signature == signature and self.path is not None

    def prepare(self, timeline, size, adjustments, signature):
        """Render the proxy for this signature unless it exists or is already on its way.

        A render still running for an outdated signature is cancelled and this one starts as soon
        as it has stopped; `ready` follows once the newest requested signature is rendered.
        """
        if self.closing or self.rendering == signature:  # rendering is None once cancelled
            return
        if self.is_ready(signature):
            self.pending = None
            if self.worker is not None:
                self._cancel_worker()
            return
        if self.worker is not None:
            # Snapshot now: the caller keeps editing the live timeline, the signature is for this state.
            self.pending = (type(timeline).from_dict(timeline.to_dict()), size, dict(adjustments), signature)
            self._cancel_worker()
            return
        self._start(timeline, size, adjustments, signature)

    def _cancel_worker(self):
        self.rendering = None  # whatever it still produces is outdated
        cancel = getattr(self.worker, 'cancel', None)
        if cancel is not None:
            cancel()

    def _start(self, timeline, size, adjustments, signature):
        self.counter += 1
        output = str(Path(self.directory.name) / f'proxy_{self.counter}.mp4')
        executable = self.executable() if callable(self.executable) else self.executable
        self.fps = timeline.fps_num / timeline.fps_den
        self.rendering = signature
        self.worker = self.worker_factory(timeline, output, self.proxy_size(size), executable,
                                          adjustments=dict(adjustments, speed=1.0, fast=True))
        self.worker.completed.connect(self._rendered)
        self.worker.failed.connect(self._render_failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _rendered(self, path):
        if self.rendering is None:  # cancelled as outdated but finished anyway
            self._discard(path)
            return
        previous = self.path
        self.signature, self.path = self.rendering, path
        if previous and previous != path and self.player.source() != QUrl.fromLocalFile(previous):
            self._discard(previous)

    @staticmethod
    def _discard(path):
        """Each edit renders a fresh copy; remove outdated ones so a long session does not fill the disk."""
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:  # still open by the media backend; the folder is removed on close
            pass

    def _render_failed(self, message):
        self.rendering = None
        self.failed.emit(message)

    def _worker_finished(self):
        self.worker = None
        self.rendering = None
        if self.closing:
            return
        if self.pending is not None:
            request, self.pending = self.pending, None
            try:
                self._start(*request)
            except Exception as exc:
                self.failed.emit(str(exc))
            return
        if self.path:
            self.ready.emit()

    def play(self, frame, speed, volume):
        self.audio.setVolume(volume)
        self.player.setPlaybackRate(speed)
        position = round(frame * 1000 / self.fps)
        if self.player.source() != QUrl.fromLocalFile(self.path):
            outdated = self.player.source().toLocalFile()
            self._start_at = position  # Windows media loads asynchronously; seek once it is loaded
            self.player.setSource(QUrl.fromLocalFile(self.path))
            if outdated:
                self._discard(outdated)
        else:
            self.player.setPosition(position)
            self.player.play()

    def seek(self, frame):
        self.player.setPosition(round(frame * 1000 / self.fps))

    def set_speed(self, speed):
        self.player.setPlaybackRate(speed)

    def set_volume(self, volume):
        self.audio.setVolume(volume)

    def pause(self):
        self._start_at = None
        self.player.pause()

    def _status(self, status):
        if status in (self._media.MediaStatus.LoadedMedia, self._media.MediaStatus.BufferedMedia) and self._start_at is not None:
            position, self._start_at = self._start_at, None
            self.player.setPosition(position)
            self.player.play()
        elif status == self._media.MediaStatus.EndOfMedia:
            self.ended.emit()

    def _frame(self, frame):
        if self.playing and frame.isValid():
            self.image_ready.emit(frame.toImage())

    def close(self):
        self.closing = True
        self.player.stop()
        self.player.setSource(QUrl())  # release the file before the folder is removed
        self.pending = None
        if self.worker is not None:
            self._cancel_worker()  # closing must not wait for a whole proxy render
            self.worker.wait()
            self.worker = None
        try:
            self.directory.cleanup()
        except OSError:
            pass
