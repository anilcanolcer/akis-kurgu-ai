from PySide6.QtCore import QThread, Signal
from ai_service import local_transcribe

class LocalCaptionWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)
    status = Signal(str)
    def __init__(self, video, model, download):
        super().__init__()
        self.video, self.model, self.download = video, model, download
    def run(self):
        try:
            self.status.emit('Yerel model yükleniyor ve konuşma çözümleniyor…')
            self.completed.emit(local_transcribe(self.video, self.model, download=self.download, timed=True))
        except Exception as exc:
            self.failed.emit(str(exc))
