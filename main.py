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
from akis.update_worker import UpdateCheckWorker, UpdateDownloadWorker
from akis.ai_service import plan_prompt, parse_suggestions, add_plan_markers
from akis.caption_worker import LocalCaptionWorker
from akis.tts_worker import TtsWorker
from akis.ai_workers import AIWorker, TranscriptWorker
from akis.media_bin import MediaBin
from akis.caption_service import caption_track
from akis import ai_providers
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
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.project_path = ""
        self._pending_project: dict | None = None
        self.worker: QThread | None = None
        self._workers = set()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1180, 760)
        self.resize(1500, 920)
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
        self.video.setMinimumSize(320, 200)
        self.video.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
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
        self.master_volume = 0.8
        volume.valueChanged.connect(self.change_master_volume)
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
        v.addLayout(tools)
        self.multitrack_view = MultitrackWidget(self.multitrack)
        self.multitrack_view.waveform_executable = ffmpeg_path
        self.multitrack_view.seek.connect(self.seek_timeline)
        self.multitrack_view.changed.connect(lambda: self.seek_timeline(self.timeline_frame))
        v.addWidget(self.multitrack_view)
        self.timeline = TimelineBar()
        self.timeline.setEnabled(False)
        self.timeline.setToolTip("Eski aralık seçimi ortak timeline çıktısını etkilemez; bölme aracını kullanın.")
        self.timeline.range_changed.connect(self.on_timeline_range)
        self.timeline.seek_requested.connect(lambda sec: self.seek_timeline(round(sec * self.multitrack.fps_num / self.multitrack.fps_den)))
        v.addWidget(self.timeline)

        trims = QHBoxLayout()
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

        v.addWidget(self.section("KURGU TERCİHLERİ / EDIT OPTIONS"))
        options = QFormLayout()
        self.ai_platform = QComboBox(); self.ai_platform.addItems(['Reels', 'TikTok', 'YouTube Shorts', 'General'])
        self.ai_tempo = QComboBox(); self.ai_tempo.addItems(['Slow', 'Medium', 'Fast', 'Dynamic'])
        self.ai_style = QComboBox(); self.ai_style.addItems(['Cinematic', 'Energetic', 'Minimal', 'Educational', 'Storytelling'])
        self.ai_focus = QComboBox(); self.ai_focus.addItems(['Hook first', 'Highlights', 'Full story', 'Product', 'Tutorial'])
        for label, widget in [('Platform', self.ai_platform), ('Tempo', self.ai_tempo), ('Stil / Style', self.ai_style), ('Odak / Focus', self.ai_focus)]:
            options.addRow(label, widget)
        v.addLayout(options)
        v.addWidget(self.section("YAPAY ZEKÂ HEDEFİ"))
        self.ai_prompt = QPlainTextEdit()
        self.ai_prompt.setPlaceholderText("Örn. İlk 2 saniyesi güçlü, dinamik bir Reels kurgusu. Ürün net görünsün, ton güven veren olsun.")
        self.ai_prompt.setPlainText("İlk saniyeleri güçlü, tempolu ve profesyonel bir Reels kurgusu oluştur. En ilgi çekici bölümü öne çıkar.")
        self.ai_prompt.setFixedHeight(112)
        v.addWidget(self.ai_prompt)

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

        analyze = QPushButton("✦  AI ile kurguyu planla")
        analyze.setObjectName("primaryLarge")
        analyze.clicked.connect(self.run_ai)
        v.addWidget(analyze)
        self.ai_suggestions = []
        self.ai_choice = QComboBox()
        self.ai_choice.currentIndexChanged.connect(self.show_ai_suggestion)
        v.addWidget(self.ai_choice)
        apply_plan = QPushButton('Seçili öneriyi işaretlere uygula / Apply markers')
        apply_plan.clicked.connect(self.apply_ai_suggestion)
        v.addWidget(apply_plan)
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
        self.speed.currentTextChanged.connect(self.change_speed)
        v.addWidget(self.speed)
        self.fade = QCheckBox("Yumuşak giriş ve çıkış geçişi")
        self.fade.setChecked(True)
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
        self.export_profile.currentTextChanged.connect(lambda text: setattr(self.state, "export_profile", text))
        v.addWidget(self.export_profile)
        self.noise_reduction = QCheckBox("Temel gürültü azaltma")
        self.noise_reduction.setEnabled(False)
        self.noise_reduction.setToolTip("Ortak timeline render yolunda henüz desteklenmiyor.")
        self.noise_reduction.toggled.connect(lambda checked: setattr(self.state, "noise_reduction", checked))
        v.addWidget(self.noise_reduction)
        self.loudness = QCheckBox("Ses yüksekliğini -14 LUFS'a normalleştir")
        self.loudness.setChecked(True)
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
            self.load_video(path)

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
        self.on_duration(round(duration * 1000))
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
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.playback_clock.stop()
            self.timeline_audio.stop()
            self.play_button.setText('▶')
        else:
            if not duration_frames(self.multitrack):
                return
            self.playback_clock.start(self.timeline_frame, self.state.speed)
            self.play_timer.start(15)
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
        self.state.overlay_text = self.overlay.text()
        self.state.aspect = self.aspect.currentText()
        self.state.export_profile = self.export_profile.currentText()
        self.begin_work("Dışa aktarma hazırlanıyor…")
        self.worker = TimelineRenderWorker(self.multitrack, path, self.canvas_size(), ffmpeg_path(), adjustments=self.render_adjustments())
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
        import base64
        payload = base64.b64encode(json.dumps({'pid': os.getpid(), 'installer': installer, 'app': sys.executable}).encode('utf-8')).decode('ascii')
        script = "$d=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + payload + "'))|ConvertFrom-Json; Wait-Process -Id $d.pid -ErrorAction SilentlyContinue; $p=Start-Process -FilePath $d.installer -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-' -Wait -PassThru; if($p.ExitCode -eq 0){Start-Process -FilePath $d.app}"
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], creationflags=subprocess.CREATE_NO_WINDOW)
        self.close()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def timeline_zoom(self, value):
        self.multitrack_view.zoom = value / 10
        self.multitrack_view.update()

    def selected_clip(self):
        return timeline_service.selected_clip(self.multitrack, self.multitrack_view.selected)

    def add_track(self):
        kind, ok = QInputDialog.getItem(self, 'İz ekle / Add track', 'Tür / Type', ['video', 'audio', 'text', 'overlay'], 0, False)
        if ok:
            self.multitrack.tracks.append(Track(kind, f'{kind.title()} {len(self.multitrack.tracks)+1}'))
            self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * len(self.multitrack.tracks)))
            self.multitrack_view.update()

    def remove_track(self):
        index = self.multitrack_view.selected_track
        if index is None:
            self.set_status('Silinecek izi seçin.')
            return
        self.multitrack.tracks.pop(index)
        self.multitrack_view.selected = None
        self.multitrack_view.selected_track = None
        self.multitrack_view.update()

    def edit_text_clip(self):
        track, clip = self.selected_clip()
        if not clip or track.kind != 'text':
            self.set_status('Önce bir metin klibi seçin.')
            return
        value, ok = QInputDialog.getMultiLineText(self, 'Metni düzenle', 'Başlık / altyazı', clip.text)
        if ok:
            clip.text = value
            self.multitrack_view.update()
            self.seek_timeline(self.timeline_frame)

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
            seconds = MediaService(ffmpeg_path()).duration(path)
        except ValueError:
            QMessageBox.warning(self, APP_NAME, 'Medya süresi okunamadı.')
            return
        timeline_service.append_media(self.multitrack, index, path, seconds)
        self.media_bin.add(path)
        self.refresh_media_bin()
        self.multitrack_view.refresh_waveforms()
        self.multitrack_view.update()

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
            self.multitrack_view.update()

    def seek_timeline(self, frame, *, from_clock=False):
        total = duration_frames(self.multitrack)
        if not total:
            return
        self.timeline_frame = min(max(0, frame), total - 1)
        if not from_clock and self.playback_clock.playing:
            self.playback_clock.seek(self.timeline_frame)
        self.sync_timeline_audio(force=not from_clock)
        self.multitrack_view.playhead = self.timeline_frame
        self.multitrack_view.update()
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        self.time_label.setText(f'{format_time(self.timeline_frame/fps)} / {format_time(total/fps)}')
        self.preview.request(self.multitrack, self.timeline_frame, self.canvas_size(), self.render_adjustments())

    def show_timeline_frame(self, path):
        pixmap = QPixmap(path)
        self.video.setPixmap(pixmap.scaled(self.video.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

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

    def canvas_size(self):
        return timeline_service.canvas_size(self.aspect.currentText(), self.multitrack, MediaService(ffmpeg_path()))

    def sync_timeline_audio(self, force=False):
        if self.play_timer.isActive():
            self.preview_audio_output.setVolume(timeline_service.playback_volume(self.multitrack, self.timeline_frame, self.master_volume))
            self.timeline_audio.sync(self.multitrack, self.timeline_frame, self.state.speed, force)

    def change_master_volume(self, value):
        self.master_volume = value / 100
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
            document, source_path = project_service.load_with_source(path)
            self.project_path = path
            self._pending_project = document
            self.load_video(source_path)
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

    def closeEvent(self, event):
        if self._workers:
            self.set_status('İşlem devam ediyor; kapatmadan önce bitmesini bekleyin.')
            event.ignore()
            return
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        if self.update_download and self.update_download.isRunning():
            self.update_download.wait()
        if self.update_check and self.update_check.isRunning():
            self.update_check.wait()
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

