from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from timeline_model import Timeline, Track, Clip
from multitrack_widget import MultitrackWidget
import project_service
from media_service import MediaService
from timeline_render import TimelineRenderer, duration_frames
from frame_plan import audio_at

from PySide6.QtCore import QLocale, QSettings, QSize, QStandardPaths, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Akış Kurgu AI"
ORG_NAME = "AkisStudio"
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

EN_UI = {
    "Projeler": "Projects", "İlham": "Inspiration", "Şablonlar": "Templates",
    "Dışa aktarımlar": "Exports", "PROJE MEDYASI": "PROJECT MEDIA",
    "＋  Video ekle": "＋  Add video", "●  Yerel işleme": "●  Local processing",
    "Dışa aktarma bilgisayarınızda yapılır. AI yalnızca siz başlatınca çalışır.":
        "Export runs on your computer. AI only runs when you start it.",
    "Yeni proje": "New project", "Video ekleyerek başlayın": "Start by adding a video",
    "Proje aç": "Open project", "Projeyi kaydet": "Save project", "Dışa aktar  ↗": "Export  ↗",
    "Ses": "Audio", "Zaman çizelgesi": "Timeline", "Seçim: —": "Selection: —",
    "Başlangıç": "Start", "Bitiş": "End", "Aralığı sıfırla": "Reset range",
    "✦ AI Kurgu": "✦ AI Edit", "Düzenle": "Edit", "Yayın": "Publish",
    "Videonu anlat.\nAkış gerisini planlasın.": "Describe your video.\nLet Akış plan the rest.",
    "Temsilci kareleri analiz eder; en güçlü bölüm, başlık, açıklama ve kurgu ritmi önerir.":
        "Analyzes representative frames and suggests the strongest section, title, caption and pacing.",
    "YAPAY ZEKÂ HEDEFİ": "AI GOAL", "OPENAI AYARLARI": "OPENAI SETTINGS",
    "Windows'ta güvenli sakla": "Store securely in Windows", "Göster": "Show",
    "✦  AI ile kurguyu planla": "✦  Plan edit with AI",
    "Konuşmayı Türkçe metne çevir": "Transcribe speech",
    "AI kurgu planı burada görünecek.": "The AI edit plan will appear here.",
    "TUVAL ORANI": "CANVAS RATIO", "HIZ VE GEÇİŞ": "SPEED & TRANSITION",
    "Yumuşak giriş ve çıkış geçişi": "Soft fade in and out", "GÖRÜNÜM EFEKTİ": "LOOK EFFECT",
    "Yok": "None", "Sinematik": "Cinematic", "Siyah-beyaz": "Black & white", "Yumuşak": "Soft",
    "RENK VE IŞIK": "COLOR & LIGHT", "Parlaklık": "Brightness", "Kontrast": "Contrast",
    "Doygunluk": "Saturation", "Canlı görünüm uygula": "Apply vivid look",
    "Doğal görünüme dön": "Reset to natural", "BAŞLIK KATMANI": "TITLE LAYER",
    "Videoda görünecek kısa başlık": "Short title shown on video",
    "Başlık alt-orta güvenli bölgede, yüksek kontrastlı kutu içinde dışa aktarılır.":
        "The title is exported in a high-contrast box within the lower safe area.",
    "YAYIN PAKETİ": "PUBLISH PACKAGE", "Dışa aktarma profili": "Export profile",
    "Temel gürültü azaltma": "Basic noise reduction",
    "Ses yüksekliğini -14 LUFS'a normalleştir": "Normalize loudness to -14 LUFS",
    "AI Başlık": "AI Title", "Başlık önerisi": "Title suggestion", "Açıklama": "Caption",
    "Video açıklaması": "Video caption", "Etiketler": "Hashtags",
    "Yayın metnini panoya kopyala": "Copy publish text",
    "Instagram'a doğrudan yükleme bu sürümde yoktur. Videoyu filigransız dışa aktarabilir ve yayın paketini kopyalayabilirsiniz.":
        "Direct Instagram upload is not included. Export without a watermark and copy the publish package.",
    "1:1 · Kare": "1:1 · Square", "4:5 · Instagram gönderisi": "4:5 · Instagram post",
    "Kaynak oranı": "Source ratio",
}


def runtime_file(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def ffmpeg_path() -> str:
    bundled = runtime_file("ffmpeg.exe")
    if bundled.exists():
        return str(bundled)
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("FFmpeg bulunamadı. Uygulamayı yeniden kurmayı deneyin.")
    return found


def safe_filename(value: str) -> str:
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE).strip().replace(" ", "_")
    return value[:64] or "video"


def format_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{int(hours):02d}:{int(minutes):02d}:{sec:05.2f}"
    return f"{int(minutes):02d}:{sec:05.2f}"


def escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


@dataclass
class EditState:
    source: str = ""
    duration: float = 0.0
    start: float = 0.0
    end: float = 0.0
    aspect: str = "9:16 · Reels / Shorts"
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    speed: float = 1.0
    effect: str = "Yok"
    fade: bool = True
    export_profile: str = "Reels · 1080×1920"
    noise_reduction: bool = False
    loudness_normalization: bool = True
    overlay_text: str = ""
    ai_title: str = ""
    ai_caption: str = ""
    ai_hashtags: str = ""


class TimelineBar(QWidget):
    range_changed = Signal(float, float)
    seek_requested = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(96)
        self.setMouseTracking(True)
        self.duration = 1.0
        self.start = 0.0
        self.end = 1.0
        self.playhead = 0.0
        self._drag = ""

    def set_duration(self, seconds: float) -> None:
        self.duration = max(0.01, seconds)
        self.start = 0.0
        self.end = self.duration
        self.playhead = 0.0
        self.update()

    def set_range(self, start: float, end: float, emit: bool = False) -> None:
        start = max(0.0, min(float(start), self.duration))
        end = max(start + min(0.05, self.duration), min(float(end), self.duration))
        self.start, self.end = start, end
        self.update()
        if emit:
            self.range_changed.emit(start, end)

    def set_playhead(self, seconds: float) -> None:
        self.playhead = max(0.0, min(seconds, self.duration))
        self.update()

    def _x(self, value: float) -> float:
        return 18 + (self.width() - 36) * value / self.duration

    def _value(self, x: float) -> float:
        return max(0.0, min(self.duration, (x - 18) / max(1, self.width() - 36) * self.duration))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self.rect().adjusted(18, 28, -18, -24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#191b22"))
        p.drawRoundedRect(track, 10, 10)

        p.setPen(QPen(QColor("#343746"), 2))
        center = track.center().y()
        steps = max(32, self.width() // 10)
        for i in range(steps):
            x = track.left() + i * track.width() / max(1, steps - 1)
            wave = 7 + 10 * abs(math.sin(i * 1.71) * math.cos(i * 0.47))
            p.drawLine(int(x), int(center - wave), int(x), int(center + wave))

        sx, ex = self._x(self.start), self._x(self.end)
        selected = track.adjusted(int(sx - track.left()), 0, int(ex - track.right()), 0)
        p.setBrush(QColor(124, 92, 255, 54))
        p.setPen(QPen(QColor("#7c5cff"), 2))
        p.drawRoundedRect(selected, 9, 9)

        for x in (sx, ex):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#9b87ff"))
            p.drawRoundedRect(int(x - 5), track.top() - 5, 10, track.height() + 10, 5, 5)

        px = self._x(self.playhead)
        p.setPen(QPen(QColor("#ff4fa3"), 2))
        p.drawLine(int(px), track.top() - 12, int(px), track.bottom() + 8)
        path = QPainterPath()
        path.moveTo(px - 5, track.top() - 13)
        path.lineTo(px + 5, track.top() - 13)
        path.lineTo(px, track.top() - 6)
        path.closeSubpath()
        p.fillPath(path, QColor("#ff4fa3"))

        p.setPen(QColor("#8d91a4"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(18, self.height() - 6, format_time(self.start))
        end_text = format_time(self.end)
        p.drawText(self.width() - 18 - p.fontMetrics().horizontalAdvance(end_text), self.height() - 6, end_text)

    def mousePressEvent(self, event) -> None:
        x = event.position().x()
        if abs(x - self._x(self.start)) <= 12:
            self._drag = "start"
        elif abs(x - self._x(self.end)) <= 12:
            self._drag = "end"
        else:
            self._drag = "seek"
            self.seek_requested.emit(self._value(x))

    def mouseMoveEvent(self, event) -> None:
        value = self._value(event.position().x())
        if self._drag == "start":
            self.start = min(value, self.end - min(0.05, self.duration))
            self.range_changed.emit(self.start, self.end)
            self.update()
        elif self._drag == "end":
            self.end = max(value, self.start + min(0.05, self.duration))
            self.range_changed.emit(self.start, self.end)
            self.update()
        elif self._drag == "seek":
            self.seek_requested.emit(value)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag = ""


class AIWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key: str, model: str, video: str, duration: float, prompt: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.video = video
        self.duration = duration
        self.prompt = prompt

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
                    result = MediaService(ffmpeg_path()).extract_frame(self.video, at, target)
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
                        '{"summary":"", "title":"", "caption":"", "hashtags":[""], '
                        '"trim_start":0.0, "trim_end":0.0, "pacing":"", "filter":"natural|vivid|cinematic", '
                        '"notes":[""]}. trim_start/trim_end video sınırları içinde olsun.'
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
                plan = json.loads(match.group(0))
                self.completed.emit(plan)
        except Exception as exc:
            self.failed.emit(str(exc))


class TranscriptWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key: str, video: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.video = video

    def run(self) -> None:
        try:
            from openai import OpenAI

            self.status.emit("Ses parçası hazırlanıyor…")
            with tempfile.TemporaryDirectory(prefix="akis_audio_") as temp:
                audio = Path(temp) / "audio.mp3"
                result = MediaService(ffmpeg_path()).extract_audio(self.video, audio)
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


class ExportWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, state: EditState, output: str) -> None:
        super().__init__()
        self.state = state
        self.output = output

    def run(self) -> None:
        try:
            self.status.emit("Video işleniyor ve dışa aktarılıyor…")
            filters = []
            aspect_map = {
                "9:16 · Reels / Shorts": (1080, 1920),
                "16:9 · YouTube": (1920, 1080),
                "1:1 · Kare": (1080, 1080),
                "1:1 · Square": (1080, 1080),
                "4:5 · Instagram gönderisi": (1080, 1350),
                "4:5 · Instagram post": (1080, 1350),
            }
            profile_map = {
                "Reels · 1080×1920": (1080, 1920),
                "TikTok · 1080×1920": (1080, 1920),
                "YouTube · 1920×1080": (1920, 1080),
                "4K Dikey · 2160×3840": (2160, 3840),
                "4K UHD · 3840×2160": (3840, 2160),
            }
            if self.state.export_profile in profile_map:
                aspect_map[self.state.aspect] = profile_map[self.state.export_profile]
            if self.state.aspect in aspect_map:
                w, h = aspect_map[self.state.aspect]
                filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
                filters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
            else:
                filters.append("scale='min(1920,iw)':-2")

            brightness = self.state.brightness / 100.0
            contrast = 1.0 + self.state.contrast / 100.0
            saturation = 1.0 + self.state.saturation / 100.0
            filters.append(f"eq=brightness={brightness:.2f}:contrast={contrast:.2f}:saturation={saturation:.2f}")

            if self.state.effect in {"Sinematik", "Cinematic"}:
                filters.extend(["curves=preset=strong_contrast", "vignette=PI/5"])
            elif self.state.effect in {"Siyah-beyaz", "Black & white"}:
                filters.append("hue=s=0")
            elif self.state.effect in {"Yumuşak", "Soft"}:
                filters.append("gblur=sigma=0.6")

            source_duration = max(0.05, self.state.end - self.state.start)
            output_duration = source_duration / max(0.25, self.state.speed)
            if self.state.fade and output_duration >= 1.0:
                filters.append("fade=t=in:st=0:d=0.30")
                filters.append(f"fade=t=out:st={max(0.31, output_duration - 0.30):.3f}:d=0.30")

            if abs(self.state.speed - 1.0) > 0.001:
                filters.append(f"setpts=PTS/{self.state.speed:.3f}")

            if self.state.overlay_text.strip():
                text = escape_drawtext(self.state.overlay_text.strip())
                font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeuib.ttf"
                fontfile = str(font).replace("\\", "/").replace(":", r"\:")
                filters.append(
                    "drawtext="
                    f"fontfile='{fontfile}':text='{text}':fontcolor=white:fontsize=h/18:"
                    "x=(w-text_w)/2:y=h*0.78:box=1:boxcolor=black@0.52:boxborderw=18"
                )

            duration = source_duration
            audio_filters = []
            speed_left = self.state.speed
            while speed_left > 2.0:
                audio_filters.append("atempo=2.0")
                speed_left /= 2.0
            while speed_left < 0.5:
                audio_filters.append("atempo=0.5")
                speed_left /= 0.5
            if abs(speed_left - 1.0) > 0.001:
                audio_filters.append(f"atempo={speed_left:.3f}")
            if self.state.noise_reduction:
                audio_filters.append("afftdn=nf=-25")
            if self.state.loudness_normalization:
                audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
            cmd = [
                ffmpeg_path(), "-y", "-ss", f"{self.state.start:.3f}", "-i", self.state.source,
                "-t", f"{duration:.3f}", "-vf", ",".join(filters),
            ]
            if audio_filters:
                cmd.extend(["-af", ",".join(audio_filters)])
            crf = "16" if self.state.export_profile.startswith("4K") else "18"
            cmd.extend([
                "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", self.output,
            ])
            result = MediaService(cmd[0]).run(cmd[1:], text=True)
            if result.returncode != 0:
                tail = "\n".join(result.stderr.splitlines()[-8:])
                raise RuntimeError(f"FFmpeg dışa aktarma hatası:\n{tail}")
            self.completed.emit(self.output)
        except Exception as exc:
            self.failed.emit(str(exc))


class TimelineRenderWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, timeline, output, size, frame=None):
        super().__init__()
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.output, self.size, self.frame = output, size, frame

    def run(self):
        try:
            renderer = TimelineRenderer(MediaService(ffmpeg_path()), self.size)
            if self.frame is None:
                renderer.export(self.timeline, self.output)
            else:
                renderer.preview(self.timeline, self.frame, self.output)
            self.completed.emit(self.output)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = EditState()
        self.multitrack = Timeline.from_legacy({})
        self.timeline_frame = 0
        self.preview_worker = None
        self.preview_pending = None
        self.preview_dir = tempfile.TemporaryDirectory(prefix='akis_preview_')
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self.advance_timeline)
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.project_path = ""
        self._pending_project: dict | None = None
        self.worker: QThread | None = None
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1180, 760)
        self.resize(1500, 920)
        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon(str(runtime_file('app.ico'))))

        self.audio = QAudioOutput()
        self.audio.setVolume(0.8)
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)
        self.preview_audio_output = QAudioOutput()
        self.preview_audio = QMediaPlayer()
        self.preview_audio.setAudioOutput(self.preview_audio_output)
        self.preview_audio_source = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_sidebar())
        layout.addWidget(self.build_workspace(), 1)

        self.player.durationChanged.connect(self.on_duration)
        self.player.positionChanged.connect(self.on_position)
        self.player.playbackStateChanged.connect(self.on_play_state)
        self.player.errorOccurred.connect(lambda _e, msg: self.set_status(f"Oynatıcı: {msg}"))
        self.load_key()
        self.apply_language(self.settings.value("language", self.system_language_code()))
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30_000)
        self.autosave_timer.timeout.connect(self.autosave_project)
        self.autosave_timer.start()
        self.set_status("Bir video sürükleyin veya “Video ekle” düğmesini kullanın.")

    def make_icon(self) -> QIcon:
        pix = QPixmap(96, 96)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QColor("#7c5cff")
        p.setBrush(gradient)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(8, 8, 80, 80, 24, 24)
        # Original interlocking A/flow mark for Akış Kurgu.
        p.setBrush(QColor("white"))
        path = QPainterPath()
        path.moveTo(25, 68)
        path.lineTo(45, 27)
        path.lineTo(53, 27)
        path.lineTo(73, 68)
        path.lineTo(62, 68)
        path.lineTo(49, 40)
        path.lineTo(36, 68)
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(QPen(QColor("#d8ccff"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(39, 58, 59, 50)
        p.end()
        return QIcon(pix)

    def build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        v = QVBoxLayout(side)
        v.setContentsMargins(18, 22, 18, 18)
        v.setSpacing(8)
        brand = QLabel("AKIŞ  <span style='color:#9b87ff'>KURGU</span>")
        brand.setTextFormat(Qt.TextFormat.RichText)
        brand.setObjectName("brand")
        v.addWidget(brand)
        subtitle = QLabel("AI Video Studio")
        subtitle.setObjectName("muted")
        v.addWidget(subtitle)
        v.addSpacing(24)

        for index, (text, icon) in enumerate([
            ("Projeler", "▦"), ("İlham", "✦"), ("Şablonlar", "◈"), ("Dışa aktarımlar", "⇧")
        ]):
            button = QPushButton(f"{icon}   {text}")
            button.setProperty("nav", True)
            button.setProperty("active", index == 0)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if index == 0:
                button.clicked.connect(lambda: self.set_status("Proje düzenleyicisi açık."))
            else:
                button.clicked.connect(lambda _=False, t=text: self.set_status(f"{t} bölümü bu ilk sürümde yakında genişletilecek."))
            v.addWidget(button)

        v.addSpacing(20)
        label = QLabel("PROJE MEDYASI")
        label.setObjectName("sectionLabel")
        v.addWidget(label)
        self.media_list = QListWidget()
        self.media_list.setObjectName("mediaList")
        self.media_list.setMinimumHeight(160)
        v.addWidget(self.media_list, 1)
        add = QPushButton("＋  Video ekle")
        add.setObjectName("secondary")
        add.clicked.connect(self.choose_video)
        v.addWidget(add)
        self.language = QComboBox()
        self.language.addItem("Türkçe", "tr")
        self.language.addItem("English", "en")
        selected_language = self.settings.value("language", self.system_language_code())
        self.language.setCurrentIndex(0 if selected_language == "tr" else 1)
        self.language.currentIndexChanged.connect(self.change_language)
        v.addWidget(self.language)
        v.addSpacing(12)

        local = QFrame()
        local.setObjectName("privacyCard")
        lv = QVBoxLayout(local)
        lv.setContentsMargins(12, 10, 12, 10)
        title = QLabel("●  Yerel işleme")
        title.setObjectName("localTitle")
        lv.addWidget(title)
        note = QLabel("Dışa aktarma bilgisayarınızda yapılır. AI yalnızca siz başlatınca çalışır.")
        note.setWordWrap(True)
        note.setObjectName("mutedSmall")
        lv.addWidget(note)
        v.addWidget(local)
        return side

    def build_workspace(self) -> QWidget:
        shell = QWidget()
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(22, 16, 22, 16)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.project_title = QLabel("Yeni proje")
        self.project_title.setObjectName("projectTitle")
        self.project_subtitle = QLabel("Video ekleyerek başlayın")
        self.project_subtitle.setObjectName("muted")
        title_box.addWidget(self.project_title)
        title_box.addWidget(self.project_subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")
        header.addWidget(self.status_label)
        open_project = QPushButton("Proje aç")
        open_project.setObjectName("ghost")
        open_project.clicked.connect(self.open_project)
        header.addWidget(open_project)
        save_project = QPushButton("Projeyi kaydet")
        save_project.setObjectName("secondary")
        save_project.clicked.connect(self.save_project)
        header.addWidget(save_project)
        export = QPushButton("Dışa aktar  ↗")
        export.setObjectName("primary")
        export.clicked.connect(self.export_video)
        header.addWidget(export)
        outer.addLayout(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self.build_editor())
        split.addWidget(self.build_inspector())
        split.setSizes([900, 390])
        outer.addWidget(split, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        outer.addWidget(self.progress)
        return shell

    def build_editor(self) -> QWidget:
        area = QFrame()
        area.setObjectName("editor")
        v = QVBoxLayout(area)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(12)

        self.video = QLabel('Video ekleyin / Add a video')
        self.video.setObjectName("video")
        self.video.setMinimumSize(520, 360)
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.video, 1)

        controls = QHBoxLayout()
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("roundButton")
        self.play_button.setFixedSize(40, 40)
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)
        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setObjectName("mono")
        controls.addWidget(self.time_label)
        controls.addStretch()
        volume_label = QLabel("Ses")
        volume_label.setObjectName("muted")
        controls.addWidget(volume_label)
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(80)
        volume.setFixedWidth(100)
        volume.valueChanged.connect(lambda val: self.audio.setVolume(val / 100))
        controls.addWidget(volume)
        v.addLayout(controls)

        timeline_header = QHBoxLayout()
        timeline_header.addWidget(QLabel("Zaman çizelgesi"))
        timeline_header.addStretch()
        self.selection_label = QLabel("Seçim: —")
        self.selection_label.setObjectName("muted")
        timeline_header.addWidget(self.selection_label)
        v.addLayout(timeline_header)
        tools = QHBoxLayout()
        for label, action in [('＋ İz', self.add_track), ('− İz', self.remove_track),
                              ('＋ Medya', self.add_timeline_media), ('Böl', self.split_clip),
                              ('Ripple sil', self.ripple_delete)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            tools.addWidget(button)
        zoom = QSlider(Qt.Orientation.Horizontal)
        zoom.setRange(1, 100)
        zoom.setValue(20)
        zoom.setFixedWidth(90)
        zoom.valueChanged.connect(self.timeline_zoom)
        tools.addWidget(QLabel('Yakınlık'))
        tools.addWidget(zoom)
        v.addLayout(tools)
        self.multitrack_view = MultitrackWidget(self.multitrack)
        self.multitrack_view.seek.connect(self.seek_timeline)
        v.addWidget(self.multitrack_view)
        self.timeline = TimelineBar()
        self.timeline.range_changed.connect(self.on_timeline_range)
        self.timeline.seek_requested.connect(lambda sec: self.seek_timeline(round(sec * self.multitrack.fps_num / self.multitrack.fps_den)))
        v.addWidget(self.timeline)

        trims = QHBoxLayout()
        trims.addWidget(QLabel("Başlangıç"))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setDecimals(2)
        self.start_spin.setSuffix(" sn")
        self.start_spin.valueChanged.connect(self.on_spin_range)
        trims.addWidget(self.start_spin)
        trims.addWidget(QLabel("Bitiş"))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setDecimals(2)
        self.end_spin.setSuffix(" sn")
        self.end_spin.valueChanged.connect(self.on_spin_range)
        trims.addWidget(self.end_spin)
        trims.addStretch()
        reset = QPushButton("Aralığı sıfırla")
        reset.setObjectName("ghost")
        reset.clicked.connect(self.reset_range)
        trims.addWidget(reset)
        v.addLayout(trims)
        return area

    def build_inspector(self) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("inspector")
        wrapper.setMinimumWidth(350)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_ai_tab(), "✦ AI Kurgu")
        self.tabs.addTab(self.build_edit_tab(), "Düzenle")
        self.tabs.addTab(self.build_publish_tab(), "Yayın")
        layout.addWidget(self.tabs)
        return wrapper

    def scroll_page(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def build_ai_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(12)

        hero = QLabel("Videonu anlat.\nAkış gerisini planlasın.")
        hero.setObjectName("aiHero")
        v.addWidget(hero)
        desc = QLabel("Temsilci kareleri analiz eder; en güçlü bölüm, başlık, açıklama ve kurgu ritmi önerir.")
        desc.setWordWrap(True)
        desc.setObjectName("muted")
        v.addWidget(desc)

        v.addWidget(self.section("YAPAY ZEKÂ HEDEFİ"))
        self.ai_prompt = QPlainTextEdit()
        self.ai_prompt.setPlaceholderText("Örn. İlk 2 saniyesi güçlü, dinamik bir Reels kurgusu. Ürün net görünsün, ton güven veren olsun.")
        self.ai_prompt.setPlainText("İlk saniyeleri güçlü, tempolu ve profesyonel bir Reels kurgusu oluştur. En ilgi çekici bölümü öne çıkar.")
        self.ai_prompt.setFixedHeight(112)
        v.addWidget(self.ai_prompt)

        v.addWidget(self.section("OPENAI AYARLARI"))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-…")
        v.addWidget(self.api_key)
        key_row = QHBoxLayout()
        self.remember_key = QCheckBox("Windows'ta güvenli sakla")
        key_row.addWidget(self.remember_key)
        key_row.addStretch()
        reveal = QToolButton()
        reveal.setText("Göster")
        reveal.clicked.connect(self.toggle_key)
        key_row.addWidget(reveal)
        v.addLayout(key_row)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(["gpt-5.5", "gpt-5.5-mini"])
        self.model.setCurrentText("gpt-5.5")
        v.addWidget(self.model)

        analyze = QPushButton("✦  AI ile kurguyu planla")
        analyze.setObjectName("primaryLarge")
        analyze.clicked.connect(self.run_ai)
        v.addWidget(analyze)
        transcript = QPushButton("Konuşmayı Türkçe metne çevir")
        transcript.setObjectName("secondary")
        transcript.clicked.connect(self.run_transcript)
        v.addWidget(transcript)

        self.ai_result = QPlainTextEdit()
        self.ai_result.setReadOnly(True)
        self.ai_result.setPlaceholderText("AI kurgu planı burada görünecek.")
        self.ai_result.setMinimumHeight(190)
        v.addWidget(self.ai_result)
        v.addStretch()
        return self.scroll_page(content)

    def section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def build_edit_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(14)
        v.addWidget(self.section("TUVAL ORANI"))
        self.aspect = QComboBox()
        self.aspect.addItems(["9:16 · Reels / Shorts", "16:9 · YouTube", "1:1 · Kare", "4:5 · Instagram gönderisi", "Kaynak oranı"])
        self.aspect.currentTextChanged.connect(lambda text: setattr(self.state, "aspect", text))
        v.addWidget(self.aspect)

        v.addWidget(self.section("HIZ VE GEÇİŞ"))
        self.speed = QComboBox()
        self.speed.addItems(["0.50×", "0.75×", "1.00×", "1.25×", "1.50×", "2.00×"])
        self.speed.setCurrentText("1.00×")
        self.speed.currentTextChanged.connect(lambda text: setattr(self.state, "speed", float(text.replace("×", ""))))
        v.addWidget(self.speed)
        self.fade = QCheckBox("Yumuşak giriş ve çıkış geçişi")
        self.fade.setChecked(True)
        self.fade.toggled.connect(lambda checked: setattr(self.state, "fade", checked))
        v.addWidget(self.fade)

        v.addWidget(self.section("GÖRÜNÜM EFEKTİ"))
        self.effect = QComboBox()
        self.effect.addItems(["Yok", "Sinematik", "Siyah-beyaz", "Yumuşak"])
        self.effect.currentTextChanged.connect(lambda text: setattr(self.state, "effect", text))
        v.addWidget(self.effect)

        v.addWidget(self.section("RENK VE IŞIK"))
        self.brightness = self.add_slider(v, "Parlaklık", -50, 50, lambda x: setattr(self.state, "brightness", x))
        self.contrast = self.add_slider(v, "Kontrast", -50, 50, lambda x: setattr(self.state, "contrast", x))
        self.saturation = self.add_slider(v, "Doygunluk", -50, 50, lambda x: setattr(self.state, "saturation", x))

        vivid = QPushButton("Canlı görünüm uygula")
        vivid.setObjectName("secondary")
        vivid.clicked.connect(lambda: self.apply_preset(5, 10, 18))
        v.addWidget(vivid)
        natural = QPushButton("Doğal görünüme dön")
        natural.setObjectName("ghost")
        natural.clicked.connect(lambda: self.apply_preset(0, 0, 0))
        v.addWidget(natural)

        v.addWidget(self.section("BAŞLIK KATMANI"))
        self.overlay = QLineEdit()
        self.overlay.setPlaceholderText("Videoda görünecek kısa başlık")
        self.overlay.textChanged.connect(lambda text: setattr(self.state, "overlay_text", text))
        v.addWidget(self.overlay)
        hint = QLabel("Başlık alt-orta güvenli bölgede, yüksek kontrastlı kutu içinde dışa aktarılır.")
        hint.setWordWrap(True)
        hint.setObjectName("mutedSmall")
        v.addWidget(hint)
        v.addStretch()
        return self.scroll_page(content)

    def add_slider(self, layout: QVBoxLayout, name: str, low: int, high: int, callback) -> QSlider:
        row = QHBoxLayout()
        label = QLabel(name)
        value = QLabel("0")
        value.setObjectName("mono")
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value)
        layout.addLayout(row)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.valueChanged.connect(lambda x: (value.setText(f"{x:+d}"), callback(x)))
        layout.addWidget(slider)
        return slider

    def build_publish_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(12)
        v.addWidget(self.section("YAYIN PAKETİ"))
        v.addWidget(QLabel("Dışa aktarma profili"))
        self.export_profile = QComboBox()
        self.export_profile.addItems([
            "Reels · 1080×1920", "TikTok · 1080×1920", "YouTube · 1920×1080",
            "4K Dikey · 2160×3840", "4K UHD · 3840×2160",
        ])
        self.export_profile.currentTextChanged.connect(lambda text: setattr(self.state, "export_profile", text))
        v.addWidget(self.export_profile)
        self.noise_reduction = QCheckBox("Temel gürültü azaltma")
        self.noise_reduction.toggled.connect(lambda checked: setattr(self.state, "noise_reduction", checked))
        v.addWidget(self.noise_reduction)
        self.loudness = QCheckBox("Ses yüksekliğini -14 LUFS'a normalleştir")
        self.loudness.setChecked(True)
        self.loudness.toggled.connect(lambda checked: setattr(self.state, "loudness_normalization", checked))
        v.addWidget(self.loudness)
        v.addWidget(QLabel("AI Başlık"))
        self.publish_title = QLineEdit()
        self.publish_title.setPlaceholderText("Başlık önerisi")
        v.addWidget(self.publish_title)
        v.addWidget(QLabel("Açıklama"))
        self.publish_caption = QPlainTextEdit()
        self.publish_caption.setPlaceholderText("Video açıklaması")
        self.publish_caption.setMinimumHeight(140)
        v.addWidget(self.publish_caption)
        v.addWidget(QLabel("Etiketler"))
        self.publish_tags = QPlainTextEdit()
        self.publish_tags.setPlaceholderText("#reels #video")
        self.publish_tags.setMaximumHeight(100)
        v.addWidget(self.publish_tags)
        copy = QPushButton("Yayın metnini panoya kopyala")
        copy.setObjectName("secondary")
        copy.clicked.connect(self.copy_publish_text)
        v.addWidget(copy)
        note = QLabel("Instagram'a doğrudan yükleme bu sürümde yoktur. Videoyu filigransız dışa aktarabilir ve yayın paketini kopyalayabilirsiniz.")
        note.setWordWrap(True)
        note.setObjectName("mutedSmall")
        v.addWidget(note)
        v.addStretch()
        return self.scroll_page(content)

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Video seç", "", "Video (*.mp4 *.mov *.mkv *.webm *.avi *.m4v)")
        if path:
            self.load_video(path)

    def load_video(self, path: str) -> None:
        file = Path(path)
        if file.suffix.lower() not in VIDEO_EXTS or not file.exists():
            QMessageBox.warning(self, APP_NAME, "Desteklenen bir video dosyası seçin.")
            return
        self.state = EditState(source=str(file), aspect=self.aspect.currentText())
        if not self._pending_project:
            self.multitrack = Timeline.from_legacy({})
            self.multitrack_view.set_model(self.multitrack)
        self.player.setSource(QUrl.fromLocalFile(str(file)))
        self.project_title.setText(file.stem)
        self.project_subtitle.setText(f"{file.suffix.upper().lstrip('.')} · {file.stat().st_size / 1024 / 1024:.1f} MB")
        self.media_list.clear()
        item = QListWidgetItem(f"▣  {file.name}")
        item.setToolTip(str(file))
        self.media_list.addItem(item)
        self.set_status("Video hazır. Zaman çizelgesinden aralığı ayarlayabilirsiniz.")

    def on_duration(self, milliseconds: int) -> None:
        if milliseconds <= 0:
            return
        duration = milliseconds / 1000.0
        self.state.duration = duration
        self.state.start = 0.0
        self.state.end = duration
        self.timeline.set_duration(duration)
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.start_spin.setRange(0, duration)
        self.end_spin.setRange(0, duration)
        self.start_spin.setValue(0)
        self.end_spin.setValue(duration)
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        self.update_range_label()
        if self._pending_project:
            pending = self._pending_project
            self._pending_project = None
            self.apply_project_state(pending)
        elif not any(t.clips for t in self.multitrack.tracks):
            self.multitrack = Timeline.from_legacy(asdict(self.state))
            self.multitrack_view.set_model(self.multitrack)
            self.seek_timeline(0)

    def on_position(self, milliseconds: int) -> None:
        seconds = milliseconds / 1000.0
        source_frame = round(seconds * self.multitrack.fps_num / self.multitrack.fps_den)
        for track in self.multitrack.tracks:
            if track.kind == 'video':
                clip = next((c for c in track.clips if c.source == self.state.source and c.source_in <= source_frame < c.source_in + c.length), None)
                if clip:
                    self.multitrack_view.playhead = clip.start + source_frame - clip.source_in
                    self.multitrack_view.update()
                    break
        self.timeline.set_playhead(seconds)
        self.time_label.setText(f"{format_time(seconds)} / {format_time(self.state.duration)}")
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and self.state.end and seconds >= self.state.end:
            self.player.pause()
            self.player.setPosition(int(self.state.start * 1000))

    def on_play_state(self, state) -> None:
        self.play_button.setText("❚❚" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")

    def toggle_play(self) -> None:
        if not self.state.source:
            self.choose_video()
            return
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.preview_audio.pause()
            self.play_button.setText('▶')
        else:
            self.play_timer.start(max(1, round(1000 * self.multitrack.fps_den / self.multitrack.fps_num)))
            self.sync_timeline_audio(force=True)
            self.play_button.setText('❚❚')

    def on_timeline_range(self, start: float, end: float) -> None:
        self.state.start, self.state.end = start, end
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.start_spin.setValue(start)
        self.end_spin.setValue(end)
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        self.update_range_label()

    def on_spin_range(self) -> None:
        if not self.state.duration:
            return
        start = min(self.start_spin.value(), self.end_spin.value() - 0.05)
        end = max(self.end_spin.value(), start + 0.05)
        self.state.start, self.state.end = start, end
        self.timeline.set_range(start, end)
        self.update_range_label()

    def update_range_label(self) -> None:
        selected = max(0, self.state.end - self.state.start)
        self.selection_label.setText(f"Seçim: {format_time(selected)}")

    def reset_range(self) -> None:
        if not self.state.duration:
            return
        self.timeline.set_range(0, self.state.duration, emit=True)

    def api_credentials(self) -> tuple[str, str] | None:
        key = self.api_key.text().strip()
        model = self.model.currentText().strip()
        if not key:
            QMessageBox.information(self, APP_NAME, "AI özellikleri için OpenAI API anahtarınızı girin.")
            return None
        if not model:
            QMessageBox.information(self, APP_NAME, "Bir OpenAI modeli belirtin.")
            return None
        if self.remember_key.isChecked():
            self.save_key(key)
        return key, model

    def save_key(self, key: str) -> None:
        try:
            import keyring
            keyring.set_password(APP_NAME, "openai_api_key", key)
            self.settings.setValue("remember_key", True)
        except Exception as exc:
            self.set_status(f"Anahtar güvenli kasaya kaydedilemedi: {exc}")

    def load_key(self) -> None:
        if not self.settings.value("remember_key", False, type=bool):
            return
        try:
            import keyring
            key = keyring.get_password(APP_NAME, "openai_api_key")
            if key:
                self.api_key.setText(key)
                self.remember_key.setChecked(True)
        except Exception:
            pass

    def toggle_key(self) -> None:
        mode = self.api_key.echoMode()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Normal if mode == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password)

    def run_ai(self) -> None:
        if not self.ensure_video():
            return
        credentials = self.api_credentials()
        if not credentials:
            return
        key, model = credentials
        self.begin_work("AI analizi başlatılıyor…")
        self.worker = AIWorker(key, model, self.state.source, self.state.duration, self.ai_prompt.toPlainText().strip())
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_ai_plan)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.start()

    def on_ai_plan(self, plan: dict) -> None:
        start = float(plan.get("trim_start", 0) or 0)
        end = float(plan.get("trim_end", self.state.duration) or self.state.duration)
        if 0 <= start < end <= self.state.duration:
            self.timeline.set_range(start, end, emit=True)

        title = str(plan.get("title", "")).strip()
        caption = str(plan.get("caption", "")).strip()
        hashtags = plan.get("hashtags", [])
        if isinstance(hashtags, str):
            tags = hashtags
        else:
            tags = " ".join("#" + str(x).lstrip("#") for x in hashtags)
        self.publish_title.setText(title)
        self.publish_caption.setPlainText(caption)
        self.publish_tags.setPlainText(tags)
        if title:
            self.overlay.setText(title[:70])

        filter_name = str(plan.get("filter", "natural"))
        if filter_name == "vivid":
            self.apply_preset(5, 10, 18)
        elif filter_name == "cinematic":
            self.apply_preset(-3, 16, -6)

        notes = plan.get("notes", [])
        if isinstance(notes, list):
            notes = "\n".join(f"• {x}" for x in notes)
        display = (
            f"ÖZET\n{plan.get('summary', '')}\n\n"
            f"RİTİM\n{plan.get('pacing', '')}\n\n"
            f"ÖNERİLER\n{notes}"
        )
        self.ai_result.setPlainText(display.strip())
        self.finish_work("AI kurgu planı uygulandı. Dilerseniz ayarları elle değiştirebilirsiniz.")

    def run_transcript(self) -> None:
        if not self.ensure_video():
            return
        credentials = self.api_credentials()
        if not credentials:
            return
        self.begin_work("Ses hazırlanıyor…")
        self.worker = TranscriptWorker(credentials[0], self.state.source)
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_transcript)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.start()

    def on_transcript(self, text: str) -> None:
        self.ai_result.setPlainText("KONUŞMA METNİ\n\n" + text)
        if not self.publish_caption.toPlainText().strip():
            self.publish_caption.setPlainText(text)
        self.finish_work("Türkçe konuşma metni hazır.")

    def export_video(self) -> None:
        if not self.ensure_video():
            return
        default = safe_filename(self.project_title.text()) + "_akis.mp4"
        path, _ = QFileDialog.getSaveFileName(self, "Videoyu dışa aktar", str(Path.home() / "Videos" / default), "MP4 Video (*.mp4)")
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path += ".mp4"
        self.state.overlay_text = self.overlay.text()
        self.state.aspect = self.aspect.currentText()
        self.state.export_profile = self.export_profile.currentText()
        self.begin_work("Dışa aktarma hazırlanıyor…")
        self.worker = TimelineRenderWorker(self.multitrack, path, self.canvas_size())
        self.worker.completed.connect(self.on_exported)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.start()

    def on_exported(self, path: str) -> None:
        self.finish_work("Dışa aktarma tamamlandı.")
        QMessageBox.information(self, APP_NAME, f"Video başarıyla oluşturuldu:\n{path}")

    def apply_preset(self, brightness: int, contrast: int, saturation: int) -> None:
        self.brightness.setValue(brightness)
        self.contrast.setValue(contrast)
        self.saturation.setValue(saturation)
        self.set_status("Renk görünümü güncellendi; dışa aktarmada uygulanacak.")

    def copy_publish_text(self) -> None:
        text = "\n\n".join(filter(None, [
            self.publish_title.text().strip(),
            self.publish_caption.toPlainText().strip(),
            self.publish_tags.toPlainText().strip(),
        ]))
        QApplication.clipboard().setText(text)
        self.set_status("Yayın metni panoya kopyalandı.")

    def ensure_video(self) -> bool:
        if not self.state.source or not self.state.duration:
            QMessageBox.information(self, APP_NAME, "Önce bir video ekleyin ve yüklenmesini bekleyin.")
            return False
        return True

    def begin_work(self, text: str) -> None:
        self.progress.show()
        self.set_status(text)

    def finish_work(self, text: str) -> None:
        self.progress.hide()
        self.set_status(text)
        self.worker = None

    def on_worker_error(self, message: str) -> None:
        self.progress.hide()
        self.worker = None
        self.set_status("İşlem tamamlanamadı.")
        QMessageBox.critical(self, APP_NAME, message)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def timeline_zoom(self, value):
        self.multitrack_view.zoom = value / 10
        self.multitrack_view.update()

    def selected_clip(self):
        selected = self.multitrack_view.selected
        if not selected:
            return None, None
        track = self.multitrack.tracks[selected[0]]
        return track, track.find(selected[1])

    def add_track(self):
        kind, ok = QInputDialog.getItem(self, 'İz ekle / Add track', 'Tür / Type', ['video', 'audio', 'text', 'overlay'], 0, False)
        if ok:
            self.multitrack.tracks.append(Track(kind, f'{kind.title()} {len(self.multitrack.tracks)+1}'))
            self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
            self.multitrack_view.update()

    def remove_track(self):
        selected = self.multitrack_view.selected
        if not selected:
            self.set_status('Silinecek izi seçmek için klibe tıklayın.')
            return
        self.multitrack.tracks.pop(selected[0])
        self.multitrack_view.selected = None
        self.multitrack_view.update()

    def add_timeline_media(self):
        track, _ = self.selected_clip()
        if track is None:
            self.set_status('Önce hedef izde bir klip seçin.')
            return
        if track.kind not in ('video', 'audio', 'overlay'):
            self.set_status('Bu sürümde medya yalnızca video/ses izine eklenir.')
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Medya seç', '', 'Media (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mp3 *.wav *.m4a)')
        if not path:
            return
        # Probe without decoding the file or relying on an additional ffprobe binary.
        try:
            seconds = MediaService(ffmpeg_path()).duration(path)
        except ValueError:
            QMessageBox.warning(self, APP_NAME, 'Medya süresi okunamadı.')
            return
        frames = max(1, round(seconds * self.multitrack.fps_num / self.multitrack.fps_den))
        start = max((c.end for c in track.clips), default=0)
        track.add(Clip(path, start, frames, source_length=frames))
        self.multitrack_view.update()

    def split_clip(self):
        track, clip = self.selected_clip()
        if clip:
            try:
                track.split(clip.id, self.multitrack_view.playhead)
                self.multitrack_view.update()
            except ValueError as exc:
                self.set_status(str(exc))

    def ripple_delete(self):
        track, clip = self.selected_clip()
        if clip:
            track.ripple_delete(clip.id)
            self.multitrack_view.selected = None
            self.multitrack_view.update()

    def seek_timeline(self, frame):
        total = duration_frames(self.multitrack)
        if not total:
            return
        self.timeline_frame = min(max(0, frame), total - 1)
        self.sync_timeline_audio()
        self.multitrack_view.playhead = self.timeline_frame
        self.multitrack_view.update()
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        self.time_label.setText(f'{format_time(self.timeline_frame/fps)} / {format_time(total/fps)}')
        if self.preview_worker and self.preview_worker.isRunning():
            self.preview_pending = self.timeline_frame
            return
        w, h = self.canvas_size()
        scale = min(1, 480/max(w, h))
        size = (max(2, int(w*scale)//2*2), max(2, int(h*scale)//2*2))
        path = str(Path(self.preview_dir.name) / 'frame.png')
        self.preview_worker = TimelineRenderWorker(self.multitrack, path, size, self.timeline_frame)
        self.preview_worker.completed.connect(self.show_timeline_frame)
        self.preview_worker.failed.connect(self.set_status)
        self.preview_worker.finished.connect(self.next_preview)
        self.preview_worker.start()

    def show_timeline_frame(self, path):
        pixmap = QPixmap(path)
        self.video.setPixmap(pixmap.scaled(self.video.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def next_preview(self):
        self.preview_worker = None
        if self.preview_pending is not None:
            frame, self.preview_pending = self.preview_pending, None
            self.seek_timeline(frame)

    def advance_timeline(self):
        if self.timeline_frame + 1 >= duration_frames(self.multitrack):
            self.play_timer.stop()
            self.preview_audio.pause()
            self.play_button.setText('▶')
        else:
            self.seek_timeline(self.timeline_frame + 1)

    def canvas_size(self):
        aspect = self.aspect.currentText()
        if aspect.startswith('16:9'):
            return (1920, 1080)
        if aspect.startswith('1:1'):
            return (1080, 1080)
        if aspect.startswith('4:5'):
            return (1080, 1350)
        if aspect in ('Kaynak oranı', 'Source ratio'):
            for track in self.multitrack.tracks:
                if track.kind == 'video' and track.clips:
                    return MediaService(ffmpeg_path()).dimensions(track.clips[0].source)
            raise ValueError('Kaynak video bulunamadı.')
        return (1080, 1920)

    def sync_timeline_audio(self, force=False):
        if not self.play_timer.isActive():
            return
        layer = audio_at(self.multitrack, self.timeline_frame)
        if layer is None:
            self.preview_audio.pause()
            self.preview_audio_source = None
            return
        position = round(layer.source_frame * 1000 * self.multitrack.fps_den / self.multitrack.fps_num)
        if self.preview_audio_source != layer.source:
            self.preview_audio_source = layer.source
            self.preview_audio.setSource(QUrl.fromLocalFile(layer.source))
            force = True
        if force or abs(self.preview_audio.position() - position) > 250:
            self.preview_audio.setPosition(position)
        self.preview_audio.play()

    def project_document(self) -> dict:
        return {
            "format": "akis-kurgu-project",
            "version": project_service.CURRENT_VERSION,
            "saved_at": datetime.now().astimezone().isoformat(),
            "state": asdict(self.state),
            "timeline": self.multitrack.to_dict(),
            "publish": {
                "title": self.publish_title.text(),
                "caption": self.publish_caption.toPlainText(),
                "hashtags": self.publish_tags.toPlainText(),
            },
            "ai_prompt": self.ai_prompt.toPlainText(),
        }

    def write_project(self, path: str, snapshot: bool = False) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        document = self.project_document()
        project_service.save(target, document)
        if snapshot:
            versions = target.parent / f"{target.name}.versions"
            versions.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            (versions / f"{stamp}.json").write_text(
                json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def save_project(self) -> None:
        if not self.state.source:
            QMessageBox.information(self, APP_NAME, "Kaydetmek için önce bir video ekleyin.")
            return
        path = self.project_path
        if not path:
            default = safe_filename(self.project_title.text()) + ".akis.json"
            path, _ = QFileDialog.getSaveFileName(
                self, "Projeyi kaydet", str(Path.home() / "Documents" / default), "Akış projesi (*.akis.json)"
            )
        if not path:
            return
        if not path.lower().endswith(".akis.json"):
            path += ".akis.json"
        self.write_project(path, snapshot=True)
        self.project_path = path
        self.set_status("Proje ve sürüm anlık görüntüsü kaydedildi.")

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Proje aç", "", "Akış projesi (*.akis.json);;JSON (*.json)"
        )
        if not path:
            return
        try:
            document = project_service.load(path)
            if document.get("format") != "akis-kurgu-project":
                raise ValueError("Bu dosya desteklenen bir Akış Kurgu projesi değil.")
            source = document.get("state", {}).get("source", "")
            source_path = Path(source)
            if source and not source_path.is_absolute():
                source_path = (Path(path).parent / source_path).resolve()
                document.setdefault("state", {})["source"] = str(source_path)
            if not source or not source_path.exists():
                raise FileNotFoundError("Projede kullanılan kaynak video bulunamadı.")
            self.project_path = path
            self._pending_project = document
            self.load_video(str(source_path))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def apply_project_state(self, document: dict) -> None:
        raw = document.get("state", {})
        allowed = set(EditState.__dataclass_fields__)
        merged = {key: value for key, value in raw.items() if key in allowed}
        merged["duration"] = self.state.duration
        self.state = EditState(**merged)
        self.multitrack = Timeline.from_dict(document['timeline']) if 'timeline' in document else Timeline.from_legacy(merged)
        self.multitrack_view.set_model(self.multitrack)
        self.timeline.set_range(
            self.state.start, min(self.state.end or self.state.duration, self.state.duration), emit=True
        )
        self.aspect.setCurrentText(self.state.aspect)
        self.brightness.setValue(self.state.brightness)
        self.contrast.setValue(self.state.contrast)
        self.saturation.setValue(self.state.saturation)
        self.speed.setCurrentText(f"{self.state.speed:.2f}×")
        self.effect.setCurrentText(self.state.effect)
        self.fade.setChecked(self.state.fade)
        self.overlay.setText(self.state.overlay_text)
        self.export_profile.setCurrentText(self.state.export_profile)
        self.noise_reduction.setChecked(self.state.noise_reduction)
        self.loudness.setChecked(self.state.loudness_normalization)
        publish = document.get("publish", {})
        self.publish_title.setText(publish.get("title", ""))
        self.publish_caption.setPlainText(publish.get("caption", ""))
        self.publish_tags.setPlainText(publish.get("hashtags", ""))
        self.ai_prompt.setPlainText(document.get("ai_prompt", self.ai_prompt.toPlainText()))
        self.set_status("Proje açıldı ve son ayarlar geri yüklendi.")

    def autosave_project(self) -> None:
        if not self.state.source:
            return
        if self.project_path:
            autosave = self.project_path + ".autosave"
        else:
            app_data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
            app_data.mkdir(parents=True, exist_ok=True)
            autosave = str(app_data / "recovery.akis.json")
        try:
            self.write_project(autosave, snapshot=False)
        except Exception:
            pass

    def system_language_code(self) -> str:
        return "tr" if QLocale.system().language() == QLocale.Language.Turkish else "en"

    def apply_language(self, code: str) -> None:
        mapping = EN_UI if code == "en" else {value: key for key, value in EN_UI.items()}

        def translated(value: str) -> str:
            if value in mapping:
                return mapping[value]
            result = value
            for source, target in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
                if source and source in result:
                    result = result.replace(source, target)
            return result

        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QLabel, QPushButton, QCheckBox, QToolButton)):
                widget.setText(translated(widget.text()))
            if isinstance(widget, (QLineEdit, QPlainTextEdit)):
                widget.setPlaceholderText(translated(widget.placeholderText()))
            if isinstance(widget, QTabWidget):
                for index in range(widget.count()):
                    widget.setTabText(index, translated(widget.tabText(index)))
            if isinstance(widget, QComboBox) and widget is not self.language:
                blocked = widget.blockSignals(True)
                for index in range(widget.count()):
                    widget.setItemText(index, translated(widget.itemText(index)))
                widget.blockSignals(blocked)

    def change_language(self) -> None:
        code = self.language.currentData()
        self.settings.setValue("language", code)
        self.apply_language(code)
        self.set_status("Language changed to English." if code == "en" else "Dil Türkçe olarak değiştirildi.")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in VIDEO_EXTS:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.load_video(urls[0].toLocalFile())
            event.acceptProposedAction()


STYLE = r"""
* { font-family: 'Segoe UI'; font-size: 13px; color: #f3f4f8; }
QMainWindow, QWidget { background: #0d0e12; }
QFrame#sidebar { background: #111218; border-right: 1px solid #252733; }
QLabel#brand { font-size: 18px; font-weight: 800; letter-spacing: 1px; }
QLabel#projectTitle { font-size: 22px; font-weight: 700; }
QLabel#aiHero { font-size: 23px; font-weight: 760; line-height: 1.25; }
QLabel#muted, QLabel#mutedSmall { color: #9195a7; }
QLabel#mutedSmall { font-size: 11px; }
QLabel#sectionLabel { color: #85899c; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 7px; }
QLabel#mono { font-family: 'Cascadia Mono'; color: #b8bbca; }
QLabel#statusPill { background: #181a22; color: #aeb2c3; border: 1px solid #282b38; border-radius: 14px; padding: 6px 11px; max-width: 360px; }
QPushButton { border: 0; border-radius: 9px; padding: 9px 12px; background: #20222c; text-align: left; }
QPushButton:hover { background: #292c38; }
QPushButton[nav='true'] { background: transparent; color: #aeb1c0; padding: 10px 12px; }
QPushButton[nav='true']:hover, QPushButton[active='true'] { background: #22202f; color: white; }
QPushButton#primary, QPushButton#primaryLarge { background: #7357f5; color: white; font-weight: 700; text-align: center; }
QPushButton#primary:hover, QPushButton#primaryLarge:hover { background: #876eff; }
QPushButton#primaryLarge { padding: 13px; }
QPushButton#secondary { border: 1px solid #343747; background: #1a1c24; text-align: center; }
QPushButton#ghost { background: transparent; color: #a7aabd; text-align: center; }
QPushButton#roundButton { border-radius: 20px; background: #7357f5; text-align: center; padding: 0; }
QFrame#editor { background: #111218; border: 1px solid #252733; border-radius: 14px; }
QFrame#privacyCard { background: #171921; border: 1px solid #282b37; border-radius: 10px; }
QLabel#localTitle { color: #74d9ac; font-weight: 600; }
QVideoWidget#video { background: #08090c; border-radius: 10px; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox { background: #171920; border: 1px solid #303340; border-radius: 8px; padding: 8px; selection-background-color: #7357f5; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid #7c5cff; }
QPlainTextEdit { line-height: 1.35; }
QListWidget#mediaList { background: transparent; border: 0; outline: 0; }
QListWidget#mediaList::item { background: #191b23; border-radius: 8px; padding: 9px; margin-bottom: 5px; }
QTabWidget::pane { background: #111218; border: 1px solid #252733; border-radius: 12px; top: -1px; }
QTabBar::tab { background: transparent; color: #888c9e; padding: 10px 12px; }
QTabBar::tab:selected { color: white; border-bottom: 2px solid #8f78ff; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #303340; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSlider::groove:horizontal { height: 4px; background: #2a2d38; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #7c5cff; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #b4a6ff; }
QProgressBar { background: transparent; border: 0; }
QProgressBar::chunk { background: #7c5cff; border-radius: 2px; }
QSplitter::handle { width: 10px; background: transparent; }
QToolTip { background: #232631; color: white; border: 1px solid #3a3e4e; padding: 5px; }
"""


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

