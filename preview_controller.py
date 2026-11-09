"""Coalesce timeline preview requests and manage FFmpeg preview workers."""
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, Signal
from render_worker import TimelineRenderWorker


class PreviewController(QObject):
    frame_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, executable, parent=None, worker_factory=TimelineRenderWorker):
        super().__init__(parent)
        self.executable = executable
        self.worker_factory = worker_factory
        self.directory = tempfile.TemporaryDirectory(prefix='akis_preview_')
        self.worker = None
        self.pending = None
        self.closing = False

    @staticmethod
    def preview_size(size):
        width, height = size
        scale = min(1.0, 480 / max(width, height))
        return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)

    def request(self, timeline, frame, size, adjustments):
        if self.closing:
            return
        request = (timeline, frame, size, dict(adjustments))
        if self.worker is not None:
            self.pending = request
            return
        try:
            self._start(request)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _start(self, request):
        timeline, frame, size, adjustments = request
        output = str(Path(self.directory.name) / 'frame.png')
        self.worker = self.worker_factory(timeline, output, self.preview_size(size),
                                          self.executable() if callable(self.executable) else self.executable, frame, adjustments)
        self.worker.completed.connect(self.frame_ready.emit)
        self.worker.failed.connect(self.failed.emit)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        self.worker = None
        if not self.closing and self.pending is not None:
            request, self.pending = self.pending, None
            try:
                self._start(request)
            except Exception as exc:
                self.failed.emit(str(exc))

    def close(self):
        self.closing = True
        self.pending = None
        if self.worker is not None:
            self.worker.wait()
            self.worker = None
        self.directory.cleanup()
