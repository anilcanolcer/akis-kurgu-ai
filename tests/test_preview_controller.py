import unittest
from PySide6.QtCore import QObject, Signal
from akis.preview_controller import PreviewController
from akis.timeline_model import Timeline

class FakeWorker(QObject):
    completed = Signal(str)
    failed = Signal(str)
    finished = Signal()
    instances = []
    def __init__(self, timeline, output, size, executable, frame, adjustments):
        super().__init__()
        self.frame = frame
        self.output = output
        self.size = size
        self.instances.append(self)
    def start(self): pass
    def wait(self): pass

class PreviewTests(unittest.TestCase):
    def test_latest_pending_preview_and_intermediate_frame_are_emitted(self):
        FakeWorker.instances.clear()
        controller = PreviewController('ffmpeg', worker_factory=FakeWorker)
        ready = []
        controller.frame_ready.connect(ready.append)
        model = Timeline()
        controller.request(model, 0, (1920, 1080), {})
        first = FakeWorker.instances[-1]
        controller.request(model, 1, (1920, 1080), {})
        controller.request(model, 8, (1920, 1080), {})
        first.completed.emit(first.output)
        self.assertEqual(ready, [first.output])
        first.finished.emit()
        self.assertEqual(FakeWorker.instances[-1].frame, 8)
        self.assertEqual(first.size, (480, 270))
        controller.close()

if __name__ == '__main__': unittest.main()
