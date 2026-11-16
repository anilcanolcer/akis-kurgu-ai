"""Slow steps run off the window's thread: the worker, and the window staying usable meanwhile."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis.call_worker import CallWorker

app = QApplication.instance() or QApplication([])


class HeldResultWorker(CallWorker):
    """Emit the result, then stay alive until released to expose premature callbacks."""
    def __init__(self, function):
        super().__init__(function)
        self.release = threading.Event()

    def run(self):
        self.completed.emit(self.function())
        self.release.wait(5)


class HeldFailureWorker(HeldResultWorker):
    def run(self):
        self.failed.emit('analysis failed')
        self.release.wait(5)


class WorkerTests(unittest.TestCase):
    def run_worker(self, function):
        worker = CallWorker(function)
        got = []
        worker.completed.connect(lambda value: got.append(('done', value)))
        worker.failed.connect(lambda message: got.append(('failed', message)))
        worker.start()
        self.assertTrue(worker.wait(5000))
        app.processEvents()
        return got

    def test_result_comes_back_from_another_thread(self):
        main = threading.get_ident()
        self.assertEqual(self.run_worker(lambda: threading.get_ident() != main), [('done', True)])

    def test_error_is_reported_once(self):
        def broken():
            raise RuntimeError('okunamadı')
        self.assertEqual(self.run_worker(broken), [('failed', 'okunamadı')])


class WindowTests(unittest.TestCase):
    def test_window_is_free_while_the_step_runs_and_busy_for_other_work(self):
        from main import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        window = MainWindow()
        release = threading.Event()
        results = []
        window.run_analysis('çalışıyor…', lambda: release.wait(5) and 42, results.append)
        self.assertEqual(window.status_label.text(), 'çalışıyor…')
        app.processEvents()                                      # the event loop is not blocked
        self.assertFalse(window.can_start_work())                # one task at a time, as for any worker
        release.set()
        self.assertTrue(window.worker.wait(5000))
        app.processEvents()
        app.processEvents()
        self.assertEqual(results, [42])
        self.assertTrue(window.can_start_work())
        window._close_confirmed = True
        window.close()

    def test_analysis_callback_waits_for_thread_finish(self):
        from main import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        window = MainWindow()
        worker = HeldResultWorker(lambda: 42)
        results = []
        with patch('akis.window.timeline_edit.CallWorker', return_value=worker):
            window.run_analysis('working…', lambda: 42, results.append)
        deadline = time.monotonic() + 5
        while not worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        for _ in range(10):
            app.processEvents()
            time.sleep(.005)
        self.assertTrue(worker.isRunning())
        self.assertEqual(results, [])
        self.assertIn(worker, window._workers)

        worker.release.set()
        self.assertTrue(worker.wait(5000))
        deadline = time.monotonic() + 5
        while (not results or window._workers) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        app.processEvents()
        self.assertEqual(results, [42])
        self.assertFalse(window._workers)
        self.assertIsNone(window.worker)
        window._close_confirmed = True
        window.close()

    def test_analysis_error_is_reported_after_thread_finish(self):
        from main import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        window = MainWindow()
        worker = HeldFailureWorker(lambda: None)
        with patch('akis.window.timeline_edit.CallWorker', return_value=worker), \
             patch('main.QMessageBox.critical') as critical:
            window.run_analysis('working…', lambda: None, lambda value: self.fail('failed worker delivered a result'))
            deadline = time.monotonic() + 5
            while not worker.isRunning() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
            for _ in range(10):
                app.processEvents()
                time.sleep(.005)
            self.assertTrue(worker.isRunning())
            critical.assert_not_called()

            worker.release.set()
            self.assertTrue(worker.wait(5000))
            deadline = time.monotonic() + 5
            while not critical.called and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
            critical.assert_called_once()
            self.assertEqual(critical.call_args.args[2], 'analysis failed')
        window._close_confirmed = True
        window.close()


if __name__ == '__main__':
    unittest.main()
