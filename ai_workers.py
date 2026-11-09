"""Background API-based planning and transcription."""
import base64
import re
import tempfile
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from media_service import MediaService
from ai_service import parse_suggestions
from ai_providers import request_plan, transcribe


class AIWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key: str, model: str, video: str, duration: float, prompt: str, executable: str, provider: str = "OpenAI") -> None:
        super().__init__()
        self.api_key = api_key
        self.provider = provider
        self.model = model
        self.video = video
        self.duration = duration
        self.prompt = prompt
        self.executable = executable

    def run(self) -> None:
        try:
            self.status.emit("Videodan temsilci kareler seçiliyor…")
            with tempfile.TemporaryDirectory(prefix="akis_ai_") as temp:
                frames = []
                moments = [0.05, 0.22, 0.42, 0.62, 0.82]
                for index, ratio in enumerate(moments):
                    target = Path(temp) / f"frame_{index}.jpg"
                    at = max(0, min(self.duration - 0.05, self.duration * ratio))
                    result = MediaService(self.executable).extract_frame(self.video, at, target)
                    if result.returncode == 0 and target.exists():
                        frames.append((at, target))

                if not frames:
                    raise RuntimeError("Videodan analiz karesi çıkarılamadı.")

                prompt = (
                    "Aşağıdaki kareler aynı videodan zamana göre sıralıdır. Türkçe yanıt ver. "
                    f"Video süresi {self.duration:.2f} saniye. Kullanıcı hedefi: {self.prompt}\n"
                    "Yalnızca geçerli JSON döndür. Şema: "
                    '{"suggestions":[{"summary":"", "title":"", "caption":"", "hashtags":[""], '
                    '"trim_start":0.0, "trim_end":0.0, "pacing":"", "filter":"natural|vivid|cinematic", '
                    '"notes":[""]}]} Üç farklı öneri ver. Zamanlar video sınırları içinde olsun.'
                )
                self.status.emit("AI kurgu planı hazırlanıyor…")
                text = request_plan(self.provider, self.api_key, self.model, prompt,
                                    [(at, path.read_bytes()) for at, path in frames]).strip()
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if not match:
                    raise RuntimeError("AI yanıtı kurgu planı olarak okunamadı.")
                self.completed.emit(parse_suggestions(match.group(0), self.duration))
        except Exception as exc:
            self.failed.emit(str(exc))


class TranscriptWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key: str, video: str, executable: str, model: str = "gpt-4o-mini-transcribe", provider: str = "OpenAI") -> None:
        super().__init__()
        self.api_key = api_key
        self.video = video
        self.executable = executable
        self.model = model
        self.provider = provider

    def run(self) -> None:
        try:
            self.status.emit("Ses parçası hazırlanıyor…")
            with tempfile.TemporaryDirectory(prefix="akis_audio_") as temp:
                audio = Path(temp) / "audio.mp3"
                result = MediaService(self.executable).extract_audio(self.video, audio)
                if result.returncode != 0 or not audio.exists():
                    raise RuntimeError("Videodan ses parçası çıkarılamadı.")
                self.status.emit("Türkçe konuşma metne çevriliyor…")
                self.completed.emit(transcribe(self.provider, self.api_key, self.model, audio))
        except Exception as exc:
            self.failed.emit(str(exc))


