from PySide6.QtCore import QThread, Signal
import update_service

class UpdateCheckWorker(QThread):
    available = Signal(object)
    def run(self):
        try:
            update = update_service.check_update()
            if update: self.available.emit(update)
        except Exception:
            pass

class UpdateDownloadWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    def __init__(self, update, destination):
        super().__init__(); self.update = update; self.destination = destination
    def run(self):
        try: self.completed.emit(update_service.download(self.update, self.destination))
        except Exception as exc: self.failed.emit(str(exc))
