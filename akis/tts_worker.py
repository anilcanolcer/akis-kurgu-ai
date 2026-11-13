from PySide6.QtCore import QThread, Signal
from akis.tts_service import synthesize

class TtsWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    def __init__(self, text, destination, voice_id=None, language='tr'):
        super().__init__()
        self.text, self.destination = text, destination
        self.voice_id, self.language = voice_id, language
    def run(self):
        try:
            self.completed.emit(synthesize(self.text, self.destination, voice_id=self.voice_id, language=self.language))
        except Exception as exc:
            self.failed.emit(str(exc))
