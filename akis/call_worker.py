"""Run one slow, self-contained step (reading a video's sound, finding beats…) off the window's thread.

Exactly one of completed / failed is emitted per run, then QThread.finished. The function must not touch
widgets; its result is handed back on the window's thread through `completed`.
"""
from PySide6.QtCore import QThread, Signal


class CallWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, function):
        super().__init__()
        self.function = function

    def run(self):
        try:
            result = self.function()
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.completed.emit(result)
