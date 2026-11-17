"""A dismissed silence dialog must not destroy its still-running measurement QThread."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import gc
import threading
import unittest
import weakref
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from akis import app_support
from akis.silence_dialog import SilenceDialog

app = QApplication.instance() or QApplication([])


class SilenceWorkerLifetimeTests(unittest.TestCase):
    def tearDown(self):
        # Avoid leaking a retained test thread into other Qt tests.
        for thread in list(app_support._background_threads):
            cancel = getattr(thread, 'cancel', None)
            if callable(cancel):
                cancel()
            thread.wait(5000)
            app_support.release_background_thread(thread)

    def test_cancelled_measurement_remains_owned_until_finished(self):
        release = threading.Event()
        finished = threading.Event()

        def slow_measure(_executable, _path):
            release.wait(5)
            finished.set()
            return []

        dialog = SilenceDialog(executable='ffmpeg', sources=[{'path':'synthetic'}],
                               segments=[{'source':0,'start':0,'end':1}], measure=slow_measure)
        worker = dialog.worker
        worker_ref = weakref.ref(worker)
        QTimer.singleShot(25, dialog.reject)
        self.assertEqual(dialog.exec(), 0)
        self.assertTrue(worker.isRunning())
        self.assertIn(worker, app_support._background_threads)

        dialog.deleteLater()
        app.processEvents()
        del dialog, worker
        gc.collect()
        self.assertIsNotNone(worker_ref())

        release.set()
        self.assertTrue(worker_ref().wait(3000))
        self.assertTrue(finished.is_set())
        QTest.qWait(10)
        app.processEvents()
        self.assertNotIn(worker_ref(), app_support._background_threads)

    def test_shutdown_drains_a_live_registered_measurement(self):
        release = threading.Event()
        dialog = SilenceDialog(executable='ffmpeg', sources=[{'path':'synthetic'}],
                               segments=[{'source':0,'start':0,'end':1}],
                               measure=lambda _executable, _path: (release.wait(5) or []))
        worker = dialog.worker
        started = threading.Event()
        worker.started.connect(started.set)
        if worker.isRunning():
            started.set()
        self.assertTrue(started.wait(1))
        stopper = threading.Thread(target=app_support.wait_for_background_threads, daemon=True)
        stopper.start()
        self.assertIn(worker, app_support._background_threads)
        release.set()
        stopper.join(3)
        self.assertFalse(stopper.is_alive())
        self.assertTrue(worker.isFinished())
        self.assertNotIn(worker, app_support._background_threads)
        dialog._close_approved = True
        dialog.close()

    def test_shutdown_does_not_drop_a_thread_while_start_is_pending(self):
        waiting = threading.Event()
        finish = threading.Event()

        class PendingThread:
            def __init__(self):
                self.finished = False

            def isRunning(self):
                return False

            def isFinished(self):
                return self.finished

            def requestInterruption(self):
                pass

            def wait(self, milliseconds):
                waiting.set()
                done = finish.wait(milliseconds / 1000)
                self.finished = done
                return done

        thread = PendingThread()
        app_support.retain_background_thread(thread)
        with patch.object(app_support, 'THREAD_STOP_WAIT_MS', 100):
            stopper = threading.Thread(target=app_support.wait_for_background_threads, daemon=True)
            stopper.start()
            self.assertTrue(waiting.wait(1))
            self.assertIn(thread, app_support._background_threads)
            finish.set()
            stopper.join(1)
        self.assertFalse(stopper.is_alive())
        self.assertTrue(thread.isFinished())
        self.assertNotIn(thread, app_support._background_threads)


if __name__ == '__main__':
    unittest.main()
