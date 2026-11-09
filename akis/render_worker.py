"""Background FFmpeg render worker."""
from PySide6.QtCore import QThread, Signal
from akis.media_service import MediaService
from akis.timeline_model import Timeline
from akis.timeline_render import TimelineRenderer


class TimelineRenderWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, timeline, output, size, executable, frame=None, adjustments=None):
        super().__init__()
        self.executable = executable
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.output, self.size, self.frame = output, size, frame
        self.adjustments = adjustments or {}

    def run(self):
        try:
            renderer = TimelineRenderer(MediaService(self.executable), self.size, **self.adjustments)
            if self.frame is None:
                renderer.export(self.timeline, self.output)
            else:
                renderer.preview(self.timeline, self.frame, self.output)
            self.completed.emit(self.output)
        except Exception as exc:
            self.failed.emit(str(exc))


