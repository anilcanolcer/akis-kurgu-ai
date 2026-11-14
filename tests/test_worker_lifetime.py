import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
import threading
import time
from unittest.mock import patch
from PySide6.QtCore import QThread, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import MainWindow

app = QApplication.instance() or QApplication([])

class DelayedFailure(QThread):
    """Reports an error, then keeps running until the test lets it finish (no timing guesswork)."""
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def run(self):
        self.failed.emit('API error')
        self.release.wait(10)


def settle(condition, seconds=10):
    end = time.time() + seconds
    while not condition() and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

class WorkerLifetimeTests(unittest.TestCase):
    def test_worker_survives_error_until_thread_finishes(self):
        window = MainWindow()
        worker = DelayedFailure()
        window.worker = worker
        with patch('main.QMessageBox.critical'):
            worker.failed.connect(window.on_worker_error)
            window.start_worker()
            settle(worker.isRunning)
            settle(lambda: False, 0.1)             # the error signal is delivered while the thread still runs
            self.assertTrue(worker.isRunning())
            self.assertIs(window.worker, worker)
            self.assertFalse(window.can_start_work())
            self.assertFalse(window.close())
            worker.release.set()
            self.assertTrue(worker.wait(10000))
            settle(lambda: window.worker is None and not window._workers)
            self.assertIsNone(window.worker)
            self.assertFalse(window._workers)
            self.assertTrue(window.close())

if __name__ == '__main__': unittest.main()

