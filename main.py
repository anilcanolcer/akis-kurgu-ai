from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

# Prefer the native Windows backend; retain an explicit user override.
if sys.platform == "win32":
    os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

from akis.timeline_model import Timeline, Track
from akis.multitrack_widget import MultitrackWidget
from akis import project_service
from akis.media_service import MediaService
from akis.timeline_render import duration_frames
from akis import timeline_service
from akis.timeline_audio import TimelineAudio
from akis.render_worker import TimelineRenderWorker
from akis.preview_controller import PreviewController
from akis.preview_widget import PreviewView, ProxyPlayback, timeline_signature
from akis.shape_art import default_tail
from akis.update_worker import UpdateCheckWorker, UpdateDownloadWorker
from akis.ai_service import plan_prompt, parse_suggestions, add_plan_markers
from akis.caption_worker import LocalCaptionWorker
from akis.tts_worker import TtsWorker
from akis.ai_workers import AIWorker, PromptEditWorker, TranscriptWorker
from akis import edit_plan
from akis.media_bin import MediaBin
from akis.caption_service import caption_track
from akis import ai_providers, update_service
from akis import template_service
from akis.template_dialog import TemplateDialog

from PySide6.QtCore import QLocale, QSettings, QSize, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
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
    QScrollBar,
    QSizePolicy,
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
    "Ne istediğini yaz.\nAkış kurgulasın.": "Say what you want.\nAkış edits it.",
    "Videoyu keser, yeniden dizer; geçiş, ok ve daire, yazı, renk ve hız ekler. Beğenmezseniz tek tıkla geri alın.":
        "Cuts and reorders the video; adds transitions, arrows and circles, text, colour and speed. Undo in one click.",
    "İSTEĞİNİZ / PROMPT": "YOUR PROMPT", "✦  Prompt ile kurgula": "✦  Edit from prompt",
    "↶  AI kurgusunu geri al": "↶  Undo AI edit", "Öneri al": "Get suggestions",
    "ÖNERİ MODU (KESMEDEN)": "SUGGESTION MODE (NO CUTS)", "KONUŞMA METNİ VE SESLENDİRME": "TRANSCRIPT & VOICEOVER",
    "Konuşmayı da çözümle (yerel Whisper, daha yavaş)": "Also analyse speech (local Whisper, slower)",
    "Yapılan kurgunun özeti burada görünecek.": "A summary of the edit will appear here.",
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
    fade: bool = False
    export_profile: str = "Reels · 1080×1920"
    noise_reduction: bool = False
    loudness_normalization: bool = False
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = EditState()
        self.media_bin = MediaBin()
        self.multitrack = Timeline.from_legacy({})
        self.timeline_frame = 0
        self.playback_clock = timeline_service.PlaybackClock()
        self.preview = PreviewController(ffmpeg_path, self)
        self.preview.frame_ready.connect(self.show_timeline_frame)
        self.preview.failed.connect(self.set_status)
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self.advance_timeline)
        self.proxy = ProxyPlayback(ffmpeg_path, self)
        self.proxy.image_ready.connect(lambda image: self.video.set_image(image))
        self.proxy.frame_changed.connect(self.on_proxy_frame)
        self.proxy.ready.connect(self.on_proxy_ready)
        self.proxy.ended.connect(self.on_proxy_ended)
        self.proxy.failed.connect(self.on_proxy_failed)
        self.proxy_enabled = True
        self._play_when_ready = False
        self.proxy_timer = QTimer(self)
        self.proxy_timer.setSingleShot(True)
        self.proxy_timer.setInterval(900)
        self.proxy_timer.timeout.connect(self.prepare_proxy)
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.project_path = ""
        self._saved_signature = None  # project contents as last saved or opened
        self._close_confirmed = False
        self._pending_project: dict | None = None
        self.worker: QThread | None = None
        self._workers = set()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 650)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1500, available.width()), min(920, available.height()))
        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon(str(runtime_file('app.ico'))))

        self.preview_audio_output = QAudioOutput()
        self.preview_audio_output.setVolume(0.8)
        self.preview_audio = QMediaPlayer()
        self.preview_audio.setAudioOutput(self.preview_audio_output)
        self.timeline_audio = TimelineAudio(self.preview_audio, self)
        self.timeline_audio.failed.connect(self.set_status)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_sidebar())
        layout.addWidget(self.build_workspace(), 1)

        self._provider_keys = {}
        self._saved_providers = set()
        self._active_provider = self.provider.currentText()
        self.provider.currentTextChanged.connect(self.change_provider)
        self.load_key()
        self.apply_language(self.settings.value("language", self.system_language_code()))
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30_000)
        self.autosave_timer.timeout.connect(self.autosave_project)
        self.autosave_timer.start()
        self.update_check = None
        self.update_download = None
        if getattr(sys, '_MEIPASS', None) and sys.platform == 'win32':
            QTimer.singleShot(5000, self.check_for_updates)
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
        side.setFixedWidth(190)
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
            elif index in (1, 2):
                button.clicked.connect(self.show_templates)
            else:
                button.clicked.connect(lambda: self.set_status("Dışa aktarmak için üstteki düğmeyi kullanın."))
            v.addWidget(button)

        v.addSpacing(20)
        label = QLabel("PROJE MEDYASI")
        label.setObjectName("sectionLabel")
        v.addWidget(label)
        self.media_search = QLineEdit()
        self.media_search.setPlaceholderText("Medya ara / Search media")
        self.media_search.textChanged.connect(self.refresh_media_bin)
        v.addWidget(self.media_search)
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
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(300)
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

        self.video = PreviewView('Video ekleyin / Add a video')
        self.video.setObjectName("video")
        self.video.setMinimumSize(320, 200)
        self.video.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.video.setToolTip('Ctrl + tekerlek: yakınlaştır · sürükle: kaydır · orta tuş: sıfırla · çift tık: yazı/işaret düzenle')
        self.video.double_clicked.connect(self.edit_at)
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
        self.master_volume = 0.8
        volume.valueChanged.connect(self.change_master_volume)
        controls.addWidget(volume)
        v.addLayout(controls)

        timeline_header = QHBoxLayout()
        timeline_header.addWidget(QLabel("Zaman çizelgesi"))
        timeline_header.addStretch()
        self.selection_label = QLabel("Seçim: —")
        self.selection_label.setObjectName("muted")
        self.selection_label.hide()
        timeline_header.addWidget(self.selection_label)
        v.addLayout(timeline_header)
        tool_container = QWidget()
        tools = QHBoxLayout(tool_container)
        tools.setContentsMargins(0, 0, 0, 0)
        for label, action in [('＋ İz', self.add_track), ('− İz', self.remove_track),
                              ('＋ Medya', self.add_timeline_media), ('Böl', self.split_clip),
                              ('Ripple sil', self.ripple_delete), ('Klip sesi', self.set_clip_volume), ('Metni düzenle', self.edit_text_clip)]:
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
        tool_scroll = QScrollArea()
        tool_scroll.setWidgetResizable(True)
        tool_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tool_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tool_scroll.setMaximumHeight(65)
        tool_scroll.setWidget(tool_container)
        v.addWidget(tool_scroll)
        self.multitrack_view = MultitrackWidget(self.multitrack)
        self.multitrack_view.waveform_executable = ffmpeg_path
        self.multitrack_view.seek.connect(self.seek_timeline)
        self.multitrack_view.changed.connect(lambda: self.seek_timeline(self.timeline_frame))
        self.multitrack_view.clip_activated.connect(self.edit_clip)
        self.track_scroll = QScrollArea()
        self.track_scroll.setWidgetResizable(True)
        self.track_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.track_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.track_scroll.setMinimumHeight(218)
        self.track_scroll.setMaximumHeight(380)
        self.track_scroll.setWidget(self.multitrack_view)
        v.addWidget(self.track_scroll)
        self.horizontal_timeline = QScrollBar(Qt.Orientation.Horizontal)
        self.horizontal_timeline.setRange(0, 0)
        self.horizontal_timeline.valueChanged.connect(self.multitrack_view.set_offset)
        self.multitrack_view.viewport_resized.connect(self.update_timeline_scroll)
        v.addWidget(self.horizontal_timeline)
        self.timeline = TimelineBar()
        self.timeline.setEnabled(False)
        self.timeline.setToolTip("Eski aralık seçimi ortak timeline çıktısını etkilemez; bölme aracını kullanın.")
        self.timeline.range_changed.connect(self.on_timeline_range)
        self.timeline.seek_requested.connect(lambda sec: self.seek_timeline(round(sec * self.multitrack.fps_num / self.multitrack.fps_den)))
        v.addWidget(self.timeline)
        self.timeline.hide()

        trim_row = QWidget()
        trims = QHBoxLayout(trim_row)
        trims.setContentsMargins(0, 0, 0, 0)
        trims.addWidget(QLabel("Başlangıç"))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setEnabled(False)
        self.start_spin.setDecimals(2)
        self.start_spin.setSuffix(" sn")
        self.start_spin.valueChanged.connect(self.on_spin_range)
        trims.addWidget(self.start_spin)
        trims.addWidget(QLabel("Bitiş"))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setEnabled(False)
        self.end_spin.setDecimals(2)
        self.end_spin.setSuffix(" sn")
        self.end_spin.valueChanged.connect(self.on_spin_range)
        trims.addWidget(self.end_spin)
        trims.addStretch()
        reset = QPushButton("Aralığı sıfırla")
        reset.setEnabled(False)
        reset.setObjectName("ghost")
        reset.clicked.connect(self.reset_range)
        trims.addWidget(reset)
        v.addWidget(trim_row)
        trim_row.hide()
        return area

    def build_inspector(self) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("inspector")
        wrapper.setMinimumWidth(300)
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

        hero = QLabel("Ne istediğini yaz.\nAkış kurgulasın.")
        hero.setObjectName("aiHero")
        v.addWidget(hero)
        desc = QLabel("Videoyu keser, yeniden dizer; geçiş, ok ve daire, yazı, renk ve hız ekler. Beğenmezseniz tek tıkla geri alın.")
        desc.setWordWrap(True)
        desc.setObjectName("muted")
        v.addWidget(desc)

        v.addWidget(self.section("İSTEĞİNİZ / PROMPT"))
        self.ai_prompt = QPlainTextEdit()
        self.ai_prompt.setPlaceholderText("Örn. Sessizlikleri at, sahneler arasına geçiş koy, en komik ana ok ve daire ekle, başa dikkat çekici bir yazı yaz.")
        self.ai_prompt.setFixedHeight(112)
        v.addWidget(self.ai_prompt)

        prompt_edit = QPushButton("✦  Prompt ile kurgula")
        prompt_edit.setObjectName("primaryLarge")
        prompt_edit.setToolTip("Yazdığınız isteğe göre videoyu gerçekten keser, dizer ve ayarlar.")
        prompt_edit.clicked.connect(self.run_prompt_edit)
        v.addWidget(prompt_edit)
        self.undo_edit_button = QPushButton("↶  AI kurgusunu geri al")
        self.undo_edit_button.setObjectName("secondary")
        self.undo_edit_button.setEnabled(False)
        self.undo_edit_button.clicked.connect(self.undo_prompt_edit)
        v.addWidget(self.undo_edit_button)
        self._edit_undo = []
        self.ai_result = QPlainTextEdit()
        self.ai_result.setReadOnly(True)
        self.ai_result.setPlaceholderText("Yapılan kurgunun özeti burada görünecek.")
        self.ai_result.setMinimumHeight(150)
        v.addWidget(self.ai_result)
        self.use_speech = QCheckBox("Konuşmayı da çözümle (yerel Whisper, daha yavaş)")
        self.use_speech.setToolTip("Model önbellekte yoksa bu adım atlanır; kurgu kare, sessizlik ve sahne bilgisiyle yapılır.")
        v.addWidget(self.use_speech)
        v.addWidget(self.section("AI SAĞLAYICI / PROVIDER"))
        self.provider = QComboBox()
        self.provider.addItems(ai_providers.PROVIDERS)
        v.addWidget(self.provider)
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
        self.model.addItems(ai_providers.PROVIDERS["OpenAI"])
        v.addWidget(self.model)
        save_key = QPushButton("Anahtarı güvenli kaydet / Save key")
        save_key.clicked.connect(lambda: self.save_key(self.api_key.text().strip()))
        v.addWidget(save_key)


        v.addWidget(self.section("ÖNERİ MODU (KESMEDEN)"))
        options = QFormLayout()
        self.ai_platform = QComboBox(); self.ai_platform.addItems(['Reels', 'TikTok', 'YouTube Shorts', 'General'])
        self.ai_tempo = QComboBox(); self.ai_tempo.addItems(['Slow', 'Medium', 'Fast', 'Dynamic'])
        self.ai_style = QComboBox(); self.ai_style.addItems(['Cinematic', 'Energetic', 'Minimal', 'Educational', 'Storytelling'])
        self.ai_focus = QComboBox(); self.ai_focus.addItems(['Hook first', 'Highlights', 'Full story', 'Product', 'Tutorial'])
        for label, widget in [('Platform', self.ai_platform), ('Tempo', self.ai_tempo), ('Stil / Style', self.ai_style), ('Odak / Focus', self.ai_focus)]:
            options.addRow(label, widget)
        v.addLayout(options)

        analyze = QPushButton("Öneri al")
        analyze.setObjectName("secondary")
        analyze.clicked.connect(self.run_ai)
        v.addWidget(analyze)
        self.ai_suggestions = []
        self.ai_choice = QComboBox()
        self.ai_choice.currentIndexChanged.connect(self.show_ai_suggestion)
        v.addWidget(self.ai_choice)
        apply_plan = QPushButton('Seçili öneriyi işaretlere uygula / Apply markers')
        apply_plan.clicked.connect(self.apply_ai_suggestion)
        v.addWidget(apply_plan)
        v.addWidget(self.section("KONUŞMA METNİ VE SESLENDİRME"))
        self.caption_backend = QComboBox()
        self.caption_backend.addItems(['OpenAI', 'Yerel / Local Whisper', 'xAI', 'Gemini'])
        v.addWidget(self.caption_backend)
        v.addWidget(QLabel('API transkripsiyon modeli'))
        self.transcript_model = QComboBox(); self.transcript_model.setEditable(True)
        self.transcript_model.addItems(ai_providers.TRANSCRIPTION_MODELS['OpenAI'])
        v.addWidget(self.transcript_model)
        self.caption_backend.currentTextChanged.connect(self.change_transcript_provider)
        self.local_model = QComboBox(); self.local_model.addItems(['tiny', 'base', 'small'])
        v.addWidget(self.local_model)
        self.download_model = QCheckBox('Modeli indir / Download model (internet)')
        v.addWidget(self.download_model)
        note = QLabel('Yerel model ilk kullanımda indirilmeli; indirme kapalıyken yalnızca önbellek kullanılır. / Download once for offline use.')
        note.setWordWrap(True); v.addWidget(note)
        transcript = QPushButton("Konuşmayı Türkçe metne çevir")
        transcript.setObjectName("secondary")
        transcript.clicked.connect(self.run_transcript)
        v.addWidget(transcript)
        self.caption_segments = []
        self.caption_source = ''
        self.apply_captions_button = QPushButton('Yerel altyazıyı timeline’a ekle / Add local captions')
        self.apply_captions_button.setEnabled(False)
        self.apply_captions_button.clicked.connect(self.apply_local_captions)
        v.addWidget(self.apply_captions_button)

        self.tts_input = QPlainTextEdit()
        self.tts_input.setPlaceholderText('Seslendirme metni / Voiceover text')
        self.tts_input.setFixedHeight(75)
        v.addWidget(self.tts_input)
        tts_button = QPushButton('Windows sesiyle WAV oluştur / Create voiceover')
        tts_button.clicked.connect(self.create_voiceover)
        v.addWidget(tts_button)
        tts_hint = QLabel('Çevrimdışı Windows sistem sesi kullanılır; dil ve ses işletim sisteminde yüklü seslere bağlıdır.')
        tts_hint.setWordWrap(True)
        v.addWidget(tts_hint)

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
        self.aspect.currentTextChanged.connect(self.change_aspect)
        v.addWidget(self.aspect)

        v.addWidget(self.section("HIZ VE GEÇİŞ"))
        self.speed = QComboBox()
        self.speed.addItems(["0.50×", "0.75×", "1.00×", "1.25×", "1.50×", "2.00×"])
        self.speed.setCurrentText("1.00×")
        self.speed.currentTextChanged.connect(self.change_speed)
        v.addWidget(self.speed)
        self.fade = QCheckBox("Yumuşak giriş ve çıkış geçişi (henüz yok)")
        self.fade.setEnabled(False)
        self.fade.setToolTip("Ortak timeline render yolunda henüz desteklenmiyor.")
        self.fade.toggled.connect(lambda checked: setattr(self.state, "fade", checked))
        v.addWidget(self.fade)

        v.addWidget(self.section("GÖRÜNÜM EFEKTİ"))
        self.effect = QComboBox()
        self.effect.addItems(["Yok", "Sinematik", "Siyah-beyaz", "Yumuşak"])
        self.effect.setEnabled(False)
        self.effect.setToolTip("Ortak timeline render yolunda henüz desteklenmiyor.")
        self.effect.currentTextChanged.connect(lambda text: setattr(self.state, "effect", text))
        v.addWidget(self.effect)

        v.addWidget(self.section("RENK VE IŞIK"))
        self.brightness = self.add_slider(v, "Parlaklık", -50, 50, lambda x: self.change_color("brightness", x))
        self.contrast = self.add_slider(v, "Kontrast", -50, 50, lambda x: self.change_color("contrast", x))
        self.saturation = self.add_slider(v, "Doygunluk", -50, 50, lambda x: self.change_color("saturation", x))

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
        self.overlay.setEnabled(False)
        self.overlay.setToolTip("Bu kontrol ortak timeline render yolunda henüz desteklenmiyor.")
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
        self.export_profile.currentTextChanged.connect(self.change_export_profile)
        v.addWidget(self.export_profile)
        profile_hint = QLabel('Profil oranı seçer; 4K seçenekleri seçili oranı iki kat çözünürlükte dışa aktarır.')
        profile_hint.setWordWrap(True)
        v.addWidget(profile_hint)
        self.noise_reduction = QCheckBox("Temel gürültü azaltma")
        self.noise_reduction.setEnabled(False)
        self.noise_reduction.setToolTip("Ortak timeline render yolunda henüz desteklenmiyor.")
        self.noise_reduction.toggled.connect(lambda checked: setattr(self.state, "noise_reduction", checked))
        v.addWidget(self.noise_reduction)
        self.loudness = QCheckBox("Ses yüksekliğini -14 LUFS'a normalleştir (henüz yok)")
        self.loudness.setEnabled(False)
        self.loudness.setToolTip("Ortak timeline render yolunda henüz desteklenmiyor.")
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

    def refresh_media_bin(self):
        self.media_list.clear()
        for path in self.media_bin.search(self.media_search.text()):
            item = QListWidgetItem(f'▣  {Path(path).name}')
            item.setToolTip(path)
            self.media_list.addItem(item)

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Video seç", "", "Video (*.mp4 *.mov *.mkv *.webm *.avi *.m4v)")
        if path:
            self.add_video(path)

    def add_video(self, path: str) -> None:
        if not self.state.source:
            self.load_video(path)
            return
        file = Path(path)
        if file.suffix.lower() not in VIDEO_EXTS or not file.is_file():
            QMessageBox.warning(self, APP_NAME, 'Desteklenen bir video dosyası seçin.')
            return
        try:
            seconds = MediaService(ffmpeg_path()).duration(str(file))
            timeline_service.append_video(self.multitrack, str(file), seconds, self.multitrack_view.selected_track)
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f'Video eklenemedi: {exc}')
            return
        self.media_bin.add(str(file))
        self.refresh_media_bin()
        self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
        self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * len(self.multitrack.tracks))))
        self.multitrack_view.refresh_waveforms()
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)
        self.set_status('Video zaman çizelgesine eklendi.')

    def load_video(self, path: str) -> None:
        file = Path(path)
        if file.suffix.lower() not in VIDEO_EXTS or not file.exists():
            QMessageBox.warning(self, APP_NAME, "Desteklenen bir video dosyası seçin.")
            return
        try:
            duration = MediaService(ffmpeg_path()).duration(str(file))
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        if not self._pending_project:
            self.project_path = ''
        self.caption_segments = []
        self.caption_source = ''
        self.apply_captions_button.setEnabled(False)
        self.state = EditState(source=str(file), aspect=self.aspect.currentText(),
                               brightness=self.brightness.value(), contrast=self.contrast.value(),
                               saturation=self.saturation.value(),
                               speed=float(self.speed.currentText().replace("×", "")))
        if not self._pending_project and not getattr(self, "_template_before_video", False):
            self.multitrack = Timeline.from_legacy({})
            self.multitrack_view.set_model(self.multitrack)
        self.project_title.setText(file.stem)
        self.project_subtitle.setText(f"{file.suffix.upper().lstrip('.')} · {file.stat().st_size / 1024 / 1024:.1f} MB")
        self.media_bin.clear()
        self.media_bin.add(str(file))
        self.refresh_media_bin()
        opening_project = self._pending_project is not None
        self.on_duration(round(duration * 1000))
        self.mark_saved()
        if not opening_project:
            self.set_status("Video hazır. Sağdaki kutuya isteğinizi yazıp kurgulatabilirsiniz.")
        return True

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
        elif getattr(self, '_template_before_video', False):
            self._template_before_video = False
            index = next(i for i, t in enumerate(self.multitrack.tracks) if t.kind == 'video')
            timeline_service.append_media(self.multitrack, index, self.state.source, duration)
            self.multitrack_view.set_model(self.multitrack)
            self.seek_timeline(0)
        elif not any(t.clips for t in self.multitrack.tracks):
            self.multitrack = Timeline.from_legacy(asdict(self.state))
            self.multitrack_view.set_model(self.multitrack)
            self.seek_timeline(0)

    def toggle_play(self) -> None:
        if not self.state.source:
            self.choose_video()
            return
        if self._play_when_ready or self.proxy.playing:
            self.stop_proxy_playback()
        elif self.play_timer.isActive():
            self.play_timer.stop()
            self.playback_clock.stop()
            self.timeline_audio.stop()
            self.play_button.setText('▶')
        else:
            if not duration_frames(self.multitrack):
                return
            if self.proxy_enabled and self.proxy.available:
                if self.timeline_frame >= duration_frames(self.multitrack) - 1:
                    self.seek_timeline(0)
                self.play_button.setText('❚❚')
                if self.proxy.is_ready(self.proxy_signature()):
                    self.proxy.play(self.timeline_frame, self.state.speed, self.master_volume)
                else:
                    self._play_when_ready = True
                    self.set_status('Akıcı önizleme hazırlanıyor…')
                    self.progress.show()
                    self.prepare_proxy()
                return
            self.playback_clock.start(self.timeline_frame, self.state.speed)
            self.play_timer.start(15)
            self.sync_timeline_audio(force=True)
            self.play_button.setText('❚❚')

    def proxy_signature(self):
        adjustments = {k: v for k, v in self.render_adjustments().items() if k != 'speed'}
        return timeline_signature(self.multitrack, self.canvas_size(), adjustments)

    def prepare_proxy(self):
        """Render the smooth-playback copy in the background whenever the edit has changed."""
        if not self.proxy_enabled or not self.proxy.available or not duration_frames(self.multitrack):
            return
        try:
            adjustments = {k: v for k, v in self.render_adjustments().items() if k != 'speed'}
            self.proxy.prepare(self.multitrack, self.canvas_size(), adjustments, self.proxy_signature())
        except Exception as exc:
            self.on_proxy_failed(str(exc))

    def on_proxy_ready(self):
        if self.proxy.is_ready(self.proxy_signature()):
            if self._play_when_ready:
                self._play_when_ready = False
                self.progress.hide()
                self.set_status('Oynatılıyor.')
                self.proxy.play(self.timeline_frame, self.state.speed, self.master_volume)
        else:  # the edit changed while rendering
            self.prepare_proxy()

    def on_proxy_frame(self, frame):
        total = duration_frames(self.multitrack)
        if not total:
            return
        self.timeline_frame = min(max(0, frame), total - 1)
        self.multitrack_view.playhead = self.timeline_frame
        self.multitrack_view.update()
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        self.time_label.setText(f'{format_time(self.timeline_frame/fps)} / {format_time(total/fps)}')

    def stop_proxy_playback(self, refresh=True):
        was_active = self._play_when_ready or self.proxy.playing
        self._play_when_ready = False
        self.proxy.pause()
        self.progress.hide()
        self.play_button.setText('▶')
        if was_active:
            self.set_status('Duraklatıldı.')
        if was_active and refresh:
            self.seek_timeline(self.timeline_frame)  # exact full-quality still for the paused frame

    def on_proxy_ended(self):
        self.stop_proxy_playback()

    def on_proxy_failed(self, message):
        """Fall back to frame-by-frame preview rather than leaving playback broken."""
        self.proxy_enabled = False
        self.stop_proxy_playback(refresh=False)
        self.set_status(f'Akıcı önizleme kullanılamadı, kare kare önizlemeye geçildi: {message[:120]}')

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
        if not key or not model:
            QMessageBox.information(self, APP_NAME, "API anahtarı ve model belirtin.")
            return None
        self._provider_keys[self.provider.currentText()] = key
        if self.remember_key.isChecked():
            self.save_key(key)
        return key, model

    def change_provider(self, provider):
        self._provider_keys[self._active_provider] = self.api_key.text().strip()
        self._active_provider = provider
        self.model.clear(); self.model.addItems(ai_providers.PROVIDERS[provider])
        self.load_key()

    def save_key(self, key: str) -> None:
        if not key:
            self.set_status('Kaydedilecek API anahtarını girin.')
            return
        try:
            ai_providers.save_key(APP_NAME, self.provider.currentText(), key)
            self._provider_keys[self.provider.currentText()] = key
            self._saved_providers.add(self.provider.currentText())
            self.remember_key.setChecked(True)
            self.set_status('API anahtarı sistem kasasına kaydedildi.')
        except Exception as exc:
            self.set_status(f'Anahtar güvenli kasaya kaydedilemedi: {exc}')

    def load_key(self) -> None:
        provider = self.provider.currentText()
        key = self._provider_keys.get(provider, '')
        if not key:
            try:
                key = ai_providers.load_key(APP_NAME, provider)
                if key:
                    self._saved_providers.add(provider)
            except Exception:
                key = ''
        self.api_key.setText(key)
        self.remember_key.setChecked(provider in self._saved_providers)

    def change_transcript_provider(self, provider):
        self.transcript_model.clear()
        self.transcript_model.addItems(ai_providers.TRANSCRIPTION_MODELS.get(provider, ()))

    def show_templates(self):
        dialog = TemplateDialog(self)
        if dialog.exec():
            template, style, tempo = dialog.selection()
            template_service.apply_template(self.multitrack, template)
            self._template_before_video = not bool(self.state.source)
            for i in range(self.aspect.count()):
                if self.aspect.itemText(i).startswith(template.ratio):
                    self.aspect.setCurrentIndex(i); break
            self.apply_preset(*template_service.STYLES[style])
            self.speed.setCurrentText(template_service.TEMPOS[tempo])
            self.multitrack_view.set_model(self.multitrack)
            self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
            self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * len(self.multitrack.tracks))))
            self.multitrack_view.update()
            if duration_frames(self.multitrack):
                self.seek_timeline(self.timeline_frame)
            self.set_status(f'{template.name} uygulandı; medyayı izlere ekleyin.')

    def toggle_key(self) -> None:
        mode = self.api_key.echoMode()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Normal if mode == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password)

    def run_ai(self) -> None:
        if not self.can_start_work():
            return
        if not self.ensure_video():
            return
        credentials = self.api_credentials()
        if not credentials:
            return
        key, model = credentials
        self.begin_work("AI analizi başlatılıyor…")
        self.worker = AIWorker(key, model, self.state.source, self.state.duration, plan_prompt(self.ai_prompt.toPlainText().strip(), self.ai_platform.currentText(), self.ai_tempo.currentText(), self.ai_style.currentText(), self.ai_focus.currentText()), ffmpeg_path(), self.provider.currentText())
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_ai_plan)
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()

    def edit_sources(self):
        """Every video on the timeline (then the loaded one), in a stable order with durations."""
        paths = []
        for track in self.multitrack.tracks:
            if track.kind == 'video':
                for clip in sorted(track.clips, key=lambda c: c.start):
                    if clip.source and clip.source not in paths:
                        paths.append(clip.source)
        if self.state.source and self.state.source not in paths:
            paths.append(self.state.source)
        media = MediaService(ffmpeg_path())
        return [(path, media.duration(path)) for path in paths if Path(path).is_file()]

    def run_prompt_edit(self) -> None:
        if not self.can_start_work() or not self.ensure_video():
            return
        request = self.ai_prompt.toPlainText().strip()
        if not request:
            QMessageBox.information(self, APP_NAME, "Önce videoyu nasıl kurgulamak istediğinizi yazın.")
            return
        credentials = self.api_credentials()
        if not credentials:
            return
        key, model = credentials
        try:
            sources = self.edit_sources()
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f'Video okunamadı: {exc}')
            return
        if not sources:
            QMessageBox.warning(self, APP_NAME, 'Kurgulanacak video dosyası bulunamadı.')
            return
        transcripts = {self.caption_source: self.caption_segments} if self.caption_source and self.caption_segments else {}
        self.begin_work("Prompt kurgusu başlatılıyor…")
        self.worker = PromptEditWorker(key, model, self.provider.currentText(), request, self.multitrack, sources,
                                       ffmpeg_path(), transcripts,
                                       self.local_model.currentText() if self.use_speech.isChecked() else None)
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_prompt_edit)
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()

    def edit_snapshot(self):
        return {'timeline': self.multitrack, 'aspect': self.aspect.currentText(), 'speed': self.speed.currentText(),
                'color': (self.brightness.value(), self.contrast.value(), self.saturation.value()),
                'publish': (self.publish_title.text(), self.publish_caption.toPlainText(), self.publish_tags.toPlainText())}

    def show_timeline(self, timeline):
        self.stop_proxy_playback(refresh=False)
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        self.multitrack = timeline
        self.multitrack_view.set_model(timeline)
        self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(timeline.tracks)))
        self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * len(timeline.tracks))))
        self.seek_timeline(0)

    def on_prompt_edit(self, plan, sources):
        try:
            aspect_text = self.aspect.itemText(edit_plan.ASPECTS.index(plan['aspect'])) if 'aspect' in plan else self.aspect.currentText()
            canvas = timeline_service.canvas_size(aspect_text, self.multitrack, MediaService(ffmpeg_path()))
            timeline = edit_plan.apply_plan(self.multitrack, sources, plan, canvas)
        except Exception as exc:
            self.on_worker_error(f'Kurgu planı uygulanamadı: {exc}')
            return
        self._edit_undo.append(self.edit_snapshot())
        self.undo_edit_button.setEnabled(True)
        if 'aspect' in plan:
            self.aspect.setCurrentIndex(edit_plan.ASPECTS.index(plan['aspect']))
        if 'speed' in plan:
            self.speed.setCurrentText(f"{plan['speed']:.2f}×")
        if 'color' in plan:
            self.apply_preset(plan['color']['brightness'], plan['color']['contrast'], plan['color']['saturation'])
        if 'title' in plan:
            self.publish_title.setText(plan['title'])
        if 'caption' in plan:
            self.publish_caption.setPlainText(plan['caption'])
        if 'hashtags' in plan:
            self.publish_tags.setPlainText(' '.join(t if t.startswith('#') else '#' + t for t in plan['hashtags']))
        self.show_timeline(timeline)
        self.ai_result.setPlainText(edit_plan.describe(plan, timeline))
        self.finish_work('AI kurgusu uygulandı. Beğenmezseniz geri alabilir veya yeni bir istek yazabilirsiniz.')

    def undo_prompt_edit(self):
        if not self._edit_undo or not self.can_start_work():
            return
        snapshot = self._edit_undo.pop()
        self.undo_edit_button.setEnabled(bool(self._edit_undo))
        self.aspect.setCurrentText(snapshot['aspect'])
        self.speed.setCurrentText(snapshot['speed'])
        self.apply_preset(*snapshot['color'])
        title, caption, tags = snapshot['publish']
        self.publish_title.setText(title)
        self.publish_caption.setPlainText(caption)
        self.publish_tags.setPlainText(tags)
        self.show_timeline(snapshot['timeline'])
        self.ai_result.setPlainText('')
        self.set_status('AI kurgusu geri alındı.')

    def on_ai_plan(self, plans):
        self.ai_suggestions = plans
        self.ai_choice.clear()
        self.ai_choice.addItems([str(p.get('title') or f'Öneri / Suggestion {i+1}') for i, p in enumerate(plans)])
        self.show_ai_suggestion(self.ai_choice.currentIndex())
        self.finish_work('Öneriler hazır; birini seçip işaret olarak uygulayabilirsiniz.')

    def show_ai_suggestion(self, index):
        if 0 <= index < len(self.ai_suggestions):
            plan = self.ai_suggestions[index]
            self.ai_result.setPlainText(json.dumps(plan, ensure_ascii=False, indent=2))

    def apply_ai_suggestion(self):
        index = self.ai_choice.currentIndex()
        if 0 <= index < len(self.ai_suggestions):
            plan = self.ai_suggestions[index]
            add_plan_markers(self.multitrack, plan)
            self.publish_title.setText(str(plan.get('title', '')))
            self.publish_caption.setPlainText(str(plan.get('caption', '')))
            self.set_status('Öneri işaretleri projeye eklendi. / Plan markers added.')
            self.multitrack_view.update()

    def run_transcript(self) -> None:
        if not self.can_start_work():
            return
        if not self.ensure_video():
            return
        if self.caption_backend.currentIndex() == 1:
            self.caption_request_source = self.state.source
            self.worker = LocalCaptionWorker(self.caption_request_source, self.local_model.currentText(), self.download_model.isChecked())
        else:
            provider = self.caption_backend.currentText()
            if self.provider.currentText() == provider:
                key = self.api_key.text().strip()
            else:
                key = self._provider_keys.get(provider, '')
                if not key:
                    try:
                        key = ai_providers.load_key(APP_NAME, provider)
                    except Exception:
                        key = ''
            if not key or not self.transcript_model.currentText().strip():
                QMessageBox.information(self, APP_NAME, f'{provider} için API anahtarı ve modeli girin.')
                return
            self.worker = TranscriptWorker(key, self.state.source, ffmpeg_path(), self.transcript_model.currentText().strip(), provider)
        self.begin_work("Ses hazırlanıyor…")
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_local_transcript if self.caption_backend.currentIndex() == 1 else self.on_transcript)
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()

    def on_local_transcript(self, segments):
        self.caption_segments = segments
        self.caption_source = self.caption_request_source
        self.apply_captions_button.setEnabled(bool(segments))
        self.on_transcript(' '.join(segment['text'] for segment in segments))

    def apply_local_captions(self):
        count = caption_track(self.multitrack, self.caption_source, self.caption_segments)
        self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
        self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * len(self.multitrack.tracks))))
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)
        self.set_status(f'{count} altyazı klibi eklendi. / Caption clips added.')

    def create_voiceover(self):
        if not self.can_start_work():
            return
        text = self.tts_input.toPlainText().strip()
        if not text:
            self.set_status('Önce seslendirme metni girin.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Seslendirmeyi kaydet', '', 'WAV (*.wav)')
        if not path:
            return
        if not path.lower().endswith('.wav'):
            path += '.wav'
        self.begin_work('Windows sesi oluşturuluyor…')
        self.worker = TtsWorker(text, path)
        self.worker.completed.connect(lambda result: self.finish_work(f'Ses kaydedildi: {result}'))
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()

    def on_transcript(self, text: str) -> None:
        self.ai_result.setPlainText("KONUŞMA METNİ\n\n" + text)
        if not self.publish_caption.toPlainText().strip():
            self.publish_caption.setPlainText(text)
        self.finish_work("Türkçe konuşma metni hazır.")

    def export_video(self) -> None:
        if not self.can_start_work():
            return
        if not self.ensure_video():
            return
        default = safe_filename(self.project_title.text()) + "_akis.mp4"
        path, _ = QFileDialog.getSaveFileName(self, "Videoyu dışa aktar", str(Path.home() / "Videos" / default), "MP4 Video (*.mp4)")
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path += ".mp4"
        if timeline_service.output_overwrites_source(self.multitrack, path, (self.state.source,)):
            QMessageBox.warning(self, APP_NAME, 'Çıktı yolu kaynak medya ile aynı olamaz; başka bir dosya adı seçin.')
            return
        self.state.overlay_text = self.overlay.text()
        self.state.aspect = self.aspect.currentText()
        self.state.export_profile = self.export_profile.currentText()
        self.begin_work("Dışa aktarma hazırlanıyor…")
        self.worker = TimelineRenderWorker(self.multitrack, path, self.export_canvas_size(), ffmpeg_path(), adjustments=self.render_adjustments())
        self.worker.completed.connect(self.on_exported)
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()

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

    def can_start_work(self) -> bool:
        if self._workers:
            self.set_status('Bir işlem devam ediyor; lütfen bitmesini bekleyin.')
            return False
        return True

    def start_worker(self) -> None:
        worker = self.worker
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self.worker_finished(w))
        worker.start()

    def worker_finished(self, worker) -> None:
        self._workers.discard(worker)
        if self.worker is worker:
            self.worker = None
        worker.deleteLater()

    def begin_work(self, text: str) -> None:
        self.progress.show()
        self.set_status(text)

    def finish_work(self, text: str) -> None:
        self.progress.hide()
        self.set_status(text)

    def on_worker_error(self, message: str) -> None:
        self.progress.hide()
        self.set_status("İşlem tamamlanamadı.")
        QMessageBox.critical(self, APP_NAME, message)

    def check_for_updates(self):
        self.update_check = UpdateCheckWorker(self)
        self.update_check.available.connect(self.offer_update)
        self.update_check.start()

    def offer_update(self, update):
        self.set_status(f"{update['version']} güncellemesi indiriliyor…")
        destination = str(Path(tempfile.mkdtemp(prefix='akis_update_')) / 'AkisKurguAI-Setup.exe')
        self.update_download = UpdateDownloadWorker(update, destination)
        self.update_download.completed.connect(self.install_update)
        self.update_download.failed.connect(lambda message: self.set_status(f'Güncelleme indirilemedi: {message}'))
        self.update_download.start()

    def install_update(self, installer):
        self.set_status('Güncelleme hazır.')
        answer = QMessageBox.question(self, APP_NAME, 'Güncelleme hazır. Önce açık projenizi kaydedin. Uygulama kapanıp güncellensin mi?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._workers:
            QMessageBox.information(self, APP_NAME, 'Güncellemeden önce devam eden işlemin bitmesini bekleyin.')
            return
        # Settle unsaved work before the installer starts waiting for this process to exit.
        if not self.confirm_close():
            return
        try:
            update_service.launch_installer(installer, sys.executable, os.getpid())
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, APP_NAME, f'Güncelleme başlatılamadı: {exc}')
            return
        self._close_confirmed = True
        self.close()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def update_timeline_scroll(self):
        if not hasattr(self, 'horizontal_timeline'):
            return
        visible = max(1, self.multitrack_view.width() - 100)
        length = round(max((clip.end for track in self.multitrack.tracks for clip in track.clips), default=0) * self.multitrack_view.zoom)
        self.horizontal_timeline.setPageStep(visible)
        self.horizontal_timeline.setRange(0, min(2147483647, max(0, length-visible+40)))
        self.horizontal_timeline.setVisible(self.horizontal_timeline.maximum() > 0)

    def timeline_zoom(self, value):
        self.multitrack_view.zoom = value / 10
        self.update_timeline_scroll()
        self.multitrack_view.update()

    def selected_clip(self):
        return timeline_service.selected_clip(self.multitrack, self.multitrack_view.selected)

    def add_track(self):
        kind, ok = QInputDialog.getItem(self, 'İz ekle / Add track', 'Tür / Type', ['video', 'audio', 'text', 'overlay'], 0, False)
        if ok:
            self.multitrack.tracks.append(Track(kind, f'{kind.title()} {len(self.multitrack.tracks)+1}'))
            self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
            self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * len(self.multitrack.tracks))))
            self.multitrack_view.update()

    def remove_track(self):
        index = self.multitrack_view.selected_track
        if index is None or not 0 <= index < len(self.multitrack.tracks):
            self.set_status('Silinecek izi seçin.')
            return
        track = self.multitrack.tracks[index]
        if track.clips and QMessageBox.question(
                self, APP_NAME, f'“{track.name}” izi ve içindeki {len(track.clips)} klip silinsin mi? Bu işlem geri alınamaz.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.multitrack.tracks.pop(index)
        self.multitrack_view.selected = None
        self.multitrack_view.selected_track = None
        self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
        self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * len(self.multitrack.tracks))))
        self.seek_timeline(self.timeline_frame)

    def edit_text_clip(self):
        track, clip = self.selected_clip()
        if not clip or track.kind != 'text':
            self.set_status('Önce bir metin klibi seçin.')
            return
        self.edit_clip(self.multitrack_view.selected[0], clip.id)

    MARK_COLOURS = {'Kırmızı': 'red', 'Sarı': 'yellow', 'Beyaz': 'white', 'Yeşil': 'green', 'Mavi': 'blue', 'Pembe': 'pink'}

    def edit_clip(self, track_index, clip_id):
        """Open the editor for a text or mark clip (double-click in the preview or on the timeline)."""
        if not 0 <= track_index < len(self.multitrack.tracks):
            return
        track = self.multitrack.tracks[track_index]
        clip = next((c for c in track.clips if c.id == clip_id), None)
        if clip is None or track.kind != 'text':
            return
        self.stop_proxy_playback(refresh=False)
        self.multitrack_view.selected, self.multitrack_view.selected_track = (track_index, clip.id), track_index
        if clip.style.get('shape'):
            names = list(self.MARK_COLOURS) + ['Sil / Delete']
            current = next((i for i, n in enumerate(self.MARK_COLOURS) if self.MARK_COLOURS[n] == clip.style.get('color')), 0)
            choice, ok = QInputDialog.getItem(self, 'İşareti düzenle', 'Renk seçin veya işareti silin', names, current, False)
            if not ok:
                return
            if choice in self.MARK_COLOURS:
                clip.style['color'] = self.MARK_COLOURS[choice]
            else:
                track.clips.remove(clip)
                self.multitrack_view.selected = None
        else:
            value, ok = QInputDialog.getMultiLineText(self, 'Metni düzenle', 'Başlık / altyazı', clip.text)
            if not ok:
                return
            if value.strip():
                clip.text = value.strip()
            else:
                track.clips.remove(clip)
                self.multitrack_view.selected = None
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)

    def element_at(self, x, y):
        """(track_index, clip) of the text or mark drawn nearest to a point of the picture, or None."""
        width, height = self.canvas_size()
        best = None
        for index, track in enumerate(self.multitrack.tracks):
            if track.kind != 'text' or track.muted:
                continue
            for clip in track.clips:
                if not clip.start <= self.timeline_frame < clip.end:
                    continue
                cx, cy = float(clip.style.get('x', 0.5)), float(clip.style.get('y', 0.78))
                if clip.style.get('shape') == 'circle':
                    reach = float(clip.style.get('size', 0.3)) / 2 + 0.04
                    distance = math.hypot(x - cx, (y - cy) * height / width)
                    hit = distance <= reach
                elif clip.style.get('shape') == 'arrow':
                    tail = default_tail(cx, cy)
                    tx, ty = float(clip.style.get('x2', tail[0])), float(clip.style.get('y2', tail[1]))
                    span = (tx - cx) ** 2 + ((ty - cy) * height / width) ** 2 or 1e-9
                    along = max(0.0, min(1.0, ((x - cx) * (tx - cx) + (y - cy) * (ty - cy) * (height / width) ** 2) / span))
                    distance = math.hypot(x - (cx + along * (tx - cx)), (y - (cy + along * (ty - cy))) * height / width)
                    hit = distance <= 0.07
                elif clip.text:
                    lines = max(1, math.ceil(len(clip.text) / 20))
                    distance = math.hypot((x - cx) * 0.3, y - cy)  # text is wide: be generous sideways
                    hit = abs(x - cx) <= 0.48 and abs(y - cy) <= 0.035 * lines + 0.03
                else:
                    continue
                if hit and (best is None or distance < best[0]):
                    best = (distance, index, clip)
        return (best[1], best[2]) if best else None

    def edit_at(self, x, y):
        found = self.element_at(x, y)
        if found:
            self.edit_clip(found[0], found[1].id)
        else:
            self.set_status('Burada düzenlenecek bir yazı veya işaret yok. Çift tıklamayı bir yazının ya da işaretin üstünde deneyin.')

    def add_timeline_media(self):
        index = self.multitrack_view.selected_track
        track = self.multitrack.tracks[index] if index is not None and index < len(self.multitrack.tracks) else None
        if track is None:
            self.set_status('Önce hedef izi seçin.')
            return
        if track.kind not in ('video', 'audio', 'overlay'):
            self.set_status('Bu sürümde medya yalnızca video/ses izine eklenir.')
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Medya seç', '', 'Media (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mp3 *.wav *.m4a)')
        if not path:
            return
        # Probe without decoding the file or relying on an additional ffprobe binary.
        try:
            media = MediaService(ffmpeg_path())
            seconds = media.duration(path)
            timeline_service.validate_track_media(media, track.kind, path)
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f'Medya eklenemedi: {exc}')
            return
        timeline_service.append_media(self.multitrack, index, path, seconds)
        self.media_bin.add(path)
        self.refresh_media_bin()
        self.multitrack_view.refresh_waveforms()
        self.update_timeline_scroll()
        self.seek_timeline(self.timeline_frame)

    def split_clip(self):
        track, clip = self.selected_clip()
        if clip:
            try:
                timeline_service.split_selected(self.multitrack, self.multitrack_view.selected, self.multitrack_view.playhead)
                self.multitrack_view.update()
            except ValueError as exc:
                self.set_status(str(exc))

    def ripple_delete(self):
        track, clip = self.selected_clip()
        if clip:
            track.ripple_delete(clip.id)
            self.multitrack_view.selected = None
            self.update_timeline_scroll()
            self.seek_timeline(self.timeline_frame)

    def seek_timeline(self, frame, *, from_clock=False):
        total = duration_frames(self.multitrack)
        self.update_timeline_scroll()
        if not total:
            self.timeline_frame = 0
            self.time_label.setText('00:00.00 / 00:00.00')
            self.multitrack_view.update()
            return
        self.timeline_frame = min(max(0, frame), total - 1)
        if self.proxy.playing:
            if self.proxy.is_ready(self.proxy_signature()):
                self.proxy.seek(self.timeline_frame)
                self.multitrack_view.playhead = self.timeline_frame
                self.multitrack_view.update()
                return
            self.stop_proxy_playback(refresh=False)  # the edit changed under the playing copy
        self.proxy_timer.start()
        if not from_clock and self.playback_clock.playing:
            self.playback_clock.seek(self.timeline_frame)
        self.sync_timeline_audio(force=not from_clock)
        self.multitrack_view.playhead = self.timeline_frame
        self.multitrack_view.update()
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        self.time_label.setText(f'{format_time(self.timeline_frame/fps)} / {format_time(total/fps)}')
        self.preview.request(self.multitrack, self.timeline_frame, self.canvas_size(), self.render_adjustments())

    def show_timeline_frame(self, path):
        if not self.proxy.playing:
            self.video.set_image(QPixmap(path))

    def advance_timeline(self):
        total = duration_frames(self.multitrack)
        frame = self.playback_clock.position(self.multitrack)
        if total <= 0 or frame >= total:
            self.play_timer.stop()
            self.playback_clock.stop()
            self.timeline_audio.stop()
            self.play_button.setText('▶')
            if total:
                self.seek_timeline(total - 1, from_clock=True)
        elif frame != self.timeline_frame:
            self.seek_timeline(frame, from_clock=True)

    def change_aspect(self, text):
        self.state.aspect = text
        if hasattr(self, 'multitrack_view') and duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)

    def change_export_profile(self, text):
        self.state.export_profile = text
        if text.startswith(('Reels', 'TikTok', '4K Dikey')):
            self.aspect.setCurrentIndex(0)
        elif text.startswith(('YouTube', '4K UHD')):
            self.aspect.setCurrentIndex(1)

    def canvas_size(self):
        return timeline_service.canvas_size(self.aspect.currentText(), self.multitrack, MediaService(ffmpeg_path()))

    def export_canvas_size(self):
        return timeline_service.output_canvas_size(self.aspect.currentText(), self.multitrack,
                                                   MediaService(ffmpeg_path()), self.export_profile.currentText())

    def sync_timeline_audio(self, force=False):
        if self.play_timer.isActive():
            self.preview_audio_output.setVolume(timeline_service.playback_volume(self.multitrack, self.timeline_frame, self.master_volume))
            self.timeline_audio.sync(self.multitrack, self.timeline_frame, self.state.speed, force)

    def change_master_volume(self, value):
        self.master_volume = value / 100
        self.proxy.set_volume(self.master_volume)
        self.sync_timeline_audio()

    def set_clip_volume(self):
        track, clip = self.selected_clip()
        if not clip or track.kind not in ('audio', 'video'):
            self.set_status('Bir ses veya video klibi seçin.')
            return
        value, ok = QInputDialog.getInt(self, 'Klip sesi / Clip volume', 'Ses / Volume (%)', round(clip.volume * 100), 0, 100)
        if ok:
            timeline_service.set_clip_volume(self.multitrack, self.multitrack_view.selected, value / 100)
            self.sync_timeline_audio(force=True)
            self.set_status(f'Klip sesi: %{value}')

    def change_color(self, name, value):
        setattr(self.state, name, value)
        if hasattr(self, 'multitrack_view') and duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)

    def change_speed(self, text):
        self.state.speed = float(text.replace('×', ''))
        if hasattr(self, 'proxy'):
            self.proxy.set_speed(self.state.speed)
        if hasattr(self, 'play_timer') and self.play_timer.isActive():
            self.playback_clock.set_speed(self.multitrack, self.state.speed)
            self.sync_timeline_audio(force=True)

    def render_adjustments(self):
        return {'brightness': self.state.brightness, 'contrast': self.state.contrast,
                'saturation': self.state.saturation, 'speed': self.state.speed}

    def project_document(self) -> dict:
        publish = {'title': self.publish_title.text(),
                   'caption': self.publish_caption.toPlainText(),
                   'hashtags': self.publish_tags.toPlainText()}
        return project_service.make_document(asdict(self.state), self.multitrack, publish,
                                             self.ai_prompt.toPlainText())

    def write_project(self, path: str, snapshot: bool = False) -> None:
        project_service.save_with_snapshot(path, self.project_document(), snapshot)

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
        try:
            self.write_project(path, snapshot=True)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, APP_NAME, f'Proje kaydedilemedi: {exc}')
            return
        self.project_path = path
        self.mark_saved()
        self.set_status("Proje ve sürüm anlık görüntüsü kaydedildi.")

    def project_signature(self) -> str:
        document = self.project_document()
        document.pop('saved_at', None)
        return hashlib.sha1(json.dumps(document, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    def mark_saved(self) -> None:
        self._saved_signature = self.project_signature()

    def has_unsaved_changes(self) -> bool:
        return bool(self.state.source) and self.project_signature() != self._saved_signature

    def confirm_close(self) -> bool:
        """Ask before work is lost. A hidden window (tests, scripted runs) has nobody to ask."""
        if self._close_confirmed or not self.isVisible() or not self.has_unsaved_changes():
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(self, APP_NAME, 'Projede kaydedilmemiş değişiklikler var. Kaydedilsin mi?',
                                      buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        if answer == buttons.Save:
            self.save_project()
            return not self.has_unsaved_changes()
        return answer == buttons.Discard

    def open_project(self) -> None:
        if not self.confirm_close():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Proje aç", "", "Akış projesi (*.akis.json);;JSON (*.json)"
        )
        if not path:
            return
        try:
            document, source_path = project_service.load_with_source(path)
            self._pending_project = document
            if self.load_video(source_path):
                self.project_path = path
            else:
                self._pending_project = None
        except Exception as exc:
            self._pending_project = None
            QMessageBox.critical(self, APP_NAME, str(exc))

    def apply_project_state(self, document: dict) -> None:
        raw = document.get("state", {})
        allowed = set(EditState.__dataclass_fields__)
        merged = {key: value for key, value in raw.items() if key in allowed}
        merged["duration"] = self.state.duration
        self.state = EditState(**merged)
        self.multitrack = Timeline.from_dict(document['timeline']) if 'timeline' in document else Timeline.from_legacy(merged)
        self.multitrack_view.set_model(self.multitrack)
        self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
        self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * len(self.multitrack.tracks))))
        for track in self.multitrack.tracks:
            for clip in track.clips:
                if clip.source:
                    self.media_bin.add(clip.source)
        self.refresh_media_bin()
        self.timeline.set_range(
            self.state.start, min(self.state.end or self.state.duration, self.state.duration), emit=True
        )
        self.aspect.setCurrentText(self.state.aspect)
        self.brightness.setValue(self.state.brightness)
        self.contrast.setValue(self.state.contrast)
        self.saturation.setValue(self.state.saturation)
        self.speed.setCurrentText(f"{self.state.speed:.2f}×")
        self.effect.setCurrentText(self.state.effect)
        self.fade.setChecked(False)
        self.overlay.setText(self.state.overlay_text)
        self.export_profile.blockSignals(True)
        self.export_profile.setCurrentText(self.state.export_profile)
        self.export_profile.blockSignals(False)
        self.noise_reduction.setChecked(self.state.noise_reduction)
        self.loudness.setChecked(False)
        publish = document.get("publish", {})
        self.publish_title.setText(publish.get("title", ""))
        self.publish_caption.setPlainText(publish.get("caption", ""))
        self.publish_tags.setPlainText(publish.get("hashtags", ""))
        self.ai_prompt.setPlainText(document.get("ai_prompt", self.ai_prompt.toPlainText()))
        self.update_timeline_scroll()
        if duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)
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

    def closeEvent(self, event):
        if self._workers:
            self.set_status('İşlem devam ediyor; kapatmadan önce bitmesini bekleyin.')
            event.ignore()
            return
        if not self.confirm_close():
            event.ignore()
            return
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        if self.update_download and self.update_download.isRunning():
            self.update_download.wait()
        if self.update_check and self.update_check.isRunning():
            self.update_check.wait()
        self.proxy_timer.stop()
        self.proxy.close()
        self.preview.close()
        self.multitrack_view.stop_waveforms()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in VIDEO_EXTS:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.add_video(urls[0].toLocalFile())
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
    if len(sys.argv) == 3 and sys.argv[1] == '--audio-diagnostic':
        from akis.audio_diagnostic import diagnose
        Path(sys.argv[2]).write_text(json.dumps(diagnose(), ensure_ascii=False, indent=2), encoding='utf-8')
    elif len(sys.argv) == 3 and sys.argv[1] == '--whisper-diagnostic':
        from akis.whisper_diagnostic import diagnose
        try:
            report = diagnose()
        except Exception as exc:
            report = {'status': 'failed', 'reason': str(exc)}
        Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if report['status'] != 'passed':
            raise SystemExit(1)
    else:
        raise SystemExit(main())

