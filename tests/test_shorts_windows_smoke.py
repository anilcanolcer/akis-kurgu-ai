"""Opt-in Windows UI smoke for repeated Shorts analysis and close-during-render.

Run with AKIS_RUN_WINDOWS_GUI_SMOKE=1. The test creates only synthetic media and a scratch settings file.
The native folder picker is replaced with a scratch folder because this harness has no safe unattended
Windows Shell UI driver; the real Qt Shorts dialog and FFmpeg workers still run.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

FFMPEG = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')


class _CloseBridge(QObject):
    request_close = Signal()

    def __init__(self, window, release):
        super().__init__()
        self.window = window
        self.release = release
        self.worker = None
        self.render_started = threading.Event()
        self.closed = threading.Event()
        self.retained_at_close = False
        self.request_close.connect(self.close_window, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def close_window(self):
        from akis import app_support

        worker = self.worker
        self.window._close_confirmed = True
        self.window.close()
        self.retained_at_close = worker in app_support._background_threads
        self.closed.set()
        self.release.set()


@unittest.skipUnless(os.environ.get('AKIS_RUN_WINDOWS_GUI_SMOKE') == '1', 'opt-in Windows GUI smoke')
@unittest.skipUnless(sys.platform == 'win32' and FFMPEG, 'requires Windows and FFmpeg')
class WindowsShortsSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='akis-shorts-smoke-')
        cls.root = Path(cls.temp.name)
        cls.old_settings = os.environ.get('AKIS_SETTINGS_FILE')
        cls.old_language = os.environ.get('AKIS_LANGUAGE')
        os.environ['AKIS_SETTINGS_FILE'] = str(cls.root / 'settings.ini')
        os.environ['AKIS_LANGUAGE'] = 'en'
        cls.app = QApplication.instance() or QApplication([])
        if cls.app.platformName() in ('offscreen', 'minimal'):
            raise unittest.SkipTest('requires the Windows GUI platform')
        cls.source = cls.root / 'synthetic.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=320x180:r=10:d=5',
                        '-f', 'lavfi', '-i', 'sine=frequency=300:duration=5', '-pix_fmt', 'yuv420p',
                        '-shortest', str(cls.source)], check=True, timeout=20)

    @classmethod
    def tearDownClass(cls):
        if cls.old_settings is None:
            os.environ.pop('AKIS_SETTINGS_FILE', None)
        else:
            os.environ['AKIS_SETTINGS_FILE'] = cls.old_settings
        if cls.old_language is None:
            os.environ.pop('AKIS_LANGUAGE', None)
        else:
            os.environ['AKIS_LANGUAGE'] = cls.old_language
        cls.temp.cleanup()

    def setUp(self):
        from akis import app_support
        from main import MainWindow

        self.stack = ExitStack()
        self.root = Path(tempfile.mkdtemp(prefix='window-', dir=self.__class__.root))
        self.stack.enter_context(patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery'))
        self.window = MainWindow()
        self.window.show()
        self.stack.enter_context(patch.object(self.window.preview, 'request', return_value=None))
        self.assertTrue(self.window.load_video(str(self.__class__.source)))
        self.app = QApplication.instance()

    def tearDown(self):
        from akis import app_support

        if self.window.isVisible():
            self.window._close_confirmed = True
            with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
                self.window.close()
        for worker in list(getattr(self.window, '_workers', ())):
            cancel = getattr(worker, 'cancel', None)
            if callable(cancel):
                cancel()
            worker.wait(5000)
        self._pump_until(lambda: not getattr(self.window, '_workers', ()), 5)
        for thread in list(app_support._background_threads):
            thread.wait(5000)
            app_support.release_background_thread(thread)
        self.stack.close()
        self.root.rmdir() if self.root.exists() and not any(self.root.iterdir()) else None

    def _pump_until(self, condition, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return True
            time.sleep(0.01)
        return condition()

    def test_repeated_analysis_dialogs_and_close_during_render(self):
        from akis import app_support, media_service, shorts_split
        from akis.shorts_dialog import ShortsDialog

        original_dialog_exec = ShortsDialog.exec
        opened = []

        def accept_dialog(dialog):
            opened.append(dialog)
            QTimer.singleShot(30, dialog.accept)
            return original_dialog_exec(dialog)

        with ExitStack() as stack:
            stack.enter_context(patch.object(ShortsDialog, 'exec', new=accept_dialog))
            stack.enter_context(patch.object(QFileDialog, 'getExistingDirectory', return_value=''))
            for expected in range(1, 5):
                self.window.export_shorts()
                self.assertTrue(self._pump_until(
                    lambda: len(opened) == expected and not self.window._workers, 15),
                    f'Shorts dialog cycle {expected} did not finish')

        release = threading.Event()
        bridge = _CloseBridge(self.window, release)
        original_worker = shorts_split.ShortsExportWorker

        class HeldRenderWorker(original_worker):
            def __init__(worker_self, *args, **kwargs):
                kwargs['canvas'] = (90, 160)
                super().__init__(*args, **kwargs)
                bridge.worker = worker_self
                real_communicate = worker_self.media._communicate_with_progress

                def hold_after_ffmpeg_start(process, on_progress, text):
                    bridge.render_started.set()
                    bridge.request_close.emit()
                    release.wait(10)
                    return real_communicate(process, on_progress, text)

                worker_self.media._communicate_with_progress = hold_after_ffmpeg_start

        with ExitStack() as stack:
            stack.enter_context(patch('akis.shorts_split.ShortsExportWorker', new=HeldRenderWorker))
            stack.enter_context(patch.object(ShortsDialog, 'exec', new=accept_dialog))
            stack.enter_context(patch.object(QFileDialog, 'getExistingDirectory', return_value=str(self.root)))
            stack.enter_context(patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes))
            self.window.export_shorts()
            self.assertTrue(self._pump_until(bridge.closed.is_set, 15), 'close during render did not complete')

        worker = bridge.worker
        self.assertTrue(bridge.render_started.is_set(), 'FFmpeg render did not start')
        self.assertTrue(bridge.retained_at_close, 'live render worker was not retained during close')
        self.assertTrue(worker.wait(10_000), 'cancelled render worker did not finish')
        self._pump_until(lambda: worker not in app_support._background_threads, 5)
        self.assertNotIn(worker, app_support._background_threads)


if __name__ == '__main__':
    unittest.main()
