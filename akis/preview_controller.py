"""Coalesce timeline preview requests and manage FFmpeg preview workers."""
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, Signal
from akis.render_worker import TimelineRenderWorker


def _remove(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


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
        self.counter = 0
        self.shown = None  # last frame handed out; removed once a newer one replaces it

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
        # A fresh name per frame: QPixmap(path) caches by path + whole-second mtime + size, so
        # reusing one name could show an older frame rendered within the same second.
        self.counter += 1
        output = str(Path(self.directory.name) / f'frame_{self.counter}.png')
        self.worker = self.worker_factory(timeline, output, self.preview_size(size),
                                          self.executable() if callable(self.executable) else self.executable, frame, adjustments)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self.failed.emit)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _completed(self, path):
        previous, self.shown = self.shown, path
        self.frame_ready.emit(path)
        if previous and previous != path:
            _remove(previous)

    def _finished(self):
        worker, self.worker = self.worker, None
        if worker is not None and worker.output != self.shown:
            _remove(worker.output)  # failed or cancelled: drop any partial file
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
            cancel = getattr(self.worker, 'cancel', None)
            if cancel is not None:
                cancel()  # do not wait for a render nobody will see
            self.worker.wait()
            self.worker = None
        self.directory.cleanup()
