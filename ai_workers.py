"""Background API-based planning and transcription."""
import base64
import re
import tempfile
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from media_service import MediaService
from ai_service import parse_suggestions


class AIWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key: str, model: str, video: str, duration: float, prompt: str, executable: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.video = video
        self.duration = duration
        self.prompt = prompt
        self.executable = executable

    def run(self) -> None:
        try:
            from openai import OpenAI

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

                content = [{
                    "type": "input_text",
                    "text": (
                        "Aşağıdaki kareler aynı videodan zamana göre sıralıdır. Türkçe yanıt ver. "
                        f"Video süresi {self.duration:.2f} saniye. Kullanıcı hedefi: {self.prompt}\n\n"
                        "Yalnızca geçerli JSON döndür ve başka metin yazma. Şema: "
                        '{"suggestions":[{"summary":"", "title":"", "caption":"", "hashtags":[""], '
                        '"trim_start":0.0, "trim_end":0.0, "pacing":"", "filter":"natural|vivid|cinematic", '
                        '"notes":[""]}, ...]} Üç farklı öneri ver. trim_start/trim_end video sınırları içinde olsun.'
                    ),
                }]
                for at, path in frames:
                    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                    content.append({"type": "input_text", "text": f"{at:.2f}. saniyedeki kare:"})
                    content.append({"type": "input_image", "detail": "low", "image_url": f"data:image/jpeg;base64,{encoded}"})

                self.status.emit("AI kurgu planı hazırlanıyor…")
                client = OpenAI(api_key=self.api_key)
                response = client.responses.create(
                    model=self.model,
                    instructions="Kısa video kurgusunda uzman, ölçülü ve pratik bir Türkçe kreatif direktörsün.",
                    input=[{"role": "user", "content": content}],
                )
                text = response.output_text.strip()
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

    def __init__(self, api_key: str, video: str, executable: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.video = video
        self.executable = executable

    def run(self) -> None:
        try:
            from openai import OpenAI

            self.status.emit("Ses parçası hazırlanıyor…")
            with tempfile.TemporaryDirectory(prefix="akis_audio_") as temp:
                audio = Path(temp) / "audio.mp3"
                result = MediaService(self.executable).extract_audio(self.video, audio)
                if result.returncode != 0 or not audio.exists():
                    raise RuntimeError("Videodan ses parçası çıkarılamadı.")
                self.status.emit("Türkçe konuşma metne çevriliyor…")
                client = OpenAI(api_key=self.api_key)
                with audio.open("rb") as handle:
                    transcript = client.audio.transcriptions.create(
                        model="gpt-transcribe",
                        file=handle,
                        prompt="Türkçe kısa video konuşması. Noktalama işaretlerini doğal kullan.",
                    )
                self.completed.emit(transcript.text)
        except Exception as exc:
            self.failed.emit(str(exc))


