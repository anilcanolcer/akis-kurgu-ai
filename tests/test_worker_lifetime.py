import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
import time
from unittest.mock import patch
from PySide6.QtCore import QThread, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import MainWindow

app = QApplication.instance() or QApplication([])

class DelayedFailure(QThread):
    failed = Signal(str)
    def run(self):
        self.failed.emit('API error')
        self.msleep(300)

class WorkerLifetimeTests(unittest.TestCase):
    def test_worker_survives_error_until_thread_finishes(self):
        window = MainWindow()
        worker = DelayedFailure()
        window.worker = worker
        with patch('main.QMessageBox.critical'):
            worker.failed.connect(window.on_worker_error)
            window.start_worker()
            time.sleep(0.1)
            app.processEvents()
            self.assertTrue(worker.isRunning())
            self.assertIs(window.worker, worker)
            self.assertFalse(window.can_start_work())
            self.assertFalse(window.close())
            time.sleep(0.4)
            app.processEvents()
            self.assertIsNone(window.worker)
            self.assertFalse(window._workers)
            self.assertTrue(window.close())

if __name__ == '__main__': unittest.main()

