"""Background API-based planning and transcription."""
import tempfile
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from akis.media_service import MediaService
from akis.ai_service import parse_suggestions
from akis.ai_providers import request_plan, transcribe
from akis.ai_service import local_transcribe
from akis.timeline_model import Timeline
from akis import edit_plan


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
                                    [(at, path.read_bytes()) for at, path in frames])
                self.completed.emit(parse_suggestions(text, self.duration))
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


MAX_FRAMES = 32
FRAME_LABEL_NOTE = ('Kare etiketleri "K<kaynak> @ <saniye>s" biçimindedir '
                    '(ör. "K1 @ 12.50s" → Kaynak 1, kaynağın kendi 12.50. saniyesi).')


def frame_label(index, at):
    """Unambiguous per-image label: source number and second in that source's own time."""
    return f'K{index} @ {at:.2f}s'


def frame_counts(durations, cap=MAX_FRAMES):
    """Frames to sample per source: ~1 per 2 s, at least 3, at most max(4, 24 // n); never more than cap in total.

    Over the cap, every source is trimmed to a common level (fair share; short sources keep what they need)
    and leftovers go to the longest sources. With more sources than the cap, evenly spread sources get one each.
    """
    n = len(durations)
    if not n:
        return []
    budget = max(4, 24 // n)
    wanted = [max(3, min(budget, round(d / 2))) for d in durations]
    if sum(wanted) <= cap:
        return wanted
    if n >= cap:
        picked = {round(i * (n - 1) / (cap - 1)) for i in range(cap)} if cap > 1 else {0}
        return [1 if i in picked else 0 for i in range(n)]
    level = max(1, cap // n)
    while level < max(wanted) and sum(min(w, level + 1) for w in wanted) <= cap:
        level += 1
    counts = [min(w, level) for w in wanted]
    spare = cap - sum(counts)
    for i in sorted(range(n), key=lambda i: -durations[i]):
        if spare <= 0:
            break
        if counts[i] < wanted[i]:
            counts[i] += 1
            spare -= 1
    return counts


class PromptEditWorker(QThread):
    """Analyse every source, ask the model for an edit plan, and return it validated."""
    completed = Signal(dict, list)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key, model, provider, request, timeline, sources, executable,
                 transcripts=None, whisper_model=None, request_fn=request_plan, settings=None) -> None:
        super().__init__()
        self.api_key, self.model, self.provider = api_key, model, provider
        self.request = request
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.settings = settings
        self.sources = [{'path': path, 'duration': duration} for path, duration in sources]
        self.executable = executable
        self.transcripts = dict(transcripts or {})
        self.whisper_model = whisper_model
        self.request_fn = request_fn

    def analyse(self, temp):
        media = MediaService(self.executable)
        frames = []
        counts = frame_counts([source['duration'] for source in self.sources])
        for index, source in enumerate(self.sources):
            path, duration = source['path'], source['duration']
            self.status.emit(f"Video çözümleniyor ({index + 1}/{len(self.sources)}): ses, sahne ve kareler…")
            source['silences'] = media.silences(path) if media.has_audio(path) else []
            source['scenes'] = media.scene_changes(path)
            source['size'] = media.dimensions(path)
            transcript = self.transcripts.get(path)
            if transcript is None and self.whisper_model and media.has_audio(path):
                try:
                    self.status.emit('Konuşma yerel Whisper ile çözümleniyor…')
                    transcript = local_transcribe(path, self.whisper_model, timed=True)
                except Exception:
                    transcript = None  # Editing still works from frames, silence and scenes.
            source['transcript'] = transcript or []
            count = counts[index]
            for step in range(count):
                at = max(0.0, min(duration - 0.05, duration * (step + 0.5) / count))
                target = Path(temp) / f"s{index}_f{step}.jpg"
                if media.extract_frame(path, at, target).returncode == 0 and target.exists():
                    frames.append((index, at, target.read_bytes()))
        if not frames:
            raise RuntimeError("Videodan analiz karesi çıkarılamadı.")
        return frames

    def run(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="akis_edit_") as temp:
                frames = self.analyse(temp)
            prompt = edit_plan.build_prompt(self.request, self.sources, self.timeline, settings=self.settings)
            self.status.emit("AI kurgu kararlarını veriyor…")
            text = self.request_fn(self.provider, self.api_key, self.model,
                                   prompt + '\n' + FRAME_LABEL_NOTE,
                                   [(frame_label(index, at), data) for index, at, data in frames],
                                   instruction=edit_plan.INSTRUCTION)
            plan = edit_plan.parse_plan(text, [s['duration'] for s in self.sources],
                                        current_duration=edit_plan.primary_duration(self.timeline))
            self.completed.emit(plan, self.sources)
        except Exception as exc:
            self.failed.emit(str(exc))
