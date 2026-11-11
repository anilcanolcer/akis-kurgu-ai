import logging

from PySide6.QtCore import QThread, Signal
from akis import update_service

log = logging.getLogger("akis.update")


class UpdateCheckWorker(QThread):
    """Reads the latest release's metadata only; nothing is downloaded."""
    available = Signal(object)
    up_to_date = Signal()
    failed = Signal(str)

    def run(self):
        try:
            update = update_service.check_update()
        except Exception as exc:  # offline, rate-limited, malformed release: never bother the user
            log.info("Güncelleme denetimi başarısız: %s", exc)
            self.failed.emit(str(exc))
            return
        if self.isInterruptionRequested():
            return
        if update:
            self.available.emit(update)
        else:
            self.up_to_date.emit()


class UpdateDownloadWorker(QThread):
    """Downloads and verifies one installer; honours requestInterruption() between chunks."""
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int, int)  # bytes done, total (0 when unknown)

    def __init__(self, update, destination, parent=None):
        super().__init__(parent)
        self.update = update
        self.destination = destination

    def run(self):
        try:
            path = update_service.download(self.update, self.destination,
                                           should_stop=self.isInterruptionRequested,
                                           progress=lambda done, total: self.progress.emit(done, total))
        except update_service.DownloadCancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
        else:
            self.completed.emit(path)
