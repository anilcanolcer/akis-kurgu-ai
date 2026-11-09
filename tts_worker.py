from PySide6.QtCore import QThread, Signal
from tts_service import synthesize

class TtsWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    def __init__(self, text, destination):
        super().__init__()
        self.text, self.destination = text, destination
    def run(self):
        try:
            self.completed.emit(synthesize(self.text, self.destination))
        except Exception as exc:
            self.failed.emit(str(exc))
