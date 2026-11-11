import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from akis.preview_controller import PreviewController
from akis.timeline_model import Timeline

app = QApplication.instance() or QApplication([])


class FakeWorker(QObject):
    completed = Signal(str)
    failed = Signal(str)
    finished = Signal()
    instances = []
    log = []

    def __init__(self, timeline, output, size, executable, frame, adjustments):
        super().__init__()
        self.frame = frame
        self.output = output
        self.size = size
        self.instances.append(self)
    def start(self): pass
    def wait(self): self.log.append(('wait', self))


class CancellableWorker(FakeWorker):
    cancelled = Signal()

    def __init__(self, *args, **kwargs):
        # ProxyPlayback passes adjustments as a keyword and no frame.
        if len(args) == 4:
            args = (*args, None, kwargs.pop('adjustments', {}))
        super().__init__(*args, **kwargs)

    def cancel(self): self.log.append(('cancel', self))

    def finish(self, path=None):
        """Simulate the thread ending: completed (when given a path) or cancelled, then finished."""
        if path:
            Path(path).write_bytes(b'png')
            self.completed.emit(path)
        else:
            self.cancelled.emit()
        self.finished.emit()


class PreviewTests(unittest.TestCase):
    def setUp(self):
        FakeWorker.instances.clear()
        FakeWorker.log.clear()

    def test_latest_pending_preview_and_intermediate_frame_are_emitted(self):
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

    def test_each_frame_gets_a_new_file_and_the_previous_one_is_removed(self):
        controller = PreviewController('ffmpeg', worker_factory=CancellableWorker)
        ready = []
        controller.frame_ready.connect(ready.append)
        controller.request(Timeline(), 0, (160, 90), {})
        first = CancellableWorker.instances[-1]
        first.finish(first.output)
        controller.request(Timeline(), 0, (160, 90), {})  # same frame again, e.g. after an edit
        second = CancellableWorker.instances[-1]
        self.assertNotEqual(first.output, second.output)
        second.finish(second.output)
        self.assertEqual(ready, [first.output, second.output])
        self.assertFalse(Path(first.output).exists())
        self.assertTrue(Path(second.output).exists())
        controller.request(Timeline(), 3, (160, 90), {})
        third = CancellableWorker.instances[-1]
        third.failed.emit('boom'); third.finished.emit()
        self.assertTrue(Path(second.output).exists())  # still on screen
        controller.close()

    def test_close_cancels_the_running_render_before_waiting(self):
        controller = PreviewController('ffmpeg', worker_factory=CancellableWorker)
        controller.request(Timeline(), 0, (160, 90), {})
        worker = CancellableWorker.instances[-1]
        controller.close()
        self.assertEqual(FakeWorker.log, [('cancel', worker), ('wait', worker)])


class ProxyTests(unittest.TestCase):
    def setUp(self):
        FakeWorker.instances.clear()
        FakeWorker.log.clear()
        from akis.preview_widget import ProxyPlayback
        self.proxy = ProxyPlayback('ffmpeg', worker_factory=CancellableWorker)
        self.ready = []
        self.proxy.ready.connect(lambda: self.ready.append(self.proxy.signature))

    def tearDown(self):
        self.proxy.close()

    def test_outdated_render_is_cancelled_and_newest_request_follows(self):
        proxy = self.proxy
        proxy.prepare(Timeline(), (160, 90), {}, 'A')
        a = CancellableWorker.instances[-1]
        proxy.prepare(Timeline(), (160, 90), {}, 'A')  # same edit: no new render, no cancel
        self.assertEqual(len(CancellableWorker.instances), 1)
        proxy.prepare(Timeline(), (160, 90), {}, 'B')
        proxy.prepare(Timeline(), (160, 90), {}, 'C')  # only the newest waits
        self.assertEqual(FakeWorker.log[0], ('cancel', a))
        self.assertEqual(len(CancellableWorker.instances), 1)
        a.finish()  # cancelled
        c = CancellableWorker.instances[-1]
        self.assertEqual(len(CancellableWorker.instances), 2)
        self.assertEqual(proxy.rendering, 'C')
        self.assertEqual(self.ready, [])
        c.finish(c.output)
        self.assertEqual(self.ready, ['C'])
        self.assertTrue(proxy.is_ready('C'))

    def test_render_finishing_despite_cancel_is_not_taken_as_current(self):
        proxy = self.proxy
        proxy.prepare(Timeline(), (160, 90), {}, 'A')
        a = CancellableWorker.instances[-1]
        proxy.prepare(Timeline(), (160, 90), {}, 'B')
        a.finish(a.output)  # completed before the kill landed
        self.assertFalse(proxy.is_ready('A'))
        self.assertFalse(Path(a.output).exists())
        b = CancellableWorker.instances[-1]
        b.finish(b.output)
        self.assertTrue(proxy.is_ready('B'))
        proxy.prepare(Timeline(), (160, 90), {}, 'A')  # undo back to A: rendered again, B kept until then
        CancellableWorker.instances[-1].finish(CancellableWorker.instances[-1].output)
        self.assertTrue(proxy.is_ready('A'))

    def test_close_cancels_running_proxy_render(self):
        self.proxy.prepare(Timeline(), (160, 90), {}, 'A')
        worker = CancellableWorker.instances[-1]
        self.proxy.close()
        self.assertEqual(FakeWorker.log, [('cancel', worker), ('wait', worker)])


@unittest.skipIf(shutil.which('ffmpeg') is None, 'ffmpeg not on PATH')
class RenderWorkerCancelTests(unittest.TestCase):
    def test_cancel_ends_thread_promptly_with_cancelled_signal(self):
        from akis.render_worker import TimelineRenderWorker

        class SlowRenderer:
            def __init__(self, media, size, **adjustments):
                self.media = media

            def export(self, timeline, output):
                self.media.run(['-v', 'error', '-re', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=30',
                                '-f', 'null', '-'], text=True)
        with patch('akis.render_worker.TimelineRenderer', SlowRenderer):
            worker = TimelineRenderWorker(Timeline(), 'out.mp4', (160, 90), shutil.which('ffmpeg'),
                                          adjustments={'fast': True})
            self.assertTrue(worker.media.low_priority)
            outcome = []
            worker.completed.connect(lambda path: outcome.append('completed'))
            worker.failed.connect(lambda message: outcome.append('failed'))
            worker.cancelled.connect(lambda: outcome.append('cancelled'))
            worker.start()
            deadline = time.monotonic() + 5
            while worker.media._process is None and time.monotonic() < deadline:
                time.sleep(0.01)
            started = time.monotonic()
            worker.cancel()
            self.assertTrue(worker.wait(3000))
            self.assertLess(time.monotonic() - started, 3)
            app.processEvents()
            self.assertEqual(outcome, ['cancelled'])


if __name__ == '__main__': unittest.main()
