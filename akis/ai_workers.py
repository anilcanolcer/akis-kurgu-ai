"""Background API-based planning and transcription."""
import tempfile
import threading
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from akis.media_service import MediaService, RenderCancelled
from akis.ai_service import parse_suggestions
from akis.ai_providers import fallback_note, request_plan, transcribe
from akis.ai_service import local_transcribe
from akis.timeline_model import Timeline
from akis import analysis_cache, edit_plan, speech_settings

POLL_SECONDS = 0.1


class WorkerCancelled(Exception):
    """Raised inside run() between stages once cancel() was requested."""


class CancellableWorker(QThread):
    """A worker whose FFmpeg stages stop at once on cancel(). A network call cannot be interrupted, so it
    runs on a daemon helper thread (see call()): on cancel the worker ends within ~0.1 s and the call's
    result is discarded. Exactly one of completed / failed / cancelled is emitted per run."""
    cancelled = Signal()

    def __init__(self, executable) -> None:
        super().__init__()
        self.executable = executable
        self.media = MediaService(executable)

    def cancel(self) -> None:
        """Safe from any thread; returns at once."""
        self.requestInterruption()
        self.media.cancel()

    def check_cancelled(self) -> None:
        if self.isInterruptionRequested() or self.media.cancelled:
            raise WorkerCancelled()

    def call(self, fn, *args, **kwargs):
        """Run a blocking call on a daemon thread, checking for cancel every POLL_SECONDS.

        Returns its result or raises its error; once cancelled, raises WorkerCancelled at once and the
        call's eventual result is dropped (the helper thread ends on its own; the request's own timeout
        and deadline bound it).
        """
        self.check_cancelled()
        box = {}
        done = threading.Event()

        def target():
            try:
                box['result'] = fn(*args, **kwargs)
            except BaseException as exc:  # handed to the worker thread below
                box['error'] = exc
            finally:
                done.set()

        threading.Thread(target=target, name='akis-ai-call', daemon=True).start()
        while not done.wait(POLL_SECONDS):
            self.check_cancelled()
        self.check_cancelled()
        if 'error' in box:
            raise box['error']
        return box.get('result')

    def report_error(self, exc: Exception) -> None:
        if isinstance(exc, (WorkerCancelled, RenderCancelled)) or self.isInterruptionRequested() or self.media.cancelled:
            self.cancelled.emit()
        else:
            self.failed.emit(str(exc))


class AIWorker(CancellableWorker):
    completed = Signal(list)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key: str, model: str, video: str, duration: float, prompt: str, executable: str, provider: str = "OpenAI") -> None:
        super().__init__(executable)
        self.api_key = api_key
        self.provider = provider
        self.model = model
        self.video = video
        self.duration = duration
        self.prompt = prompt

    def run(self) -> None:
        try:
            self.status.emit("Videodan temsilci kareler seçiliyor…")
            with tempfile.TemporaryDirectory(prefix="akis_ai_") as temp:
                frames = []
                moments = [0.05, 0.22, 0.42, 0.62, 0.82]
                for index, ratio in enumerate(moments):
                    self.check_cancelled()
                    target = Path(temp) / f"frame_{index}.jpg"
                    at = max(0, min(self.duration - 0.05, self.duration * ratio))
                    result = self.media.extract_frame(self.video, at, target)
                    if result.returncode == 0 and target.exists():
                        frames.append((at, target))

                if not frames:
                    raise RuntimeError("Videodan analiz karesi çıkarılamadı.")

                prompt = (
                    "Aşağıdaki kareler aynı videodan zamana göre sıralıdır. Türkçe yanıt ver. "
                    f"Video süresi {self.duration:.2f} saniye. Kullanıcı hedefi: {self.prompt}\n"
                    "Tam olarak 3 farklı kurgu önerisi ver. Yalnızca geçerli JSON döndür; açıklama, başlık veya kod bloğu ekleme. "
                    "Şema: "
                    '{"suggestions":[{"summary":"", "title":"", "caption":"", "hashtags":["",""], '
                    '"trim_start":2.5, "trim_end":18.0, "pacing":"", "filter":"natural|vivid|cinematic", '
                    '"notes":["",""]}]}\n'
                    f"Kurallar: trim_start ve trim_end saniye cinsinden sayıdır; trim_end her zaman trim_start'tan büyük "
                    f"ve en fazla {self.duration:.2f} olmalıdır; kesit en az 3 saniye sürsün. "
                    "Şemadaki 2.5 ve 18.0 yalnızca örnektir; değerleri bu videoya göre kendin belirle. "
                    "filter yalnızca natural, vivid veya cinematic olsun; hashtags # işaretsiz kelimeler olsun."
                )
                self.check_cancelled()
                self.status.emit("AI kurgu planı hazırlanıyor…")
                text = self.call(request_plan, self.provider, self.api_key, self.model, prompt,
                                 [(at, path.read_bytes()) for at, path in frames])
                suggestions = parse_suggestions(text, self.duration)
            self.check_cancelled()
            note = fallback_note(text)
            if note:  # format_suggestion lists notes, so every suggestion says which model wrote it
                suggestions = [dict(s, notes=list(s.get('notes') or []) + [note]) for s in suggestions]
            self.completed.emit(suggestions)
        except Exception as exc:
            self.report_error(exc)


class TranscriptWorker(CancellableWorker):
    completed = Signal(str)
    timed = Signal(list)        # [{'start', 'end', 'text'}], before completed, when the service gave timings
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key: str, video: str, executable: str, model: str = "gpt-4o-mini-transcribe", provider: str = "OpenAI") -> None:
        super().__init__(executable)
        self.api_key = api_key
        self.video = video
        self.model = model
        self.provider = provider

    def run(self) -> None:
        try:
            self.status.emit("Ses parçası hazırlanıyor…")
            # A cancelled upload may still hold the file open on its helper thread.
            with tempfile.TemporaryDirectory(prefix="akis_audio_", ignore_cleanup_errors=True) as temp:
                audio = Path(temp) / "audio.mp3"
                result = self.media.extract_audio(self.video, audio)
                self.check_cancelled()
                if result.returncode != 0 or not audio.exists():
                    raise RuntimeError("Videodan ses parçası çıkarılamadı.")
                self.status.emit("Konuşma metne çevriliyor…")
                text = self.call(transcribe, self.provider, self.api_key, self.model, audio)
            self.check_cancelled()
            segments = getattr(text, 'segments', None)
            if segments:
                self.timed.emit(list(segments))
            self.completed.emit(str(text))
        except Exception as exc:
            self.report_error(exc)


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


class PromptEditWorker(CancellableWorker):
    """Analyse every source, ask the model for an edit plan, and return it validated."""
    completed = Signal(dict, list)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key, model, provider, request, timeline, sources, executable,
                 transcripts=None, whisper_model=None, request_fn=request_plan, settings=None) -> None:
        super().__init__(executable)
        self.api_key, self.model, self.provider = api_key, model, provider
        self.request = request
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.settings = settings
        self.sources = [{'path': path, 'duration': duration} for path, duration in sources]
        self.transcripts = dict(transcripts or {})
        self.whisper_model = whisper_model
        self.request_fn = request_fn

    def analyse(self, temp):
        media = self.media
        frames = []
        counts = frame_counts([source['duration'] for source in self.sources])
        for index, source in enumerate(self.sources):
            self.check_cancelled()
            path, duration = source['path'], source['duration']
            self.status.emit(f"Video çözümleniyor ({index + 1}/{len(self.sources)}): ses, sahne ve kareler…")
            # Follow-up requests on the same file reuse what the first one worked out (akis.analysis_cache).
            source['silences'] = analysis_cache.remember(
                path, 'silences', lambda: media.silences(path) if media.has_audio(path) else [])
            source['scenes'] = analysis_cache.remember(path, 'scenes', lambda: media.scene_changes(path))
            source['size'] = media.dimensions(path)
            transcript = self.transcripts.get(path)
            if transcript is None and self.whisper_model and media.has_audio(path):
                def recognise():
                    try:
                        self.status.emit('Konuşma yerel Whisper ile çözümleniyor…')
                        return local_transcribe(path, self.whisper_model, timed=True)
                    except Exception:
                        return None  # Editing still works from frames, silence and scenes.
                # The words depend on the model and the speech settings, so those are part of the entry name.
                name = ('transcript', self.whisper_model, speech_settings.language(), speech_settings.vocabulary())
                transcript = analysis_cache.remember(path, name, recognise, keep=lambda value: value is not None)
            source['transcript'] = transcript or []
            count = counts[index]
            for step in range(count):
                self.check_cancelled()
                at = max(0.0, min(duration - 0.05, duration * (step + 0.5) / count))
                target = Path(temp) / f"s{index}_f{step}.jpg"

                def grab(at=at, target=target):
                    if media.extract_frame(path, at, target).returncode == 0 and target.exists():
                        return target.read_bytes()
                    return None
                picture = analysis_cache.remember(path, ('frame', round(at, 3)), grab, keep=lambda value: value is not None)
                if picture is not None:
                    frames.append((index, at, picture))
        if not frames:
            raise RuntimeError("Videodan analiz karesi çıkarılamadı.")
        return frames

    def run(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="akis_edit_") as temp:
                frames = self.analyse(temp)
            prompt = edit_plan.build_prompt(self.request, self.sources, self.timeline, settings=self.settings)
            self.check_cancelled()
            self.status.emit("AI kurgu kararlarını veriyor…")
            text = self.call(self.request_fn, self.provider, self.api_key, self.model,
                             prompt + '\n' + FRAME_LABEL_NOTE,
                             [(frame_label(index, at), data) for index, at, data in frames],
                             instruction=edit_plan.INSTRUCTION)
            plan = edit_plan.parse_plan(text, [s['duration'] for s in self.sources],
                                        current_duration=edit_plan.primary_duration(self.timeline))
            note = fallback_note(text)
            if note:  # shown by edit_plan.describe with the other warnings
                plan.setdefault('warnings', []).insert(0, note)
            self.check_cancelled()
            self.completed.emit(plan, self.sources)
        except Exception as exc:
            self.report_error(exc)
