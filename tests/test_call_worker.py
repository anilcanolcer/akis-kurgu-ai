"""Slow steps run off the window's thread: the worker, and the window staying usable meanwhile."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis.call_worker import CallWorker

app = QApplication.instance() or QApplication([])


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


if __name__ == '__main__':
    unittest.main()
