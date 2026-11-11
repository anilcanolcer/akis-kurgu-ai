"""Background workers for the story studio: text, image and video generation.

Same contract as ``ai_workers.CancellableWorker``: exactly one of completed / failed / cancelled per run;
cancel() is safe from any thread and returns at once. A network call in progress cannot be interrupted, so
it runs on a daemon helper thread: on cancel the QThread ends within ~0.1 s and the call's result is
discarded (nothing is written to disk). Workers are kept referenced by this module until they finish, so a
dialog may close (and be destroyed) while one is still running.
"""
import os
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from akis import gemini_api, story_service

POLL_SECONDS = 0.1


class WorkerCancelled(Exception):
    """Raised inside run() once cancel() was requested."""


class _Keeper(QObject):
    """Lives on the GUI thread; drops finished workers there (never from inside their own thread)."""

    def __init__(self):
        super().__init__()
        self.workers = set()

    @Slot()
    def reap(self):
        for worker in [w for w in self.workers if w.isFinished()]:
            self.workers.discard(worker)


_keeper = None


def keep_alive(worker):
    global _keeper
    if _keeper is None:
        _keeper = _Keeper()
    _keeper.workers.add(worker)
    worker.finished.connect(_keeper.reap)


def running_workers():
    return [w for w in (_keeper.workers if _keeper else ()) if w.isRunning()]


def stop_all(timeout_ms=3000):
    """At application exit: cancel every story worker and wait briefly. Returns True when all ended."""
    ok = True
    for worker in running_workers():
        worker.cancel()
        ok = worker.wait(timeout_ms) and ok
    return ok


def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.stem + '.', suffix='.part', dir=path.parent)
    try:
        with os.fdopen(handle, 'wb') as out:
            out.write(data)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


class StoryWorker(QThread):
    status = Signal(str)
    progress = Signal(int)        # seconds elapsed in the current network call
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self._cancel = threading.Event()
        keep_alive(self)

    def cancel(self):
        self._cancel.set()
        self.requestInterruption()

    def is_cancelled(self):
        return self._cancel.is_set() or self.isInterruptionRequested()

    def check_cancelled(self):
        if self.is_cancelled():
            raise WorkerCancelled()

    def call(self, fn, *args, **kwargs):
        """Run a blocking call on a daemon thread; return its result or raise its error, unless cancelled."""
        box = {}
        done = threading.Event()

        def target():
            try:
                box['result'] = fn(*args, **kwargs)
            except BaseException as exc:  # handed to the worker thread below
                box['error'] = exc
            finally:
                done.set()

        threading.Thread(target=target, name='akis-story-call', daemon=True).start()
        started, last = time.monotonic(), -1
        while not done.wait(POLL_SECONDS):
            self.check_cancelled()
            elapsed = int(time.monotonic() - started)
            if elapsed != last:
                last = elapsed
                self.progress.emit(elapsed)
        self.check_cancelled()
        if 'error' in box:
            raise box['error']
        return box.get('result')

    def work(self):
        raise NotImplementedError

    def run(self):
        try:
            self.check_cancelled()
            result = self.work()
            self.check_cancelled()
            self.completed.emit(result)
        except Exception as exc:
            if isinstance(exc, WorkerCancelled) or self.is_cancelled():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc) or type(exc).__name__)


class CallWorker(StoryWorker):
    """Any blocking callable (e.g. listing models)."""

    def __init__(self, fn, message=''):
        super().__init__()
        self.fn, self.message = fn, message

    def work(self):
        if self.message:
            self.status.emit(self.message)
        return self.call(self.fn)


class TextWorker(StoryWorker):
    """Runs a story_service.TextJob; completed(TextResult)."""

    def __init__(self, job, api_key, transport=None):
        super().__init__()
        self.job, self.api_key, self.transport = job, api_key, transport

    def work(self):
        labels = {'scene': 'Sahne yazılıyor', 'continue': 'Sahneye devam ediliyor', 'rewrite': 'Sahne yeniden yazılıyor',
                  'memory': 'Özet ve süreklilik notları güncelleniyor', 'visual': 'Görsel istemi hazırlanıyor',
                  'bible': 'Hikâye rehberi oluşturuluyor', 'outline': 'Olay örgüsü taslağı çıkarılıyor',
                  'split': 'Metin sahnelere bölünüyor'}
        self.status.emit(f'{labels.get(self.job.kind, "Metin üretiliyor")} ({self.job.model})…')
        return self.call(story_service.run_text_job, self.job, self.api_key, transport=self.transport)


class ImageWorker(StoryWorker):
    """completed({'path', 'mime_type', 'model', 'text'}). ``target(extension) -> Path`` names the file."""

    def __init__(self, api_key, model, prompt, target, *, references=(), aspect_ratio='16:9', image_size='1K',
                 transport=None):
        super().__init__()
        self.api_key, self.model, self.prompt, self.target = api_key, model, prompt, target
        self.references = list(references)   # [(path, role, label)]
        self.aspect_ratio, self.image_size, self.transport = aspect_ratio, image_size, transport

    def work(self):
        refs = [gemini_api.load_image(path, role, label) for path, role, label in self.references]
        self.status.emit(f'Görsel üretiliyor ({self.model}, {self.image_size})…')
        result = self.call(gemini_api.generate_image, self.api_key, self.model, self.prompt, references=refs,
                           aspect_ratio=self.aspect_ratio, image_size=self.image_size, transport=self.transport)
        self.check_cancelled()
        path = Path(self.target(gemini_api.extension_for(result.mime_type)))
        write_atomic(path, result.data)
        return {'path': str(path), 'mime_type': result.mime_type, 'model': result.model, 'text': result.text}


class VideoWorker(StoryWorker):
    """completed({'path', 'model', 'interaction_id'}). One attempt only: a timeout is never retried."""

    def __init__(self, api_key, model, prompt, target, *, image_path='', aspect_ratio='16:9', resolution='720p',
                 duration=8, transport=None, getter=None):
        super().__init__()
        self.api_key, self.model, self.prompt, self.target = api_key, model, prompt, target
        self.image_path, self.aspect_ratio, self.resolution = image_path, aspect_ratio, resolution
        self.duration, self.transport, self.getter = duration, transport, getter

    def work(self):
        images = [gemini_api.load_image(self.image_path, 'object', 'first frame')] if self.image_path else []
        self.status.emit(f'Video üretiliyor ({self.model}, {self.resolution}, {self.duration} sn); bu birkaç dakika sürebilir…')
        result = self.call(gemini_api.generate_video, self.api_key, self.prompt, model=self.model, images=images,
                           aspect_ratio=self.aspect_ratio, resolution=self.resolution, duration=self.duration,
                           transport=self.transport, getter=self.getter)
        self.check_cancelled()
        path = Path(self.target(gemini_api.extension_for(result.mime_type)))
        write_atomic(path, result.data)
        return {'path': str(path), 'model': result.model, 'interaction_id': result.interaction_id}
