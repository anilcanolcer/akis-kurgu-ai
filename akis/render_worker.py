"""Background FFmpeg render worker."""
from PySide6.QtCore import QThread, Signal
from akis.media_service import MediaService, RenderCancelled
from akis.timeline_model import Timeline
from akis.timeline_render import TimelineRenderer


class TimelineRenderWorker(QThread):
    """Exactly one of completed / failed / cancelled is emitted per run, then QThread.finished."""
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)  # whole percent of an export, each value once

    def __init__(self, timeline, output, size, executable, frame=None, adjustments=None):
        super().__init__()
        self.executable = executable
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.output, self.size, self.frame = output, size, frame
        self.adjustments = dict(adjustments or {})
        # The playback proxy passes a folder of stored pieces (akis.chunk_preview): only changed pieces
        # are drawn again.
        self.pieces = self.adjustments.pop('pieces', None)
        # The playback proxy is background work: keep it from starving still previews.
        self.media = MediaService(executable, low_priority=bool(self.adjustments.get('fast')))

    def cancel(self):
        """Stops the render from any thread; returns at once. The export target is left untouched."""
        self.media.cancel()

    def _report(self, fraction):
        percent = int(fraction * 100)
        if percent != getattr(self, '_percent', None):
            self._percent = percent
            self.progress.emit(percent)

    def run(self):
        try:
            renderer = TimelineRenderer(self.media, self.size, **self.adjustments)
            if self.frame is None and self.pieces:
                renderer.export_pieces(self.timeline, self.output, self.pieces, on_progress=self._report)
            elif self.frame is None:
                renderer.export(self.timeline, self.output, on_progress=self._report)
            else:
                renderer.preview(self.timeline, self.frame, self.output)
            self.completed.emit(self.output)
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.media.cancelled:  # e.g. a probe killed mid-way reports as unreadable media
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
