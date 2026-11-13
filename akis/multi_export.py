"""Export one edit as three files in one go: vertical, square and landscape.

Each file is a normal export of the same timeline on another canvas, written one after the other. Clips
keep their own framing: a fitted clip gets bars on a canvas of another shape, a filled one is cropped.
"""
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from akis.media_service import MediaService, RenderCancelled
from akis.timeline_model import Timeline
from akis.timeline_render import TimelineRenderer

# (suffix added to the file name, name shown to the user, canvas)
FORMATS = (('dikey', 'Dikey 9:16', (1080, 1920)), ('kare', 'Kare 1:1', (1080, 1080)), ('yatay', 'Yatay 16:9', (1920, 1080)))


def targets(chosen):
    """[(shown name, canvas, path)] for the file name the user chose: video.mp4 -> video_dikey.mp4, …"""
    base = Path(chosen)
    stem = base.stem if base.suffix.lower() == '.mp4' else base.name
    for suffix, _, _ in FORMATS:  # choosing an earlier result again must not pile suffixes up
        if stem.endswith('_' + suffix):
            stem = stem[:-len(suffix) - 1]
    return [(name, canvas, str(base.with_name(f'{stem}_{suffix}.mp4'))) for suffix, name, canvas in FORMATS]


class MultiExportWorker(QThread):
    """Same signals as TimelineRenderWorker; completed carries the paths joined by newlines."""
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)

    def __init__(self, timeline, outputs, executable, adjustments=None):
        super().__init__()
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.outputs = list(outputs)            # [(shown name, canvas, path)]
        self.adjustments = dict(adjustments or {})
        self.media = MediaService(executable)
        self._percent = None

    def cancel(self):
        self.media.cancel()

    def _report(self, index, fraction):
        percent = int((index + fraction) / len(self.outputs) * 100)
        if percent != self._percent:
            self._percent = percent
            self.progress.emit(percent)

    def run(self):
        try:
            for index, (_, canvas, path) in enumerate(self.outputs):
                renderer = TimelineRenderer(self.media, canvas, **self.adjustments)
                renderer.export(self.timeline, path, on_progress=lambda fraction, index=index: self._report(index, fraction))
            self.completed.emit('\n'.join(path for _, _, path in self.outputs))
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.media.cancelled:
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
