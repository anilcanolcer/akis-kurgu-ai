from __future__ import annotations

import contextlib
import copy
import faulthandler
import hashlib
import json
import logging
import logging.handlers
import math
import os
import traceback
import re
import shutil
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
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
from akis.update_dialog import UpdateProgressDialog
from akis.ai_service import plan_prompt, add_plan_markers, format_suggestion
from akis.caption_worker import LocalCaptionWorker
from akis.tts_worker import TtsWorker
from akis.ai_workers import AIWorker, PromptEditWorker, TranscriptWorker
from akis import edit_plan
from akis.media_bin import MediaBin
from akis.caption_service import caption_track
from akis import ai_providers, update_service
from akis import template_service
from akis import i18n
from akis.template_dialog import TemplateDialog
from akis.inspiration_dialog import InspirationDialog
from akis.silence_dialog import SilenceDialog
from akis import export_progress
from akis import shortcuts
from akis import speech_settings
from akis import clip_fit
from akis import preflight
from akis import user_templates
from akis.saved_templates_dialog import SavedTemplatesDialog
from akis.inspiration_service import template_for
from akis.story_dialog import StoryDialog
from akis.temp_cleanup import cleanup_stale_temp_dirs

from PySide6.QtCore import QByteArray, QLocale, QLockFile, QSettings, QStandardPaths, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QImage, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
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
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Akış Kurgu AI"
ORG_NAME = "AkisStudio"
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


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


log = logging.getLogger("akis")
log.addHandler(logging.NullHandler())  # without setup_logging (tests, tools) records are dropped, not printed
RECOVERY_QUESTION = "Kurtarılmış çalışma bulundu ({when}). Açılsın mı?"
RECOVERY_DETAIL = ("“Sonra sor” şimdilik açmaz, dosyayı saklar ve daha sonra yeniden sorar. "
                   "“Sil” kurtarma dosyasını kalıcı olarak siler.")
IDEA_REPLACES_PROMPT_QUESTION = "Kurgu isteği kutusunda yazdığınız bir metin var. Fikirle değiştirilsin mi?"
STALE_PLAN_QUESTION = "Zaman çizelgesi bu sırada değişti. Plan yine de uygulansın mı?"
UPDATE_REMIND_AFTER = 24 * 3600  # a postponed update is not offered again for this many seconds
CANCEL_ON_CLOSE_QUESTION = "Devam eden işlem iptal edilip çıkılsın mı?"
THREAD_STOP_WAIT_MS = 2000  # how long closing the window waits for a background thread
UNDO_LIMIT = 50  # timeline edit steps kept for undo
STILL_CLIP_SECONDS = 5  # a generated still image is added to the timeline as a clip of this length
_background_threads: list[QThread] = []  # still stopping after their window closed; waited for in main()


def start_temp_cleanup(root=None) -> threading.Thread:
    """Remove scratch folders a crash left in the temp directory, off the GUI thread (a big folder or a
    slow disk must not delay the window). Never raises; the thread is a daemon so it cannot block exit."""
    thread = threading.Thread(target=cleanup_stale_temp_dirs, args=(root,), name="akis-temp-cleanup", daemon=True)
    thread.start()
    return thread


def wait_for_background_threads() -> None:
    """After the event loop: let interrupted update threads end so none is destroyed while running."""
    while _background_threads:
        thread = _background_threads.pop()
        if not thread.wait((update_service.READ_TIMEOUT + 5) * 1000):
            log.warning("Arka plan işi zamanında bitmedi")


def app_data_dir() -> Path:
    """Per-user folder for logs and untitled-project recovery files."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))


def recovery_dir() -> Path:
    return app_data_dir() / "recovery"


def recovery_lock(path: Path) -> QLockFile:
    """Lock owned by the instance writing an untitled recovery file.

    QLockFile records the owner's pid and, on Windows, keeps the file open, so a live instance's lock can
    neither be taken nor deleted; once its process is gone the lock counts as stale and can be taken over.
    Age-based staleness is off: an instance may run for hours.
    """
    lock = QLockFile(str(path.with_name(path.name.removesuffix(".akis.json") + ".lock")))
    lock.setStaleLockTime(0)
    return lock


def orphan_recovery_files(folder: Path | None = None) -> list[tuple[Path, QLockFile]]:
    """Untitled recovery files whose writer is no longer running, newest first, each with its lock now held."""
    folder = recovery_dir() if folder is None else folder
    if not folder.is_dir():
        return []
    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    found = []
    own = f"recovery-{os.getpid()}.akis.json"
    for path in sorted(folder.glob("recovery-*.akis.json"), key=modified, reverse=True):
        if path.name == own:
            continue
        lock = recovery_lock(path)
        if lock.tryLock(0):
            found.append((path, lock))
    return found


def normalize_export_path(path: str) -> str:
    """`klip` -> `klip.mp4`; a known video extension (`klip.mov`) is replaced rather than doubled."""
    file = Path(path)
    if file.suffix.lower() == ".mp4":
        return path
    if file.suffix.lower() in VIDEO_EXTS:
        return str(file.with_suffix(".mp4"))
    return path + ".mp4"


_log_handler: logging.Handler | None = None
_crash_log = None


def setup_logging(folder: Path) -> Path:
    """Rotating application log plus a faulthandler crash log; the packaged app has no console."""
    global _log_handler, _crash_log
    folder.mkdir(parents=True, exist_ok=True)
    log_path = folder / "akis.log"
    if _log_handler is None:
        _log_handler = logging.handlers.RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        _log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.addHandler(_log_handler)
        root.setLevel(logging.INFO)
    if _crash_log is None:
        try:
            _crash_log = open(folder / "crash.log", "a", encoding="utf-8")
            faulthandler.enable(file=_crash_log, all_threads=True)
        except OSError:
            log.exception("Çökme günlüğü açılamadı")
    return log_path


class ExceptionHook:
    """sys.excepthook: logs every uncaught exception and, on the GUI thread, shows a short message."""

    def __init__(self, log_path: Path | None = None, show_dialogs: bool = True) -> None:
        self.log_path = log_path
        self.show_dialogs = show_dialogs
        self._active = False

    def __call__(self, exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Yakalanmamış hata:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if not self.show_dialogs or self._active:
            return  # re-entrant: an error while showing the previous message is only logged
        # No dialog before a QApplication exists, nor from a worker thread (widgets are GUI-thread only).
        if QApplication.instance() is None or threading.current_thread() is not threading.main_thread():
            return
        self._active = True
        try:
            text = f"Beklenmeyen bir hata oluştu: {exc}"
            if self.log_path:
                text += f"\n\nAyrıntılar günlük dosyasına yazıldı:\n{self.log_path}"
            QMessageBox.critical(None, APP_NAME, text)
        except Exception:
            log.exception("Hata iletisi gösterilemedi")
        finally:
            self._active = False


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


@dataclass
class EditState:
    source: str = ""
    duration: float = 0.0
    start: float = 0.0
    end: float = 0.0
    # Choice keys (akis.i18n), never the text a combo shows: the canonical Turkish item text.
    aspect: str = i18n.DEFAULT_ASPECT
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    speed: float = 1.0
    export_profile: str = i18n.DEFAULT_EXPORT_PROFILE
    # Sound clean-up switches (akis.audio_polish), saved with the project.
    audio_level: bool = False
    audio_denoise: bool = False
    audio_duck: bool = False
    # effect/fade/noise_reduction/loudness_normalization/overlay_text were dropped: their controls are
    # permanently disabled. apply_project_state ignores unknown keys, so older files holding them still load.
    ai_title: str = ""
    ai_caption: str = ""
    ai_hashtags: str = ""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = EditState()
        self.media_bin = MediaBin()
        self._source_rate = (30, 1)  # frame rate of the video loaded last; a new timeline adopts it
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
        # A failed proxy render only blocks that exact edit; any change makes smooth playback eligible again.
        self._proxy_failed_signature = None
        self._proxy_requested = None
        self._play_when_ready = False
        self.proxy_timer = QTimer(self)
        self.proxy_timer.setSingleShot(True)
        self.proxy_timer.setInterval(900)
        self.proxy_timer.timeout.connect(self.prepare_proxy)
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.project_path = ""
        self._saved_signature = None  # project contents as last saved or opened
        self._close_confirmed = False
        self._shutting_down = False  # set by closeEvent; late update signals are then ignored
        self._pending_project: dict | None = None
        self._autosave_file = ""  # last autosave/recovery file this window wrote
        self._recovery_lock: QLockFile | None = None  # held while our untitled recovery file exists
        self._prompt_revision = None  # timeline_revision() when the running prompt edit started
        self.worker: QThread | None = None
        self._workers = set()
        # Edit history: each step is {'before': edit_snapshot(), 'after': edit_snapshot()} around one action.
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._drag_before = None  # edit_snapshot() taken when a timeline drag began
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
        # Window-wide; a focused text field keeps Ctrl+Z / Ctrl+Y for its own text (it overrides the shortcut).
        self.undo_action = QAction(self)
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction(self)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.redo_action.triggered.connect(self.redo)
        # Ctrl shortcuts work everywhere; Space and Delete stand back while a text field has focus.
        self.shortcut_actions = {}
        for keys, slot in (("Ctrl+S", "save_project"), ("Ctrl+O", "open_project"),
                           ("Ctrl+E", "export_video"), ("Space", "shortcut_play"),
                           ("Delete", "shortcut_delete")):
            action = QAction(self)
            action.setShortcut(QKeySequence(keys))
            action.triggered.connect(lambda _checked=False, slot=slot: getattr(self, slot)())
            self.shortcut_actions[keys] = action
        for action in (self.undo_action, self.redo_action, *self.shortcut_actions.values()):
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            self.addAction(action)
        self.update_history_controls()
        self.shortcut_filter = shortcuts.install(self)  # Space, S, Delete, arrows, Ctrl+S/O/E/I, F1

        self._provider_keys = {}
        self.story_dialog = None
        self._saved_providers = set()
        self._active_provider = self.provider.currentText()
        self.provider.currentTextChanged.connect(self.change_provider)
        self.load_key()
        # Tests and scripted runs (offscreen) neither restore nor overwrite the user's saved window layout.
        self._persist_ui = QApplication.platformName() not in ("offscreen", "minimal")
        if self._persist_ui:
            self.restore_ui_settings(self.settings)
        self.apply_language(self.settings.value("language", self.system_language_code()))
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30_000)
        self.autosave_timer.timeout.connect(self.autosave_project)
        self.autosave_timer.start()
        self.update_check = None
        self.update_download = None
        self._update = None  # the release being downloaded or waiting to be installed
        self._update_percent = -1
        self._declined_updates = set()  # versions the user postponed in this session
        self._update_target: Path | None = None
        self.update_dialog: UpdateProgressDialog | None = None
        if getattr(sys, '_MEIPASS', None) and sys.platform == 'win32':
            QTimer.singleShot(0, self.report_update_result)
            QTimer.singleShot(5000, self.check_for_updates)
        self.set_status(self.ui_text("Bir video sürükleyin veya “Video ekle” düğmesini kullanın."))

    def restore_ui_settings(self, settings) -> None:
        """AI provider and model, window geometry and splitter sizes from the last session. A value that is
        missing, of the wrong type or unknown is ignored, so a damaged setting never breaks the window."""
        provider = settings.value("ui/provider", "")
        if isinstance(provider, str) and provider in ai_providers.PROVIDERS and provider != self.provider.currentText():
            self.provider.setCurrentText(provider)
        model = settings.value("ui/model", "")
        if isinstance(model, str) and 0 < len(model.strip()) <= 200:
            self.model.setCurrentText(model.strip())
        geometry = settings.value("ui/geometry")
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)
        sizes = settings.value("ui/splitter")
        try:
            sizes = [int(size) for size in sizes] if isinstance(sizes, (list, tuple)) else []
        except (TypeError, ValueError):
            sizes = []
        if len(sizes) == self.splitter.count() and all(100 <= size <= 20000 for size in sizes):
            self.splitter.setSizes(sizes)

    def save_ui_settings(self, settings) -> None:
        settings.setValue("ui/provider", self.provider.currentText())
        settings.setValue("ui/model", self.model.currentText().strip())
        settings.setValue("ui/geometry", self.saveGeometry())
        settings.setValue("ui/splitter", [int(size) for size in self.splitter.sizes()])

    def text_has_focus(self) -> bool:
        """A field the user types into has the keyboard: single-key shortcuts must leave the key to it."""
        widget = QApplication.focusWidget()
        return (isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox))
                or (isinstance(widget, QComboBox) and widget.isEditable()))

    def shortcut_play(self) -> None:
        if not self.text_has_focus() and duration_frames(self.multitrack):
            self.toggle_play()

    def shortcut_delete(self) -> None:
        if not self.text_has_focus():
            self.delete_clip()

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
            ("Projeler", "▦"), ("İlham", "✦"), ("Şablonlar", "◈"), ("Hikâye Stüdyosu", "✎"), ("Dışa aktarımlar", "⇧")
        ]):
            # The whole label (icon included) is the EN_UI key, so apply_language translates it.
            button = QPushButton(f"{icon}   {text}")
            button.setProperty("nav", True)
            button.setProperty("active", index == 0)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if index == 0:
                button.clicked.connect(lambda: self.set_status(self.ui_text("Proje düzenleyicisi açık.")))
            elif index == 1:
                button.clicked.connect(self.show_inspiration)
            elif index == 2:
                button.clicked.connect(self.show_templates)
            elif index == 3:
                button.clicked.connect(self.show_story_studio)
            else:
                button.clicked.connect(lambda: self.set_status(self.ui_text("Dışa aktarmak için üstteki düğmeyi kullanın.")))
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
        # The running version, always in view; a click asks GitHub whether a newer one exists.
        self.version_button = QPushButton(f"v{update_service.VERSION}")
        self.version_button.setObjectName("versionTag")
        self.version_button.setProperty("i18n_skip", True)  # a version number, the same in every language
        self.version_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_button.clicked.connect(lambda: self.check_for_updates(manual=True))
        v.addWidget(self.version_button)
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
        # User content once a video is loaded (file name and size); apply_language only rewrites the
        # placeholders while there is no video.
        for label in (self.project_title, self.project_subtitle):
            label.setProperty("i18n_skip", True)
        title_box.addWidget(self.project_title)
        title_box.addWidget(self.project_subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(300)
        self.status_label.setProperty("i18n_skip", True)  # messages can quote file names and errors
        header.addWidget(self.status_label)
        open_project = QPushButton("Proje aç")
        open_project.setObjectName("ghost")
        open_project.setToolTip("Kayıtlı bir projeyi açar (Ctrl+O)")
        open_project.clicked.connect(self.open_project)
        header.addWidget(open_project)
        save_project = QPushButton("Projeyi kaydet")
        save_project.setObjectName("secondary")
        save_project.setToolTip("Projeyi kaydeder (Ctrl+S)")
        save_project.clicked.connect(self.save_project)
        header.addWidget(save_project)
        export = QPushButton("Dışa aktar  ↗")
        export.setObjectName("primary")
        export.setToolTip("Videoyu MP4 olarak dışa aktarır (Ctrl+E)")
        export.clicked.connect(self.export_video)
        header.addWidget(export)
        outer.addLayout(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self.build_editor())
        split.addWidget(self.build_inspector())
        split.setSizes([900, 390])
        self.splitter = split
        outer.addWidget(split, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 1, Qt.AlignmentFlag.AlignVCenter)
        # Shown while a worker runs; enabled only when that worker can be stopped (it has cancel()).
        self.cancel_button = QPushButton("İptal")
        self.cancel_button.setObjectName("ghost")
        self.cancel_button.setToolTip("Devam eden işlemi durdurur.")
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel_work)
        progress_row.addWidget(self.cancel_button)
        outer.addLayout(progress_row)
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
        # Zooming in (or a larger window) needs a sharper still; wait until the gesture has settled.
        self.still_timer = QTimer(self)
        self.still_timer.setSingleShot(True)
        self.still_timer.setInterval(250)
        self.still_timer.timeout.connect(self.refresh_still)
        self.video.zoom_changed.connect(lambda _zoom: self.still_timer.start())
        self.video.resized.connect(self.still_timer.start)
        v.addWidget(self.video, 1)

        controls = QHBoxLayout()
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("roundButton")
        self.play_button.setFixedSize(40, 40)
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setToolTip("Oynat / duraklat (Boşluk)")  # the button is i18n_skip: apply_language sets it
        controls.addWidget(self.play_button)
        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setObjectName("mono")
        for dynamic in (self.play_button, self.time_label):
            dynamic.setProperty("i18n_skip", True)
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
                              ('Ripple sil', self.ripple_delete), ('Klip sesi', self.set_clip_volume), ('Kadraj', self.set_clip_fit), ('Metni düzenle', self.edit_text_clip)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            if label == 'Ripple sil':
                button.setToolTip('Seçili klibi siler ve boşluğu kapatır. Delete tuşu klibi boşluk bırakarak siler.')
            tools.addWidget(button)
        self.undo_button = QPushButton('↶ Geri al')
        self.undo_button.setToolTip('Son adımı geri al (Ctrl+Z)')
        self.undo_button.clicked.connect(self.undo)
        tools.addWidget(self.undo_button)
        self.redo_button = QPushButton('↷ Yinele')
        self.redo_button.setToolTip('Geri alınan adımı yinele (Ctrl+Y)')
        self.redo_button.clicked.connect(self.redo)
        tools.addWidget(self.redo_button)
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
        self.multitrack_view.edit_started.connect(self.on_timeline_drag_started)
        self.multitrack_view.changed.connect(self.on_timeline_dragged)
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
        silence_button = QPushButton("Sessizlikleri çıkar")
        silence_button.setObjectName("secondary")
        silence_button.setToolTip("Konuşma olmayan yerleri keser. Yapay zekâ, anahtar ve internet gerekmez.")
        silence_button.clicked.connect(self.remove_silences)
        v.addWidget(silence_button)
        # Undoes the last step of the shared edit history; right after an AI edit that is the AI edit.
        self.undo_edit_button = QPushButton("↶  Son adımı geri al")
        self.undo_edit_button.setObjectName("secondary")
        self.undo_edit_button.setToolTip("AI kurgusu dahil son düzenlemeyi geri alır (Ctrl+Z).")
        self.undo_edit_button.setEnabled(False)
        self.undo_edit_button.clicked.connect(self.undo)
        v.addWidget(self.undo_edit_button)
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
        self.remember_key.clicked.connect(self.on_remember_key_clicked)  # user clicks only, not load_key
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
        # Item data is the value sent to the model, whatever the item shows.
        self.ai_platform = self.keyed_combo(['Reels', 'TikTok', 'YouTube Shorts', 'General'])
        self.ai_tempo = self.keyed_combo(['Slow', 'Medium', 'Fast', 'Dynamic'])
        self.ai_style = self.keyed_combo(['Cinematic', 'Energetic', 'Minimal', 'Educational', 'Storytelling'])
        self.ai_focus = self.keyed_combo(['Hook first', 'Highlights', 'Full story', 'Product', 'Tutorial'])
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
        v.addWidget(QLabel('Konuşma dili'))
        self.speech_language = QComboBox()
        for code, name, _ in speech_settings.LANGUAGES:
            self.speech_language.addItem(name, code)
        self.speech_language.setProperty("i18n_skip", True)  # language names are shown in their own language
        self.speech_language.setToolTip('Altyazı ve konuşma metni bu dilde çözümlenir.')
        v.addWidget(self.speech_language)
        self.speech_vocabulary = QLineEdit()
        self.speech_vocabulary.setPlaceholderText('Özel adlar ve terimler, virgülle (örn. Anılcan, Akış Kurgu)')
        self.speech_vocabulary.setToolTip('Yanlış yazılan isimleri ve terimleri buraya ekleyin; tanıma bunları bekler.')
        v.addWidget(self.speech_vocabulary)
        self.load_speech_settings()
        self.speech_language.activated.connect(lambda _index: self.save_speech_settings())
        self.speech_vocabulary.editingFinished.connect(self.save_speech_settings)
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

    def load_speech_settings(self) -> None:
        speech_settings.set_current(str(self.settings.value("speech/language", speech_settings.DEFAULT_LANGUAGE)),
                                    str(self.settings.value("speech/vocabulary", "") or ""))
        chosen = speech_settings.language() or speech_settings.AUTO
        self.speech_language.setCurrentIndex(max(0, self.speech_language.findData(chosen)))
        self.speech_vocabulary.setText(speech_settings.vocabulary())

    def save_speech_settings(self) -> None:
        """The user changed the speech language or the term list: use it from now on and remember it."""
        speech_settings.set_current(self.speech_language.currentData(), self.speech_vocabulary.text())
        self.speech_vocabulary.setText(speech_settings.vocabulary())
        self.settings.setValue("speech/language", speech_settings.language() or speech_settings.AUTO)
        self.settings.setValue("speech/vocabulary", speech_settings.vocabulary())

    def section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def keyed_combo(keys) -> QComboBox:
        """A combo whose items carry a stable key as item data; the shown text may be translated."""
        combo = QComboBox()
        for key in keys:
            combo.addItem(key, key)
        combo.setProperty("i18n_keyed", True)
        return combo

    @staticmethod
    def select_choice(combo: QComboBox, key) -> bool:
        """Select the item whose key is `key`; returns False (selection unchanged) when there is none."""
        index = combo.findData(key)
        if index < 0:
            return False
        combo.setCurrentIndex(index)
        return True

    def select_aspect(self, value) -> str:
        """Select an aspect from a key, an older file's display text (Turkish or English) or a bare ratio."""
        key = i18n.choice_key(i18n.ASPECTS, value)
        if key is None:
            log.warning("Bilinmeyen tuval oranı %r; varsayılan kullanılıyor", value)
            key = i18n.DEFAULT_ASPECT
        self.select_choice(self.aspect, key)
        return key

    def select_export_profile(self, value) -> str:
        key = i18n.choice_key(i18n.EXPORT_PROFILES, value)
        if key is None:
            log.warning("Bilinmeyen dışa aktarma profili %r; varsayılan kullanılıyor", value)
            key = i18n.DEFAULT_EXPORT_PROFILE
        self.select_choice(self.export_profile, key)
        return key

    def select_speed(self, value) -> float:
        """Select the offered speed nearest to `value` (1.25, '1.25×'). Raises ValueError for a non-number."""
        speed = i18n.speed_key(value)
        self.select_choice(self.speed, speed)
        return speed

    def speed_value(self) -> float:
        return float(self.speed.currentData())

    def refresh_timeline_view(self) -> None:
        """Size the track view and its scroll area for the current number of tracks."""
        tracks = len(self.multitrack.tracks)
        self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * tracks))
        self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * tracks)))

    def build_edit_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(14)
        v.addWidget(self.section("TUVAL ORANI"))
        self.aspect = self.keyed_combo(i18n.ASPECTS)
        self.aspect.currentIndexChanged.connect(lambda _index: self.change_aspect(self.aspect.currentData()))
        v.addWidget(self.aspect)

        v.addWidget(self.section("HIZ VE GEÇİŞ"))
        self.speed = QComboBox()
        for value in i18n.SPEEDS:
            self.speed.addItem(f"{value:.2f}×", value)
        self.select_speed(1.0)
        self.speed.currentIndexChanged.connect(lambda _index: self.change_speed(self.speed.currentData()))
        v.addWidget(self.speed)
        # Not supported by the shared timeline renderer yet: shown disabled, not saved in projects.
        self.fade = QCheckBox("Yumuşak giriş ve çıkış geçişi (henüz yok)")
        self.fade.setEnabled(False)
        self.fade.setToolTip("Ortak timeline render yolunda henüz desteklenmiyor.")
        v.addWidget(self.fade)

        v.addWidget(self.section("GÖRÜNÜM EFEKTİ"))
        self.effect = self.keyed_combo(i18n.EFFECTS)
        self.effect.setEnabled(False)
        self.effect.setToolTip("Ortak timeline render yolunda henüz desteklenmiyor.")
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
        self.overlay.setPlaceholderText("Videoda görünecek kısa başlık (henüz yok)")
        self.overlay.setEnabled(False)
        self.overlay.setToolTip("Bu kontrol ortak timeline render yolunda henüz desteklenmiyor.")
        v.addWidget(self.overlay)
        # The overlay field is disabled and not exported; say so instead of describing how it would export.
        hint = QLabel("Başlık katmanı henüz yok. Videoya yazıyı AI kurgusu, şablonlar veya altyazılar ekler.")
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
        slider.value_label = value  # kept current by hand when a value is restored with signals blocked
        layout.addWidget(slider)
        return slider

    def build_publish_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(12)
        v.addWidget(self.section("YAYIN PAKETİ"))
        v.addWidget(QLabel("Dışa aktarma profili"))
        self.export_profile = self.keyed_combo(i18n.EXPORT_PROFILES)
        self.export_profile.currentIndexChanged.connect(
            lambda _index: self.change_export_profile(self.export_profile.currentData()))
        v.addWidget(self.export_profile)
        profile_hint = QLabel('Profil oranı seçer; 4K seçenekleri seçili oranı iki kat çözünürlükte dışa aktarır.')
        profile_hint.setWordWrap(True)
        v.addWidget(profile_hint)
        v.addWidget(self.section("SES İYİLEŞTİRME"))
        self.loudness = QCheckBox("Ses yüksekliğini -14 LUFS'a normalleştir")
        self.loudness.setToolTip("Kısık çekilmiş videoyu yayın düzeyine çıkarır; önizlemede ve dışa aktarmada uygulanır.")
        self.noise_reduction = QCheckBox("Temel gürültü azaltma")
        self.noise_reduction.setToolTip("Videonun kendi sesindeki uğultu ve hışırtıyı hafifletir; müziğe dokunmaz. Sonucu dinleyerek karar verin.")
        self.music_duck = QCheckBox("Konuşurken müziği kıs")
        self.music_duck.setToolTip("Videoda biri konuşurken ses izlerindeki müzik alçalır, susunca geri yükselir.")
        for box, name in self.audio_boxes():
            box.toggled.connect(lambda checked, name=name: self.change_audio(name, checked))
            v.addWidget(box)
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
            with self.history_step():
                timeline_service.append_video(self.multitrack, str(file), seconds, self.multitrack_view.selected_track)
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f'Video eklenemedi: {exc}')
            return
        self.media_bin.add(str(file))
        self.refresh_media_bin()
        self.refresh_timeline_view()
        self.multitrack_view.refresh_waveforms()
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('Video zaman çizelgesine eklendi.'))

    def load_video(self, path: str) -> bool:
        """Make `path` the main video; returns False (and has told the user why) when it was refused."""
        if not self.can_start_work():  # a running worker would deliver its result into the new video
            return False
        file = Path(path)
        if file.suffix.lower() not in VIDEO_EXTS or not file.is_file():
            QMessageBox.warning(self, APP_NAME, "Desteklenen bir video dosyası seçin.")
            return False
        try:
            media = MediaService(ffmpeg_path())
            duration = media.duration(str(file))
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return False
        try:  # a new project runs at its first video's own frame rate
            self._source_rate = media.frame_rate(str(file)) or (30, 1)
        except (ValueError, RuntimeError, OSError):
            self._source_rate = (30, 1)
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        # Work done before the first main video (a template, ＋ Medya clips, text) is kept: the video is
        # appended to that timeline instead of replacing it, and the work stays unsaved until it is saved.
        keep_timeline = not self._pending_project and not self.state.source and (
            getattr(self, "_template_before_video", False) or self.has_content())
        if keep_timeline:
            self._template_before_video = True  # on_duration appends the video to the existing timeline
        if not self._pending_project and not keep_timeline:
            self.project_path = ''
        self.caption_segments = []
        self.caption_source = ''
        self.apply_captions_button.setEnabled(False)
        self.state = EditState(source=str(file), aspect=self.aspect.currentData(),
                               brightness=self.brightness.value(), contrast=self.contrast.value(),
                               saturation=self.saturation.value(), speed=self.speed_value(),
                               export_profile=self.export_profile.currentData())
        if not self._pending_project and not keep_timeline:
            self.multitrack = Timeline.from_legacy({}, self._source_rate)
            self.multitrack_view.set_model(self.multitrack)
        self.project_title.setText(file.stem)
        self.project_subtitle.setText(f"{file.suffix.upper().lstrip('.')} · {file.stat().st_size / 1024 / 1024:.1f} MB")
        if not keep_timeline:
            self.media_bin.clear()
        self.media_bin.add(str(file))
        self.refresh_media_bin()
        opening_project = self._pending_project is not None
        self.on_duration(round(duration * 1000))
        if not keep_timeline:
            # Undo steps belong to the previous video/project; restoring one here would mix sources.
            self.clear_history()
            self.mark_saved()
        if not opening_project:
            self.set_status(self.ui_text("Video hazır. Sağdaki kutuya isteğinizi yazıp kurgulatabilirsiniz."))
        return True

    def on_duration(self, milliseconds: int) -> None:
        if milliseconds <= 0:
            return
        duration = milliseconds / 1000.0
        self.state.duration = duration
        self.state.start = 0.0
        self.state.end = duration
        self.update_range_label()
        if self._pending_project:
            pending = self._pending_project
            self._pending_project = None
            self.apply_project_state(pending)
        elif getattr(self, '_template_before_video', False):
            self._template_before_video = False
            if not any(t.clips for t in self.multitrack.tracks):  # nothing placed yet: frames can still change meaning
                self.multitrack.fps_num, self.multitrack.fps_den = self._source_rate
            # The first video track, or a new one if the template's video tracks were removed meanwhile.
            with self.history_step():  # earlier steps stay valid: they edit this same timeline
                timeline_service.append_video(self.multitrack, self.state.source, duration)
            self.multitrack_view.set_model(self.multitrack)
            self.refresh_timeline_view()
            self.seek_timeline(0)
        elif not any(t.clips for t in self.multitrack.tracks):
            self.multitrack = Timeline.from_legacy(asdict(self.state), self._source_rate)
            self.multitrack_view.set_model(self.multitrack)
            self.seek_timeline(0)

    def toggle_play(self) -> None:
        if not self.state.source and not duration_frames(self.multitrack):
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
            if self.proxy_usable():
                if self.timeline_frame >= duration_frames(self.multitrack) - 1:
                    self.seek_timeline(0)
                self.play_button.setText('❚❚')
                if self.proxy.is_ready(self.proxy_signature()):
                    self.proxy.play(self.timeline_frame, self.state.speed, self.master_volume)
                else:
                    self._play_when_ready = True
                    self.set_status(self.ui_text('Akıcı önizleme hazırlanıyor…'))
                    self.progress.show()
                    self.prepare_proxy()
                return
            self.playback_clock.start(self.timeline_frame, self.state.speed)
            self.play_timer.start(15)
            self.sync_timeline_audio(force=True)
            self.play_button.setText('❚❚')

    def proxy_signature(self):
        """Signature of the current edit for the proxy, or None when no canvas size can be worked out."""
        adjustments = {k: v for k, v in self.render_adjustments().items() if k != 'speed'}
        try:
            canvas = self.canvas_size()
        except (ValueError, RuntimeError, OSError):  # e.g. "Kaynak oranı" with no usable video clip
            return None
        return timeline_signature(self.multitrack, canvas, adjustments)

    def proxy_usable(self, signature=...):
        """Smooth playback can be tried for this edit: the backend works and this exact edit has not failed."""
        if not self.proxy.available:
            return False
        if signature is ...:
            signature = self.proxy_signature()
        return signature is not None and signature != self._proxy_failed_signature

    def prepare_proxy(self):
        """Render the smooth-playback copy in the background whenever the edit has changed."""
        if not duration_frames(self.multitrack):
            return
        signature = self.proxy_signature()
        if not self.proxy_usable(signature):
            return
        self._proxy_requested = signature
        try:
            adjustments = {k: v for k, v in self.render_adjustments().items() if k != 'speed'}
            self.proxy.prepare(self.multitrack, self.canvas_size(), adjustments, signature)
        except Exception as exc:
            self.on_proxy_failed(str(exc))

    def on_proxy_ready(self):
        if self.proxy.is_ready(self.proxy_signature()):
            if self._play_when_ready:
                self._play_when_ready = False
                self.hide_progress_if_idle()
                self.set_status(self.ui_text('Oynatılıyor.'))
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
        self.hide_progress_if_idle()
        self.play_button.setText('▶')
        if was_active:
            self.set_status(self.ui_text('Duraklatıldı.'))
        if was_active and refresh:
            self.seek_timeline(self.timeline_frame)  # exact full-quality still for the paused frame

    def hide_progress_if_idle(self):
        """The progress bar is shared with export and AI work: playback only hides it when nothing runs."""
        if not self._workers:
            self.progress.hide()

    def on_proxy_ended(self):
        self.stop_proxy_playback()

    def on_proxy_failed(self, message):
        """Fall back to frame-by-frame preview for this edit rather than leaving playback broken.

        Only the failed signature is remembered: the next change to the edit tries the proxy again.
        """
        failed = self._proxy_requested or self.proxy.signature or self.proxy_signature()
        self._proxy_failed_signature = failed
        log.warning("Akıcı önizleme başarısız (%s): %s", failed, message)
        self.stop_proxy_playback(refresh=False)
        self.set_status(f'Akıcı önizleme kullanılamadı, kare kare önizlemeye geçildi: {message[:120]}')

    def update_range_label(self) -> None:
        selected = max(0, self.state.end - self.state.start)
        self.selection_label.setText(f"Seçim: {format_time(selected)}")

    def api_credentials(self) -> tuple[str, str] | None:
        key = self.api_key.text().strip()
        model = self.model.currentText().strip()
        if not key or not model:
            QMessageBox.information(self, APP_NAME, self.ui_text("API anahtarı ve model belirtin."))
            return None
        self._provider_keys[self.provider.currentText()] = key
        if self.remember_key.isChecked():
            self.save_key(key)
        return key, model

    def change_provider(self, provider):
        self._provider_keys[self._active_provider] = self.api_key.text().strip()
        self._active_provider = provider
        self.model.clear(); self.model.addItems(ai_providers.PROVIDERS[provider])
        self.api_key.setPlaceholderText(ai_providers.CLOUDFLARE_KEY_HINT if provider == 'Cloudflare' else "sk-…")
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
            self.set_status(self.ui_text('API anahtarı sistem kasasına kaydedildi.'))
        except Exception as exc:
            self.set_status(f'Anahtar güvenli kasaya kaydedilemedi: {exc}')

    def on_remember_key_clicked(self, checked: bool) -> None:
        """Unticking "Windows'ta güvenli sakla" removes the stored key of this provider from the vault."""
        if checked:
            return  # saved on the next use or with "Anahtarı güvenli kaydet"
        provider = self.provider.currentText()
        delete_key = getattr(ai_providers, 'delete_key', None)
        if not callable(delete_key):
            self._saved_providers.discard(provider)
            self.set_status(self.ui_text('Anahtar artık kaydedilmeyecek; kayıtlı anahtar bu sürümde silinemiyor.'))
            return
        try:
            delete_key(APP_NAME, provider)
        except Exception as exc:
            log.warning("Anahtar silinemedi (%s): %s", provider, exc)
            self.set_status(self.ui_text('Kayıtlı anahtar silinemedi: {error}', error=exc))
            return
        self._saved_providers.discard(provider)
        self.set_status(self.ui_text('{provider} anahtarı sistem kasasından silindi.', provider=provider))

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
        """Şablonlar: ready-made structure (tracks, aspect ratio, colour style, tempo)."""
        code = self.ui_language()
        aspect = i18n.translate(str(self.aspect.currentData() or ""), code).split(" · ")[0]
        dialog = TemplateDialog(self, language=code, current_aspect=aspect, timeline=self.multitrack)
        result = dialog.exec()
        if result == TemplateDialog.SAVED:
            self.show_saved_templates()
        elif result and dialog.selection()[0] is not None:
            self.apply_template_choice(*dialog.selection())

    def show_saved_templates(self):
        """Şablonlarım: templates the user saved from their own projects."""
        folder = app_data_dir()
        dialog = SavedTemplatesDialog(self, saved=user_templates.load(folder), language=self.ui_language(),
                                      save=lambda name: user_templates.add(folder, self.capture_template(name)),
                                      delete=lambda name: user_templates.remove(folder, name))
        if dialog.exec() and dialog.selection() is not None:
            self.apply_saved_template(dialog.selection())

    def capture_template(self, name):
        """The open project's structure and settings as a template of the user's own."""
        return user_templates.capture(
            name, self.multitrack, aspect=self.aspect.currentData(),
            color=(self.brightness.value(), self.contrast.value(), self.saturation.value()),
            speed=self.speed_value(), audio=self.render_adjustments().get('audio', ()))

    def apply_saved_template(self, item):
        with self.history_step():
            user_templates.apply(self.multitrack, item)
            self._template_before_video = not bool(self.state.source)
            if item['aspect']:
                self.select_aspect(item['aspect'])
            self.apply_preset(*item['color'])
            self.select_speed(item['speed'])
        for box, name in self.audio_boxes():
            box.setChecked(name[len('audio_'):] in item['audio'])
        self.multitrack_view.set_model(self.multitrack)
        self.refresh_timeline_view()
        self.multitrack_view.update()
        if duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('{name} uygulandı; medyayı izlere ekleyin.', name=item['name']))

    def show_inspiration(self):
        """İlham: creative ideas. An idea becomes the edit request; its matching template is optional."""
        dialog = InspirationDialog(self, language=self.ui_language())
        if not dialog.exec():
            return
        idea, action = dialog.selection()
        if idea is None:
            return
        current = self.ai_prompt.toPlainText().strip()
        if current and current != idea.prompt.strip():
            # The edit request is the user's own text and the box has no undo across setPlainText.
            answer = QMessageBox.question(self, APP_NAME, self.ui_text(IDEA_REPLACES_PROMPT_QUESTION),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.set_status(self.ui_text('Kurgu isteğiniz korundu; fikir uygulanmadı.'))
                return
        self.ai_prompt.setPlainText(idea.prompt)
        template = template_for(idea) if action == 'prompt+template' else None
        if template is not None:
            self.apply_template_choice(template, template.style, template.tempo)
            self.set_status(f'“{idea.title}” fikri kurgu isteğine yazıldı ve {template.name} şablonu uygulandı.')
        else:
            self.set_status(f'“{idea.title}” fikri kurgu isteğine yazıldı; AI sekmesinden uygulayabilirsiniz.')

    # Hikâye Stüdyosu: Gemini text → image → video; results are added to the project as media.
    def gemini_key(self) -> str:
        if self.provider.currentText() == 'Gemini' and self.api_key.text().strip():
            return self.api_key.text().strip()
        key = self._provider_keys.get('Gemini', '')
        if not key:
            try:
                key = ai_providers.load_key(APP_NAME, 'Gemini')
            except Exception:  # keyring backend missing or locked
                key = ''
        return key

    def story_output_dir(self) -> str:
        """Generated media lives beside the project file, or in the app-data folder for an untitled project."""
        if self.project_path:
            project = Path(self.project_path)
            folder = project.with_name(project.name.removesuffix('.akis.json').removesuffix('.json') + '_ai')
        else:
            folder = app_data_dir() / 'generated'
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def add_generated_media(self, path: str) -> bool:
        """Put a generated file on the timeline. A still image becomes a short clip, since tracks hold video."""
        file = Path(path)
        if not file.is_file():
            return False
        if file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            clip = file.with_name(file.stem + '_klip.mp4')
            result = MediaService(ffmpeg_path()).run(
                ['-y', '-loop', '1', '-t', str(STILL_CLIP_SECONDS), '-i', str(file), '-r', '30',
                 '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p', '-c:v', 'libx264', '-an', str(clip)], text=True)
            if result.returncode != 0 or not clip.is_file():
                QMessageBox.warning(self, APP_NAME, 'Görsel klibe dönüştürülemedi.')
                return False
            file = clip
        before = len(self.media_bin.paths)
        self.add_video(str(file))
        return bool(self.state.source) and (len(self.media_bin.paths) > before or str(file) in self.media_bin.paths)

    def show_story_studio(self):
        if self.story_dialog is None:
            self.story_dialog = StoryDialog(self, api_key=self.gemini_key, output_dir=self.story_output_dir,
                                            add_media=self.add_generated_media,
                                            default_aspect=str(self.aspect.currentData() or '16:9'))
        self.story_dialog.show()
        self.story_dialog.raise_()
        self.story_dialog.activateWindow()

    def apply_template_choice(self, template, style, tempo):
        with self.history_step():
            template_service.apply_template(self.multitrack, template)
            self._template_before_video = not bool(self.state.source)
            self.select_choice(self.aspect, i18n.choice_key(i18n.ASPECTS, template.ratio))
            self.apply_preset(*template_service.STYLES[style])
            self.select_speed(template_service.TEMPOS[tempo])
        self.multitrack_view.set_model(self.multitrack)
        self.refresh_timeline_view()
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
        self.worker = AIWorker(key, model, self.state.source, self.state.duration, plan_prompt(self.ai_prompt.toPlainText().strip(), self.ai_platform.currentData(), self.ai_tempo.currentData(), self.ai_style.currentData(), self.ai_focus.currentData()), ffmpeg_path(), self.provider.currentText())
        self.begin_work("AI analizi başlatılıyor…")
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_ai_plan)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_worker_cancelled)
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

    def remove_silences(self) -> None:
        """Cut the pauses out of the main cut: measured locally, previewed in a dialog, one undo step."""
        if not self.can_start_work() or not self.ensure_video():
            return
        try:
            sources = [{'path': path, 'duration': seconds} for path, seconds in self.edit_sources()]
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f'Video okunamadı: {exc}')
            return
        segments = edit_plan.current_segments(self.multitrack, sources)
        if not segments:
            QMessageBox.information(self, APP_NAME, 'Zaman çizelgesinde kesilecek video yok.')
            return
        dialog = SilenceDialog(self, executable=ffmpeg_path(), sources=sources, segments=segments)
        if not dialog.exec() or not dialog.cuts:  # exec() is 0 when the dialog is dismissed
            return
        try:
            timeline = edit_plan.apply_plan(self.multitrack, sources, {'segments': dialog.segments})
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f'Sessizlikler kesilemedi: {exc}')
            return
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(f'{len(dialog.cuts)} sessiz yer kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).')

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
        self._prompt_revision = self.timeline_revision()
        self.begin_work("Prompt kurgusu başlatılıyor…")
        # The model sets colour/speed/aspect as absolute values, so it is told what they are now.
        settings = {'color': (self.brightness.value(), self.contrast.value(), self.saturation.value()),
                    'speed': self.speed.currentText(), 'aspect': self.aspect.currentData()}
        self.worker = PromptEditWorker(key, model, self.provider.currentText(), request, self.multitrack, sources,
                                       ffmpeg_path(), transcripts,
                                       self.local_model.currentText() if self.use_speech.isChecked() else None,
                                       settings=settings)
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_prompt_edit)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_worker_cancelled)
        self.start_worker()

    def edit_snapshot(self):
        """What one edit step can change: the timeline (a private copy) and the settings an AI plan or a
        template sets. Stored snapshots are never modified; restoring one installs another copy."""
        return {'timeline': copy.deepcopy(self.multitrack), 'aspect': self.aspect.currentData(),
                'speed': self.speed_value(),
                'color': (self.brightness.value(), self.contrast.value(), self.saturation.value()),
                'publish': (self.publish_title.text(), self.publish_caption.toPlainText(), self.publish_tags.toPlainText())}

    @staticmethod
    def snapshot_changes(before, after) -> list[str]:
        """Keys of an edit snapshot whose values differ between two snapshots."""
        def value(snapshot, key):
            return snapshot[key].to_dict() if key == 'timeline' else snapshot[key]
        return [key for key in before if value(before, key) != value(after, key)]

    def record_step(self, before) -> bool:
        """Add one undo step from `before` to now; nothing is added when nothing changed."""
        after = self.edit_snapshot()
        if not self.snapshot_changes(before, after):
            return False
        self._undo_stack.append({'before': before, 'after': after})
        del self._undo_stack[:-UNDO_LIMIT]
        self._redo_stack.clear()
        self.update_history_controls()
        return True

    @contextlib.contextmanager
    def history_step(self):
        """`with self.history_step(): <mutate>` makes the mutation one undo step (also when it raises
        after changing something, so a partly applied edit can still be undone)."""
        before = self.edit_snapshot()
        try:
            yield
        finally:
            self.record_step(before)

    def clear_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._drag_before = None
        self.update_history_controls()

    def update_history_controls(self) -> None:
        can_undo, can_redo = bool(self._undo_stack), bool(self._redo_stack)
        for control in (getattr(self, 'undo_edit_button', None), getattr(self, 'undo_button', None),
                        getattr(self, 'undo_action', None)):
            if control is not None:
                control.setEnabled(can_undo)
        for control in (getattr(self, 'redo_button', None), getattr(self, 'redo_action', None)):
            if control is not None:
                control.setEnabled(can_redo)

    def apply_edit_snapshot(self, snapshot, keys) -> None:
        """Put back the given keys of a snapshot. Only the keys a step changed are written, so undoing a
        timeline edit never resets a colour or text the user changed after it."""
        if 'aspect' in keys:
            self.select_choice(self.aspect, snapshot['aspect'])
        if 'speed' in keys:
            self.select_speed(snapshot['speed'])
        if 'color' in keys:
            self.apply_preset(*snapshot['color'])
        if 'publish' in keys:
            title, caption, tags = snapshot['publish']
            self.publish_title.setText(title)
            self.publish_caption.setPlainText(caption)
            self.publish_tags.setPlainText(tags)
        if 'timeline' in keys:
            self.show_timeline(copy.deepcopy(snapshot['timeline']), frame=self.timeline_frame)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._drag_before = None
        step = self._undo_stack.pop()
        self._redo_stack.append(step)
        self.apply_edit_snapshot(step['before'], self.snapshot_changes(step['before'], step['after']))
        self.update_history_controls()
        self.set_status(self.ui_text('Son adım geri alındı.'))
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._drag_before = None
        step = self._redo_stack.pop()
        self._undo_stack.append(step)
        self.apply_edit_snapshot(step['after'], self.snapshot_changes(step['before'], step['after']))
        self.update_history_controls()
        self.set_status(self.ui_text('Adım yinelendi.'))
        return True

    def on_timeline_drag_started(self):
        self._drag_before = self.edit_snapshot()

    def on_timeline_dragged(self):
        """The track view finished a move/trim that changed a clip: one step for the whole drag."""
        before, self._drag_before = self._drag_before, None
        if before is not None:
            self.record_step(before)
        self.seek_timeline(self.timeline_frame)

    def show_timeline(self, timeline, frame=0):
        self.stop_proxy_playback(refresh=False)
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        self.multitrack = timeline
        self.multitrack_view.set_model(timeline)
        self.refresh_timeline_view()
        self.seek_timeline(frame)

    def timeline_revision(self) -> str:
        """Cheap fingerprint of the timeline's contents, to notice edits made while a worker was running."""
        payload = json.dumps(self.multitrack.to_dict(), sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha1(payload.encode()).hexdigest()

    def on_prompt_edit(self, plan, sources):
        if self._shutting_down:  # a result that arrives while the window closes is dropped
            return
        started, self._prompt_revision = self._prompt_revision, None
        if started is not None and started != self.timeline_revision():
            # The plan was computed from the timeline as it was when the request started.
            answer = QMessageBox.question(self, APP_NAME, STALE_PLAN_QUESTION,
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.finish_work('AI planı uygulanmadı; zaman çizelgesindeki değişiklikleriniz korundu.')
                return
        try:
            aspect = self.aspect.currentData()
            if 'aspect' in plan:  # a bare ratio such as '16:9'
                aspect = i18n.choice_key(i18n.ASPECTS, plan['aspect'])
                if aspect is None:
                    raise ValueError(f'desteklenmeyen oran: {plan["aspect"]}')
            canvas = timeline_service.canvas_size(aspect, self.multitrack, MediaService(ffmpeg_path()))
            timeline = edit_plan.apply_plan(self.multitrack, sources, plan, canvas)
        except Exception as exc:
            self.on_worker_error(f'Kurgu planı uygulanamadı: {exc}')
            return
        with self.history_step():  # the whole AI edit, settings included, is one undo step
            if 'aspect' in plan:
                self.select_choice(self.aspect, aspect)
            if 'speed' in plan:
                self.select_speed(plan['speed'])
            if 'color' in plan:
                # A plan carries only the colour keys the model gave; the others keep their current value.
                color = plan['color']
                self.apply_preset(color.get('brightness', self.brightness.value()),
                                  color.get('contrast', self.contrast.value()),
                                  color.get('saturation', self.saturation.value()))
            if 'title' in plan:
                self.publish_title.setText(plan['title'])
            if 'caption' in plan:
                self.publish_caption.setPlainText(plan['caption'])
            if 'hashtags' in plan:
                self.publish_tags.setPlainText(' '.join(t if t.startswith('#') else '#' + t for t in plan['hashtags']))
            self.show_timeline(timeline)
        self.ai_result.setPlainText(edit_plan.describe(plan, timeline))
        self.finish_work('AI kurgusu uygulandı. Beğenmezseniz geri alabilir veya yeni bir istek yazabilirsiniz.')

    def on_ai_plan(self, plans):
        if self._shutting_down:
            return
        self.ai_suggestions = plans
        self.ai_choice.clear()
        self.ai_choice.addItems([str(p.get('title') or f'Öneri / Suggestion {i+1}') for i, p in enumerate(plans)])
        self.show_ai_suggestion(self.ai_choice.currentIndex())
        self.finish_work('Öneriler hazır; birini seçip işaret olarak uygulayabilirsiniz.')

    def show_ai_suggestion(self, index):
        if 0 <= index < len(self.ai_suggestions):
            plan = self.ai_suggestions[index]
            self.ai_result.setPlainText(format_suggestion(plan))

    def apply_ai_suggestion(self):
        index = self.ai_choice.currentIndex()
        if 0 <= index < len(self.ai_suggestions):
            plan = self.ai_suggestions[index]
            with self.history_step():
                add_plan_markers(self.multitrack, plan)
                self.publish_title.setText(str(plan.get('title', '')))
                self.publish_caption.setPlainText(str(plan.get('caption', '')))
                if plan.get('hashtags'):
                    self.publish_tags.setPlainText(' '.join('#' + str(tag).lstrip('#') for tag in plan['hashtags']))
            self.set_status('Öneri işaretleri projeye eklendi. / Plan markers added.')
            self.multitrack_view.update()
        else:
            self.set_status('Önce “Öneri al” ile öneri isteyin.')

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
        if hasattr(self.worker, 'cancelled'):  # local Whisper runs in one call and cannot be stopped
            self.worker.cancelled.connect(self.on_worker_cancelled)
        self.start_worker()

    def on_local_transcript(self, segments):
        if self._shutting_down:
            return
        self.caption_segments = segments
        self.caption_source = self.caption_request_source
        self.apply_captions_button.setEnabled(bool(segments))
        self.on_transcript(' '.join(segment['text'] for segment in segments))

    def apply_local_captions(self):
        with self.history_step():
            # Applying again replaces the previous caption track instead of drawing the captions twice.
            self.multitrack.tracks = [track for track in self.multitrack.tracks
                                      if not (track.kind == 'text' and track.name == edit_plan.CAPTION_TRACK)]
            self.multitrack_view.selected = self.multitrack_view.selected_track = None
            count = caption_track(self.multitrack, self.caption_source, self.caption_segments)
        self.refresh_timeline_view()
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
        chosen, _ = QFileDialog.getSaveFileName(self, 'Seslendirmeyi kaydet', '', 'WAV (*.wav)')
        if not chosen:
            return
        path = chosen if chosen.lower().endswith('.wav') else chosen + '.wav'
        if not self.confirm_overwrite(chosen, path):
            return
        self.begin_work('Windows sesi oluşturuluyor…')
        self.worker = TtsWorker(text, path)
        self.worker.completed.connect(self.on_voiceover)
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()

    def on_voiceover(self, path: str) -> None:
        if not self._shutting_down:
            self.finish_work(f'Ses kaydedildi: {path}')

    def on_transcript(self, text: str) -> None:
        if self._shutting_down:
            return
        self.ai_result.setPlainText("KONUŞMA METNİ\n\n" + text)
        if not self.publish_caption.toPlainText().strip():
            self.publish_caption.setPlainText(text)
        self.finish_work("Türkçe konuşma metni hazır.")

    def export_video(self) -> None:
        if not self.can_start_work():
            return
        if not self.ensure_video():
            return
        try:
            canvas = self.export_canvas_size()
        except (ValueError, RuntimeError, OSError) as exc:  # e.g. "Kaynak oranı" with no usable video clip
            QMessageBox.warning(self, APP_NAME, f'Dışa aktarma boyutu belirlenemedi: {exc}')
            self.set_status('Dışa aktarma başlatılamadı.')
            return
        findings = preflight.check(self.multitrack)
        if findings and QMessageBox.question(self, APP_NAME, preflight.question(findings),
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.set_status('Dışa aktarma başlatılmadı.')
            return
        default = safe_filename(self.project_title.text()) + "_akis.mp4"
        chosen, _ = QFileDialog.getSaveFileName(self, "Videoyu dışa aktar", str(Path.home() / "Videos" / default), "MP4 Video (*.mp4)")
        if not chosen:
            return
        path = normalize_export_path(chosen)
        if not self.confirm_overwrite(chosen, path):
            return
        if timeline_service.output_overwrites_source(self.multitrack, path, (self.state.source,)):
            QMessageBox.warning(self, APP_NAME, 'Çıktı yolu kaynak medya ile aynı olamaz; başka bir dosya adı seçin.')
            return
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        seconds = duration_frames(self.multitrack) / fps / self.state.speed
        problem = export_progress.space_problem(path, export_progress.estimated_bytes(canvas, fps, seconds))
        if problem and QMessageBox.question(self, APP_NAME, problem + '\n\nYine de devam edilsin mi?',
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.set_status('Dışa aktarma başlatılmadı.')
            return
        self.state.aspect = self.aspect.currentData()
        self.state.export_profile = self.export_profile.currentData()
        self.worker = TimelineRenderWorker(self.multitrack, path, canvas, ffmpeg_path(), adjustments=self.render_adjustments())
        self.begin_work(self.ui_text("Dışa aktarma hazırlanıyor…"))
        self._export_estimator = export_progress.Estimator()
        self.worker.progress.connect(self.on_export_progress)
        self.worker.finished.connect(lambda: self.progress.setRange(0, 0))  # back to the "busy" look
        self.worker.completed.connect(self.on_exported)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_export_cancelled)
        self.start_worker()

    def on_export_progress(self, percent: int) -> None:
        if self._shutting_down:
            return
        shown, remaining = self._export_estimator.update(percent / 100)
        self.progress.setRange(0, 100)
        self.progress.setValue(shown)
        self.set_status(export_progress.text(shown, remaining))

    def confirm_overwrite(self, chosen: str, path: str) -> bool:
        """The file dialog only confirmed overwriting `chosen`; ask again when the final name differs and exists."""
        if os.path.normcase(os.path.abspath(chosen)) == os.path.normcase(os.path.abspath(path)) or not Path(path).exists():
            return True
        answer = QMessageBox.question(self, APP_NAME, f'“{Path(path).name}” zaten var. Üzerine yazılsın mı?',
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def on_exported(self, path: str) -> None:
        if self._shutting_down:
            return
        self.finish_work(self.ui_text("Dışa aktarma tamamlandı."))
        QMessageBox.information(self, APP_NAME, self.ui_text("Video başarıyla oluşturuldu:\n{path}", path=path))

    def apply_preset(self, brightness: int, contrast: int, saturation: int) -> None:
        self.brightness.setValue(brightness)
        self.contrast.setValue(contrast)
        self.saturation.setValue(saturation)
        self.set_status(self.ui_text("Renk görünümü güncellendi; dışa aktarmada uygulanacak."))

    def copy_publish_text(self) -> None:
        text = "\n\n".join(filter(None, [
            self.publish_title.text().strip(),
            self.publish_caption.toPlainText().strip(),
            self.publish_tags.toPlainText().strip(),
        ]))
        QApplication.clipboard().setText(text)
        self.set_status(self.ui_text("Yayın metni panoya kopyalandı."))

    def ensure_video(self) -> bool:
        if not self.state.source or not self.state.duration:
            QMessageBox.information(self, APP_NAME, self.ui_text("Önce bir video ekleyin ve yüklenmesini bekleyin."))
            return False
        return True

    def can_start_work(self) -> bool:
        if self._workers:
            self.set_status(self.ui_text('Bir işlem devam ediyor; lütfen bitmesini bekleyin.'))
            return False
        return True

    def start_worker(self) -> None:
        worker = self.worker
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self.worker_finished(w))
        self.cancel_button.setEnabled(callable(getattr(worker, 'cancel', None)))
        self.cancel_button.show()
        worker.start()

    def worker_finished(self, worker) -> None:
        self._workers.discard(worker)
        if self.worker is worker:
            self.worker = None
        if not self._workers:
            self.cancel_button.setEnabled(False)
            self.cancel_button.hide()
        worker.deleteLater()

    def cancel_work(self) -> None:
        """İptal: stop the running worker; its `cancelled` signal then ends the busy state."""
        worker = self.worker
        if worker is None or worker not in self._workers or not callable(getattr(worker, 'cancel', None)):
            return
        worker.cancel()
        self.cancel_button.setEnabled(False)
        self.set_status(self.ui_text('İptal ediliyor…'))

    def begin_work(self, text: str) -> None:
        self.progress.show()
        self.set_status(text)

    def finish_work(self, text: str) -> None:
        self.progress.hide()
        self.set_status(text)

    def on_worker_error(self, message: str) -> None:
        if self._shutting_down:
            return
        self.progress.hide()
        self.set_status(self.ui_text("İşlem tamamlanamadı."))
        QMessageBox.critical(self, APP_NAME, message)

    def on_worker_cancelled(self) -> None:
        self._prompt_revision = None
        if not self._shutting_down:
            self.finish_work(self.ui_text('İşlem iptal edildi.'))

    def on_export_cancelled(self) -> None:
        if not self._shutting_down:
            self.finish_work(self.ui_text('Dışa aktarma iptal edildi.'))

    # Self-update: check the version, ask, download with a progress dialog into one fixed folder (the install
    # folder is not touched), check free space, ask again, verify, hand over to the installer helper.
    def update_folder(self) -> Path:
        return update_service.update_dir(app_data_dir())

    @staticmethod
    def install_folder() -> Path:
        return Path(sys.executable).resolve().parent

    def ui_text(self, template: str, **values) -> str:
        """A whole-string translation of `template` into the current UI language, then filled in."""
        return i18n.translate(template, self.ui_language()).format(**values)

    def report_update_result(self) -> None:
        """At startup: say that an update worked, or (once) that it failed, and remember the failed version.

        install_update stores the version it hands over as update/pending_version; this launch then runs
        either that version (success) or still the old one (the installer failed and restored it).
        """
        current = update_service.VERSION
        current_tuple = update_service.version_tuple(current)
        pending = str(self.settings.value("update/pending_version", "") or "")
        last = str(self.settings.value("update/last_run_version", "") or "")
        self.settings.setValue("update/last_run_version", current)
        if pending:
            self.settings.remove("update/pending_version")
            target = update_service.version_tuple(pending)
            if target and current_tuple and current_tuple >= target:
                self.update_succeeded(current)
            else:
                log.warning("Güncelleme %s kurulamadı; %s çalışıyor", pending, current)
                self.settings.setValue("update/failed_version", pending)
                self.set_status(self.ui_text(
                    "Akış Kurgu AI {version} güncellemesi kurulamadı; {current} sürümü kullanılmaya devam ediyor.",
                    version=pending, current=current))
        elif last and current_tuple and (update_service.version_tuple(last) or current_tuple) < current_tuple:
            self.update_succeeded(current)  # updated by running the installer by hand

    def update_succeeded(self, current: str) -> None:
        log.info("Güncelleme tamamlandı: %s", current)
        self.settings.remove("update/failed_version")
        update_service.cleanup_update_dir(self.update_folder())
        self.set_status(self.ui_text("Akış Kurgu AI {version} sürümüne güncellendi.", version=current))

    def check_for_updates(self, manual: bool = False) -> None:
        """Ask GitHub for a newer release. `manual` (the version tag was clicked) reports every outcome
        and asks again about a version the user postponed; the check at startup stays silent."""
        if self._shutting_down:
            return
        if manual and not (getattr(sys, '_MEIPASS', None) and sys.platform == 'win32'):
            # Run from source: there is no installed copy to update.
            self.set_status(self.ui_text("Sürüm {version} · kaynak koddan çalışıyor; güncelleme denetimi kurulu "
                                         "sürümde yapılır.", version=update_service.VERSION))
            return
        if any(t is not None and t.isRunning() for t in (self.update_check, self.update_download)):
            if manual:
                self.set_status(self.ui_text("Güncelleme denetimi veya indirmesi zaten sürüyor."))
            return
        update_service.cleanup_legacy_temp()
        self.update_check = UpdateCheckWorker()
        self.update_check.available.connect(self.offer_update)
        self.update_check.up_to_date.connect(lambda: update_service.cleanup_update_dir(self.update_folder()))
        if manual:
            self._declined_updates.clear()
            self.settings.remove("update/postponed_until")
            # Bound methods, so the results are delivered on the UI thread.
            self.update_check.up_to_date.connect(self.report_up_to_date)
            self.update_check.failed.connect(self.report_update_check_failed)
            self.set_status(self.ui_text("Güncellemeler denetleniyor…"))
        self.update_check.start()

    def report_up_to_date(self) -> None:
        if not self._shutting_down:
            self.set_status(self.ui_text("Akış Kurgu AI güncel: {version} en son sürüm.",
                                         version=update_service.VERSION))

    def report_update_check_failed(self, _message: str = "") -> None:
        if not self._shutting_down:
            self.set_status(self.ui_text("Güncellemeler denetlenemedi. İnternet bağlantınızı kontrol edip yeniden "
                                         "deneyin."))

    def update_postponed(self, version: str) -> bool:
        """The user said "later" to this version in this session, or within UPDATE_REMIND_AFTER."""
        if version in self._declined_updates:
            return True
        try:
            until = float(self.settings.value("update/postponed_until", 0) or 0)
        except (TypeError, ValueError):
            until = 0.0
        return self.settings.value("update/postponed_version", "") == version and time.time() < until

    def postpone_update(self, version: str) -> None:
        self._declined_updates.add(version)
        self.settings.setValue("update/postponed_version", version)
        self.settings.setValue("update/postponed_until", time.time() + UPDATE_REMIND_AFTER)

    def offer_update(self, update) -> None:
        if self._shutting_down:
            return
        version = update['version']
        try:
            target = update_service.installer_path(self.update_folder(), update)
        except ValueError:
            log.warning("Geçersiz güncelleme sürümü: %r", version)
            return
        # Installers of any other version (older downloads, partial files) are stale now.
        update_service.cleanup_update_dir(target.parent, keep=target)
        if self.update_postponed(version):
            log.info("Güncelleme %s ertelendiği için sorulmadı", version)
            return
        if str(self.settings.value("update/failed_version", "") or "") == version:
            # Installing this version failed before: say so and let the user decide, never re-run silently.
            question = self.ui_text(
                "Akış Kurgu AI {version} güncellemesi önceki denemede kurulamadı; {current} sürümü değişmeden "
                "çalışıyor.\n\nAyrıntılar: {log}\n\nYeniden denensin mi?",
                version=version, current=update_service.VERSION, log=target.parent / update_service.INSTALL_LOG)
            if target.is_file():
                question += "\n\n" + self.ui_text("Kurulum dosyasını elle de çalıştırabilirsiniz: {path}", path=target)
        else:
            size = update.get('size')
            question = self.ui_text(
                "Akış Kurgu AI {version} sürümü yayımlandı. İndirme boyutu: {size:.1f} MB.\n\nŞimdi indirilsin "
                "mi? İndirme arka planda yapılır; kurulumdan önce yeniden sorulur.",
                version=version, size=size / 1024 / 1024) if size else self.ui_text(
                "Akış Kurgu AI {version} sürümü yayımlandı.\n\nŞimdi indirilsin mi? İndirme arka planda "
                "yapılır; kurulumdan önce yeniden sorulur.", version=version)
        answer = QMessageBox.question(self, APP_NAME, question,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            self.postpone_update(version)
            self.set_status(self.ui_text("{version} güncellemesi ertelendi.", version=version))
            return
        if not target.is_file():
            shortfall = update_service.space_shortfall(target.parent, update_service.download_space_needed(update))
            if shortfall:
                self._declined_updates.add(version)  # asked again at the next launch
                text = self.ui_text(
                    "Güncellemeyi indirmek için {folder} konumunda en az {needed:.0f} MB boş alan gerekiyor; şu "
                    "anda {free:.0f} MB boş. Yer açtıktan sonra güncelleme yeniden önerilecek.",
                    folder=target.parent, needed=shortfall[0] / 1024 ** 2, free=shortfall[1] / 1024 ** 2)
                self.set_status(text)
                QMessageBox.warning(self, APP_NAME, text)
                return
        self.start_update_download(update, target)

    def start_update_download(self, update, target: Path) -> None:
        if self.update_download is not None and self.update_download.isRunning():
            return
        self._update = update
        self._update_target = Path(target)
        self._update_percent = -1
        if self.update_dialog is None or self.update_dialog.version != update['version']:
            if self.update_dialog is not None:
                self.update_dialog.deleteLater()
            self.update_dialog = UpdateProgressDialog(update['version'], self.ui_language(), self)
            self.update_dialog.cancel_requested.connect(self.cancel_update_download)
            self.update_dialog.retry_requested.connect(self.retry_update_download)
        self.update_dialog.start()
        self.update_dialog.show()
        self.set_status(self.ui_text("{version} güncellemesi indiriliyor…", version=update['version']))
        self.update_download = UpdateDownloadWorker(update, str(target))
        self.update_download.progress.connect(self.on_update_progress)
        self.update_download.completed.connect(self.install_update)
        self.update_download.failed.connect(self.on_update_failed)
        self.update_download.cancelled.connect(self.on_update_cancelled)
        self.update_download.start()

    def cancel_update_download(self) -> None:
        if self.update_download is not None and self.update_download.isRunning():
            self.update_download.requestInterruption()  # the worker deletes its partial file
        else:
            self.on_update_cancelled()

    def retry_update_download(self) -> None:
        if self._shutting_down or self._update is None or self._update_target is None:
            return
        self.start_update_download(self._update, self._update_target)

    def on_update_progress(self, done: int, total: int) -> None:
        if self._shutting_down:
            return
        if self.update_dialog is not None:
            self.update_dialog.set_progress(done, total)
        if total <= 0:
            return
        percent = min(100, done * 100 // total)
        if percent != self._update_percent:
            self._update_percent = percent
            self.set_status(self.ui_text("{version} güncellemesi indiriliyor… %{percent}",
                                         version=self._update['version'], percent=percent))

    def on_update_cancelled(self) -> None:
        log.info("Güncelleme indirmesi iptal edildi")
        if self._shutting_down:
            return
        if self.update_dialog is not None:
            self.update_dialog.hide()
        if self._update is not None:
            self.postpone_update(self._update['version'])
        self.set_status(self.ui_text("Güncelleme indirmesi iptal edildi."))

    def on_update_failed(self, message: str) -> None:
        log.warning("Güncelleme indirilemedi: %s", message)
        if self._shutting_down:
            return
        self.set_status(self.ui_text("Güncelleme indirilemedi: {message}", message=message))
        if self.update_dialog is not None:
            self.update_dialog.show_failed(message)

    def install_update(self, installer: str) -> None:
        update = self._update
        if self._shutting_down or update is None:
            return
        if self.update_dialog is not None:
            self.update_dialog.show_verifying()
            self.update_dialog.hide()
        self.set_status(self.ui_text("Güncelleme hazır."))
        folder = self.install_folder()
        shortfall = update_service.space_shortfall(folder, update_service.required_install_space(folder))
        if shortfall:
            self.postpone_update(update['version'])  # the verified file stays and is reused next time
            QMessageBox.warning(self, APP_NAME, self.ui_text(
                "Güncellemeyi kurmak için {folder} sürücüsünde en az {needed:.1f} GB boş alan gerekiyor; şu anda "
                "{free:.1f} GB boş. Hiçbir şey değiştirilmedi; yer açtıktan sonra güncelleme yeniden önerilecek.",
                folder=folder.anchor or folder, needed=shortfall[0] / 1024 ** 3, free=shortfall[1] / 1024 ** 3))
            return
        answer = QMessageBox.question(self, APP_NAME, self.ui_text(
            "Akış Kurgu AI {version} indirildi ve doğrulandı.\n\nUygulama kapanacak; bir güncelleme penceresi "
            "ilerlemeyi gösterecek ve bitince yeni sürüm açılacak. Bu birkaç dakika sürebilir; o sırada "
            "uygulamayı yeniden açmayın. Bir sorun olursa kullandığınız sürüm olduğu gibi kalır.\n\nÖnce açık "
            "projenizi kaydedin. Şimdi güncellensin mi?", version=update['version']),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self.postpone_update(update['version'])  # the verified file stays and is reused next time
            return
        if self._workers:
            QMessageBox.information(self, APP_NAME, self.ui_text("Güncellemeden önce devam eden işlemin bitmesini bekleyin."))
            return
        # Settle unsaved work before the installer starts waiting for this process to exit.
        if not self.confirm_close():
            return
        # The next launch compares this with the version it runs to tell success from failure.
        self.settings.setValue("update/pending_version", update['version'])
        self.settings.sync()
        try:
            # Verifies the SHA-256 again right before spawning; the helper re-verifies before Start-Process.
            update_service.launch_installer(installer, sys.executable, os.getpid(), sha256=update['sha256'])
        except (OSError, ValueError) as exc:
            self.settings.remove("update/pending_version")
            if str(exc) == update_service.VERIFY_FAILED:
                self.remove_file(Path(installer))
            QMessageBox.critical(self, APP_NAME, self.ui_text("Güncelleme başlatılamadı: {message}", message=exc))
            return
        self._close_confirmed = True
        self.close()

    @staticmethod
    def stop_thread(thread) -> None:
        """Ask a background thread to stop and wait briefly; one still blocked on the network is left to
        finish on its own (kept referenced, waited for once the event loop has ended)."""
        if thread is None or not thread.isRunning():
            return
        thread.requestInterruption()
        if not thread.wait(THREAD_STOP_WAIT_MS):
            log.info("Arka plan işi %s ms içinde durmadı; kapanışta beklenecek", THREAD_STOP_WAIT_MS)
            _background_threads.append(thread)

    def stop_workers(self) -> None:
        """At close: cancel every editing worker (killing its FFmpeg) and wait a bounded time for each.
        One that cannot stop in time (a network call, local Whisper) is kept referenced and waited for
        after the event loop; its results are ignored because _shutting_down is set."""
        for worker in list(self._workers):
            cancel = getattr(worker, 'cancel', None)
            if callable(cancel):
                cancel()
            self.stop_thread(worker)
        self.cancel_button.setEnabled(False)

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
            with self.history_step():
                self.multitrack.tracks.append(Track(kind, f'{kind.title()} {len(self.multitrack.tracks)+1}'))
            self.refresh_timeline_view()
            self.multitrack_view.update()

    def remove_track(self):
        index = self.multitrack_view.selected_track
        if index is None or not 0 <= index < len(self.multitrack.tracks):
            self.set_status(self.ui_text('Silinecek izi seçin.'))
            return
        track = self.multitrack.tracks[index]
        if track.clips and QMessageBox.question(
                self, APP_NAME, f'“{track.name}” izi ve içindeki {len(track.clips)} klip silinsin mi? '
                                'Ctrl+Z ile geri alabilirsiniz.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        with self.history_step():
            self.multitrack.tracks.pop(index)
        self.multitrack_view.selected = None
        self.multitrack_view.selected_track = None
        self.refresh_timeline_view()
        self.seek_timeline(self.timeline_frame)

    def edit_text_clip(self):
        track, clip = self.selected_clip()
        if not clip or track.kind != 'text':
            self.set_status(self.ui_text('Önce bir metin klibi seçin.'))
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
            with self.history_step():
                if choice in self.MARK_COLOURS:
                    clip.style['color'] = self.MARK_COLOURS[choice]
                else:
                    track.clips.remove(clip)
                    self.multitrack_view.selected = None
        else:
            value, ok = QInputDialog.getMultiLineText(self, 'Metni düzenle', 'Başlık / altyazı', clip.text)
            if not ok:
                return
            with self.history_step():
                if value.strip():
                    clip.text = value.strip()
                else:
                    track.clips.remove(clip)
                    self.multitrack_view.selected = None
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)

    def element_at(self, x, y):
        """(track_index, clip) of the text or mark drawn nearest to a point of the picture, or None."""
        try:
            width, height = self.canvas_size()
        except (ValueError, RuntimeError, OSError) as exc:  # no picture to hit-test against
            self.set_status(f'Önizleme boyutu belirlenemedi: {exc}')
            return None
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
            self.set_status(self.ui_text('Önce hedef izi seçin.'))
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
            QMessageBox.warning(self, APP_NAME, self.ui_text('Medya eklenemedi: {error}', error=exc))
            return
        with self.history_step():
            timeline_service.append_media(self.multitrack, index, path, seconds)
        self.media_bin.add(path)
        self.refresh_media_bin()
        self.multitrack_view.refresh_waveforms()
        self.update_timeline_scroll()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('Medya zaman çizelgesine eklendi.'))

    def split_clip(self):
        track, clip = self.selected_clip()
        if not clip:
            self.set_status(self.ui_text('Önce bölünecek klibi seçin.'))
            return
        try:
            with self.history_step():
                timeline_service.split_selected(self.multitrack, self.multitrack_view.selected, self.multitrack_view.playhead)
        except ValueError as exc:  # the model's messages are English and technical
            if str(exc) == 'Split must be inside clip':
                self.set_status(self.ui_text('Klip bölünemedi: oynatma imlecini seçili klibin içine getirin.'))
            else:
                self.set_status(self.ui_text('Klip bölünemedi: {error}', error=exc))
            return
        self.multitrack_view.update()
        self.set_status(self.ui_text('Klip bölündü.'))

    def delete_clip(self):
        """Delete key: remove the selected clip and leave its gap (Ripple sil closes the gap)."""
        track, clip = self.selected_clip()
        if not clip:
            self.set_status(self.ui_text('Önce silinecek klibi seçin.'))
            return
        with self.history_step():
            track.clips.remove(clip)
        self.multitrack_view.selected = None
        self.update_timeline_scroll()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('Klip silindi. Ctrl+Z ile geri alabilirsiniz.'))

    def ripple_delete(self):
        """Delete the selected clip and close the gap on every track and on the markers (one undo step)."""
        track, clip = self.selected_clip()
        if not clip:
            self.set_status(self.ui_text('Önce silinecek klibi seçin.'))
            return
        track_index = self.multitrack_view.selected[0]
        try:
            with self.history_step():
                self.multitrack.ripple_delete(track_index, clip.id)
        except ValueError as exc:  # the timeline rolled itself back
            self.set_status(f'Klip silinemedi: {exc}')
            self.multitrack_view.update()
            return
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
            self.preview.pending = None
            self._preview_cleared = True  # a late frame of the removed clips must not come back
            self.video.set_image(None)  # the placeholder, not the last clip's frame
            return
        self._preview_cleared = False
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
        try:
            canvas = self.canvas_size()
        except (ValueError, RuntimeError, OSError) as exc:  # e.g. "Kaynak oranı" with the first clip missing
            self.set_status(f'Önizleme oluşturulamadı: {exc}')
            return
        self.preview.limit = self.preview_limit()
        self.preview.request(self.multitrack, self.timeline_frame, canvas, self.render_adjustments())

    def preview_limit(self) -> int:
        """Longest side of a still preview in pixels: what the view really shows (screen scaling and zoom
        included), so a paused frame is sharp without rendering more than can be seen."""
        shown = max(self.video.width(), self.video.height()) * self.video.devicePixelRatioF() * self.video.zoom
        return int(max(PreviewController.DEFAULT_LIMIT, min(PreviewController.MAX_LIMIT, math.ceil(shown / 160) * 160)))

    def refresh_still(self) -> None:
        """Render the paused frame again when the view was zoomed or resized past its sharpness."""
        if (duration_frames(self.multitrack) and not self.proxy.playing and not self.play_timer.isActive()
                and self.preview_limit() > self.preview.limit):
            self.seek_timeline(self.timeline_frame)

    def show_timeline_frame(self, path):
        if not self.proxy.playing and not getattr(self, '_preview_cleared', False):
            self.video.set_image(QImage(path))

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

    def change_aspect(self, key):
        self.state.aspect = key
        if hasattr(self, 'multitrack_view') and duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)

    def change_export_profile(self, key):
        self.state.export_profile = key
        if key.startswith(('Reels', 'TikTok', '4K Dikey')):
            self.select_choice(self.aspect, '9:16 · Reels / Shorts')
        elif key.startswith(('YouTube', '4K UHD')):
            self.select_choice(self.aspect, '16:9 · YouTube')

    # timeline_service parses the canonical Turkish texts, which are exactly the combo keys.
    def canvas_size(self):
        return timeline_service.canvas_size(self.aspect.currentData(), self.multitrack, MediaService(ffmpeg_path()))

    def export_canvas_size(self):
        return timeline_service.output_canvas_size(self.aspect.currentData(), self.multitrack,
                                                   MediaService(ffmpeg_path()), self.export_profile.currentData())

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
            self.set_status(self.ui_text('Bir ses veya video klibi seçin.'))
            return
        value, ok = QInputDialog.getInt(self, 'Klip sesi / Clip volume', 'Ses / Volume (%)', round(clip.volume * 100), 0, 100)
        if ok:
            with self.history_step():
                timeline_service.set_clip_volume(self.multitrack, self.multitrack_view.selected, value / 100)
            self.sync_timeline_audio(force=True)
            self.set_status(f'Klip sesi: %{value}')

    def set_clip_fit(self):
        """Fit the selected video clip inside the canvas or let it fill the canvas (cropped), one undo step."""
        track, clip = self.selected_clip()
        if not clip or track.kind not in ('video', 'overlay'):
            self.set_status('Önce bir video klibi seçin.')
            return
        labels = [label for label, _, _ in clip_fit.CHOICES]
        chosen, ok = QInputDialog.getItem(self, 'Kadraj', 'Klip tuvale nasıl yerleşsin?', labels,
                                          clip_fit.choice_index(clip.style), False)
        if not ok:
            return
        _, fit, focus = clip_fit.CHOICES[labels.index(chosen)]
        with self.history_step():
            clip_fit.apply(clip, fit, focus)
        self.seek_timeline(self.timeline_frame)
        self.set_status(f'Kadraj: {chosen}')

    def change_color(self, name, value):
        setattr(self.state, name, value)
        if hasattr(self, 'multitrack_view') and duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)

    def change_speed(self, value):
        self.state.speed = i18n.speed_key(value)
        if hasattr(self, 'proxy'):
            self.proxy.set_speed(self.state.speed)
        if hasattr(self, 'play_timer') and self.play_timer.isActive():
            self.playback_clock.set_speed(self.multitrack, self.state.speed)
            self.sync_timeline_audio(force=True)

    def audio_boxes(self):
        """The sound clean-up checkboxes with the EditState field each one sets."""
        return ((self.loudness, 'audio_level'), (self.noise_reduction, 'audio_denoise'), (self.music_duck, 'audio_duck'))

    def change_audio(self, name, checked):
        setattr(self.state, name, bool(checked))
        if hasattr(self, 'multitrack_view') and duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)  # the playback copy is rebuilt with the new sound

    def render_adjustments(self):
        adjustments = {'brightness': self.state.brightness, 'contrast': self.state.contrast,
                       'saturation': self.state.saturation, 'speed': self.state.speed}
        audio = tuple(name[len('audio_'):] for name in ('audio_denoise', 'audio_duck', 'audio_level')
                      if getattr(self.state, name))
        if audio:  # absent when everything is off, so renders and signatures stay as they were
            adjustments['audio'] = audio
        return adjustments

    def project_document(self) -> dict:
        publish = {'title': self.publish_title.text(),
                   'caption': self.publish_caption.toPlainText(),
                   'hashtags': self.publish_tags.toPlainText()}
        return project_service.make_document(asdict(self.state), self.multitrack, publish,
                                             self.ai_prompt.toPlainText())

    def write_project(self, path: str, snapshot: bool = False) -> None:
        project_service.save_with_snapshot(path, self.project_document(), snapshot)

    def save_project(self) -> None:
        if not self.has_content():
            QMessageBox.information(self, APP_NAME, self.ui_text("Kaydetmek için önce bir video veya medya ekleyin."))
            return
        path = self.project_path
        if not path:
            default = safe_filename(self.project_title.text()) + ".akis.json"
            chosen, _ = QFileDialog.getSaveFileName(
                self, "Projeyi kaydet", str(Path.home() / "Documents" / default), "Akış projesi (*.akis.json)"
            )
            if not chosen:
                return
            path = project_service.normalize_project_path(chosen)
            if not self.confirm_overwrite(chosen, path):
                return
        try:
            self.write_project(path, snapshot=True)
        except (OSError, ValueError) as exc:
            log.exception("Proje kaydedilemedi: %s", path)
            QMessageBox.critical(self, APP_NAME, f'Proje kaydedilemedi: {exc}')
            return
        self.project_path = path
        self.mark_saved()
        self.discard_autosave()  # the project file now holds everything the autosave did
        self.set_status(self.ui_text("Proje ve sürüm anlık görüntüsü kaydedildi."))

    def project_signature(self) -> str:
        document = self.project_document()
        document.pop('saved_at', None)
        return hashlib.sha1(json.dumps(document, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    def mark_saved(self) -> None:
        self._saved_signature = self.project_signature()

    def has_content(self) -> bool:
        """There is work to keep: a main video, or any clip on the timeline (media added with ＋ Medya or a
        template's title before any video, text, ...). Save, autosave and the close prompt key off this."""
        return bool(self.state.source) or any(track.clips for track in self.multitrack.tracks)

    def has_unsaved_changes(self) -> bool:
        return self.has_content() and self.project_signature() != self._saved_signature

    def confirm_close(self) -> bool:
        """Ask before work is lost. A hidden window (tests, scripted runs) has nobody to ask."""
        if self._close_confirmed or not self.isVisible() or not self.has_unsaved_changes():
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(self, APP_NAME, self.ui_text('Projede kaydedilmemiş değişiklikler var. Kaydedilsin mi?'),
                                      buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        if answer == buttons.Save:
            self.save_project()
            return not self.has_unsaved_changes()
        if answer == buttons.Discard:
            self.discard_autosave()  # discarded work must not come back as "recovered" later
            return True
        return False

    def open_project(self) -> None:
        if not self.can_start_work() or not self.confirm_close():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Proje aç", "", "Akış projesi (*.akis.json);;JSON (*.json)"
        )
        if not path:
            return
        self.open_project_file(path)

    def open_project_file(self, path: str) -> bool:
        """Open a project file, offering its newer autosave (left by a crash) instead."""
        autosave = Path(path + ".autosave")
        load_from, recovered = path, False
        try:
            newer = autosave.is_file() and autosave.stat().st_mtime > Path(path).stat().st_mtime
        except OSError:
            newer = False
        if newer:
            answer = self.ask_recovery(autosave)
            if answer == 'open':
                load_from, recovered = str(autosave), True
            elif answer == 'later':
                # Opening the project now would let this window's autosave overwrite or remove the file.
                self.set_status(self.ui_text('Proje açılmadı; kurtarma dosyası saklandı ve bir dahaki açılışta '
                                             'yeniden sorulacak.'))
                return False
            else:
                self.remove_file(autosave)
        elif autosave.is_file():
            self.remove_file(autosave)  # older than the project: the project was saved after it
        opened = self.load_project_document(load_from, path, recovered=recovered)
        if opened and recovered:
            self._autosave_file = str(autosave)  # ours now: removed on save, discard or clean close
        return opened

    def load_project_document(self, load_from: str, project_path: str, recovered: bool = False) -> bool:
        """Load `load_from` as the project at `project_path` (the real project, never the autosave)."""
        # Opening is all-or-nothing: load_video/apply_project_state replace the window's project piece by
        # piece, so a failure half-way must put the previous project back. Otherwise the window would show
        # the new project while project_path still names the old file, and Save/autosave would overwrite it.
        snapshot = self.open_snapshot()
        try:
            document, source_path, missing = project_service.load_project(load_from)
            if source_path:
                self._pending_project = document
                loaded = self.load_video(source_path)
            else:  # saved before any main video was added
                loaded = self.load_sourceless_project(document, project_path)
        except Exception as exc:
            log.exception("Proje açılamadı: %s", load_from)
            self.restore_open_snapshot(snapshot)
            QMessageBox.critical(self, APP_NAME, f'Proje açılamadı: {exc}')
            self.set_status('Proje açılamadı; önceki çalışma olduğu gibi korundu.')
            return False
        if not loaded:  # load_video refused the source and already told the user why
            self.restore_open_snapshot(snapshot)
            return False
        # The previous project was saved or discarded in confirm_close; never delete the file just recovered.
        self.discard_autosave(keep=load_from if recovered else None)
        self.project_path = project_path
        if recovered:
            self._saved_signature = None  # recovered work is not in any saved file yet
            self.set_status(self.ui_text('Kurtarılan çalışma açıldı; kalıcı olması için projeyi kaydedin.'))
        if missing:
            names = '\n'.join(f'• {item}' for item in missing)
            QMessageBox.warning(self, APP_NAME, f'Projede kullanılan şu medya dosyaları bulunamadı:\n{names}\n\n'
                                                'Proje açıldı; bu dosyaları kullanan klipler önizlemede ve dışa aktarmada eksik kalabilir.')
        return True

    def load_sourceless_project(self, document: dict, project_path: str) -> bool:
        """Open a project that has no main video yet (only ＋ Medya clips, text, a template...)."""
        if not self.can_start_work():
            return False
        self.stop_proxy_playback(refresh=False)
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        self.caption_segments = []
        self.caption_source = ''
        self.apply_captions_button.setEnabled(False)
        self._pending_project = None
        self._template_before_video = False
        self.state = EditState()
        self.media_bin.clear()
        name = Path(project_path).name.removesuffix('.akis.json').removesuffix('.json') if project_path else ''
        self.project_title.setText(name or self.ui_text('Yeni proje'))
        self.project_subtitle.setText(self.ui_text('Video ekleyerek başlayın'))
        self.timeline_frame = 0
        self.apply_project_state(document)
        self.clear_history()
        self.mark_saved()
        return True

    def project_controls(self):
        """(widget, getter, setter) for every control apply_project_state writes."""
        # Keyed combos are captured and restored by key, so a language switch in between cannot break them.
        return [(self.aspect, self.aspect.currentData, lambda key: self.select_choice(self.aspect, key)),
                (self.brightness, self.brightness.value, self.brightness.setValue),
                (self.contrast, self.contrast.value, self.contrast.setValue),
                (self.saturation, self.saturation.value, self.saturation.setValue),
                (self.speed, self.speed.currentData, lambda key: self.select_choice(self.speed, key)),
                (self.export_profile, self.export_profile.currentData,
                 lambda key: self.select_choice(self.export_profile, key)),
                (self.publish_title, self.publish_title.text, self.publish_title.setText),
                (self.publish_caption, self.publish_caption.toPlainText, self.publish_caption.setPlainText),
                (self.publish_tags, self.publish_tags.toPlainText, self.publish_tags.setPlainText),
                (self.ai_prompt, self.ai_prompt.toPlainText, self.ai_prompt.setPlainText),
                (self.project_title, self.project_title.text, self.project_title.setText),
                (self.project_subtitle, self.project_subtitle.text, self.project_subtitle.setText),
                (self.apply_captions_button, self.apply_captions_button.isEnabled, self.apply_captions_button.setEnabled)]

    def open_snapshot(self) -> dict:
        """Everything opening a project can replace, so a failed open can be undone exactly."""
        return {'state': copy.deepcopy(self.state), 'multitrack': self.multitrack,
                'selected': (self.multitrack_view.selected, self.multitrack_view.selected_track),
                'frame': self.timeline_frame, 'project_path': self.project_path,
                'saved_signature': self._saved_signature, 'pending': self._pending_project,
                'template_before_video': getattr(self, '_template_before_video', False),
                'media': list(self.media_bin.paths),
                # Steps are never modified once stored, so copying the lists is enough.
                'history': (list(self._undo_stack), list(self._redo_stack)),
                'captions': (self.caption_segments, self.caption_source),
                'controls': [(widget, setter, getter()) for widget, getter, setter in self.project_controls()]}

    def restore_open_snapshot(self, snapshot: dict) -> None:
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        self.proxy_timer.stop()
        # Plain data first: it decides what Save and autosave write, and where.
        self.project_path = snapshot['project_path']
        self._saved_signature = snapshot['saved_signature']
        self._pending_project = snapshot['pending']
        self._template_before_video = snapshot['template_before_video']
        self.multitrack = snapshot['multitrack']
        self.media_bin.paths[:] = snapshot['media']
        undo, redo = snapshot['history']
        self._undo_stack[:], self._redo_stack[:] = undo, redo
        self._drag_before = None
        self.update_history_controls()
        self.caption_segments, self.caption_source = snapshot['captions']
        # Controls with their signals blocked: their slots would write into state and re-render mid-restore.
        for widget, setter, value in snapshot['controls']:
            blocked = widget.blockSignals(True)
            try:
                setter(value)
            finally:
                widget.blockSignals(blocked)
            if hasattr(widget, 'value_label'):
                widget.value_label.setText(f'{value:+d}')
        self.state = copy.deepcopy(snapshot['state'])
        self.proxy.set_speed(self.state.speed)
        self.multitrack_view.set_model(self.multitrack)
        self.multitrack_view.selected, self.multitrack_view.selected_track = snapshot['selected']
        self.refresh_timeline_view()
        self.refresh_media_bin()
        self.update_range_label()
        self.timeline_frame = snapshot['frame']
        try:
            self.seek_timeline(self.timeline_frame)  # only refreshes the picture; the data is already back
        except Exception:
            self.multitrack_view.update()

    def apply_project_state(self, document: dict) -> None:
        raw = document.get("state", {})
        allowed = set(EditState.__dataclass_fields__)
        merged = {key: value for key, value in raw.items() if key in allowed}
        merged["duration"] = self.state.duration
        self.state = EditState(**merged)
        self.multitrack = Timeline.from_dict(document['timeline']) if 'timeline' in document else Timeline.from_legacy(merged)
        self.fill_source_lengths()
        self.multitrack_view.set_model(self.multitrack)
        self.refresh_timeline_view()
        for track in self.multitrack.tracks:
            for clip in track.clips:
                if clip.source:
                    self.media_bin.add(clip.source)
        self.refresh_media_bin()
        # The legacy in/out range, clamped to the video as the old range bar did.
        duration = max(0.01, self.state.duration)
        start = max(0.0, min(float(self.state.start), duration))
        end = max(start + min(0.05, duration), min(float(self.state.end or duration), duration))
        self.state.start, self.state.end = start, end
        self.update_range_label()
        # Older files may hold display text (Turkish, or English if saved with the English UI): map to keys.
        self.state.aspect = self.select_aspect(self.state.aspect)
        self.brightness.setValue(self.state.brightness)
        self.contrast.setValue(self.state.contrast)
        self.saturation.setValue(self.state.saturation)
        for box, name in self.audio_boxes():
            setattr(self.state, name, getattr(self.state, name) is True)  # only a real true switches it on
            box.blockSignals(True)
            box.setChecked(getattr(self.state, name))
            box.blockSignals(False)
        self.state.speed = self.select_speed(self.state.speed)
        self.export_profile.blockSignals(True)
        self.state.export_profile = self.select_export_profile(self.state.export_profile)
        self.export_profile.blockSignals(False)
        publish = document.get("publish", {})
        self.publish_title.setText(publish.get("title", ""))
        self.publish_caption.setPlainText(publish.get("caption", ""))
        self.publish_tags.setPlainText(publish.get("hashtags", ""))
        self.ai_prompt.setPlainText(document.get("ai_prompt", self.ai_prompt.toPlainText()))
        self.update_timeline_scroll()
        self.seek_timeline(self.timeline_frame)  # an empty timeline clears the previous project's frame
        self.set_status(self.ui_text("Proje açıldı ve son ayarlar geri yüklendi."))

    def fill_source_lengths(self) -> None:
        """Older projects stored media clips without their source's length, so trimming a clip's end could
        stretch it past the media into a black, silent tail. Fill it in from the media's duration."""
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        known = {self.state.source: self.state.duration} if self.state.source and self.state.duration else {}
        media = None
        for track in self.multitrack.tracks:
            if track.kind not in ('video', 'audio', 'overlay'):
                continue
            for clip in track.clips:
                if clip.source_length is not None or not clip.source:
                    continue
                if clip.source not in known:
                    known[clip.source] = 0.0
                    if Path(clip.source).is_file():
                        try:
                            media = media or MediaService(ffmpeg_path())
                            known[clip.source] = media.duration(clip.source)
                        except (ValueError, RuntimeError, OSError):
                            log.warning("Medya süresi okunamadı: %s", clip.source)
                frames = round(known[clip.source] * fps)
                if frames > 0:  # never shorter than what the clip already uses
                    clip.source_length = max(frames, clip.source_in + clip.length)

    def untitled_recovery_path(self) -> Path:
        """This instance's recovery file for an untitled project, with its lock taken (one per process)."""
        path = recovery_dir() / f"recovery-{os.getpid()}.akis.json"
        if self._recovery_lock is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            lock = recovery_lock(path)
            if not lock.tryLock(0):
                raise OSError(f'Kurtarma dosyası kilitlenemedi: {lock.error()}')
            self._recovery_lock = lock
        return path

    def autosave_path(self) -> str:
        return self.project_path + ".autosave" if self.project_path else str(self.untitled_recovery_path())

    def autosave_project(self) -> bool:
        """Write unsaved work where a crash can be recovered from. Returns whether a file was written."""
        if not self.has_unsaved_changes():  # also False when there is nothing to keep
            return False
        try:
            path = self.autosave_path()
            if self._autosave_file and self._autosave_file != path:
                self.remove_file(Path(self._autosave_file))  # e.g. untitled recovery after the first save
            self.write_project(path, snapshot=False)
        except Exception as exc:
            log.exception("Otomatik kayıt başarısız")
            self.set_status(f'Otomatik kayıt yapılamadı: {exc}')
            return False
        self._autosave_file = path
        return True

    @staticmethod
    def remove_file(path: Path) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            log.exception("Dosya silinemedi: %s", path)

    def discard_autosave(self, keep: str | None = None) -> None:
        """Remove this window's autosave/recovery file: the work is saved, discarded or the window closes."""
        targets = {self._autosave_file} if self._autosave_file else set()
        if self.project_path:
            targets.add(self.project_path + ".autosave")
        for target in targets:
            if keep is None or os.path.normcase(os.path.abspath(target)) != os.path.normcase(os.path.abspath(keep)):
                self.remove_file(Path(target))
        self._autosave_file = ""
        if self._recovery_lock is not None:
            self.remove_file(recovery_dir() / f"recovery-{os.getpid()}.akis.json")
            self._recovery_lock.unlock()
            self._recovery_lock = None

    def ask_recovery(self, path) -> str:
        """'open', 'later' (keep the file, ask again another time) or 'delete' for a recovery file."""
        try:
            when = datetime.fromtimestamp(Path(path).stat().st_mtime).strftime('%d.%m.%Y %H:%M')
        except (OSError, ValueError, OverflowError):
            when = '?'
        box = QMessageBox(QMessageBox.Icon.Question, APP_NAME, self.ui_text(RECOVERY_QUESTION, when=when),
                          QMessageBox.StandardButton.NoButton, self)
        box.setInformativeText(self.ui_text(RECOVERY_DETAIL))
        open_button = box.addButton(self.ui_text('Aç'), QMessageBox.ButtonRole.AcceptRole)
        later_button = box.addButton(self.ui_text('Sonra sor'), QMessageBox.ButtonRole.RejectRole)
        delete_button = box.addButton(self.ui_text('Sil'), QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(open_button)
        box.setEscapeButton(later_button)  # closing the box never deletes anything
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_button:
            return 'open'
        return 'delete' if clicked is delete_button else 'later'

    def offer_recovery(self) -> bool:
        """At startup: offer untitled work left behind by an instance that is no longer running."""
        for path, lock in orphan_recovery_files():
            try:
                answer = self.ask_recovery(path)
                if answer == 'later':
                    continue  # kept; the lock is released below, so the next launch offers it again
                if answer != 'open':
                    self.remove_file(path)
                    continue
                if not self.load_project_document(str(path), "", recovered=True):
                    continue  # unreadable: kept for a later attempt, the user has been told
                # Keep the work in our own recovery file before the orphan goes away.
                if self.autosave_project():
                    self.remove_file(path)
                return True
            finally:
                lock.unlock()
        return False

    def system_language_code(self) -> str:
        return "tr" if QLocale.system().language() == QLocale.Language.Turkish else "en"

    @staticmethod
    def _retranslated(widget, slot: str, current: str, code: str) -> str:
        """Text for one translatable slot of a widget, from the Turkish source remembered on the widget.

        Whole strings only. The remembered source is used while the slot still shows that source or its
        translation; text that code put there since is taken as the new source (mapped back to Turkish
        only when it is exactly a known English string).
        """
        prop = f"i18n_{slot}"
        source = widget.property(prop)
        if not isinstance(source, str) or current not in (source, i18n.translate(source, "en")):
            source = i18n.source_of(current)
            widget.setProperty(prop, source)
        return i18n.translate(source, code)

    def ui_language(self) -> str:
        """The language the UI is shown in: the one apply_language last used, which messages and dialogs follow."""
        return getattr(self, "_ui_language", None) or self.language.currentData() or "tr"

    def apply_language(self, code: str) -> None:
        """Show the UI in `code` ('tr' or 'en'). User content and saved values are never changed."""
        self._ui_language = code if code in ("tr", "en") else "tr"
        for widget in self.findChildren(QWidget):
            if widget.property("i18n_skip"):
                continue
            if isinstance(widget, (QLabel, QPushButton, QCheckBox, QToolButton)):
                text = self._retranslated(widget, "text", widget.text(), code)
                if text != widget.text():
                    widget.setText(text)
            if isinstance(widget, (QLineEdit, QPlainTextEdit)) and widget.placeholderText():
                widget.setPlaceholderText(self._retranslated(widget, "placeholder", widget.placeholderText(), code))
            if widget.toolTip():
                tip = self._retranslated(widget, "tooltip", widget.toolTip(), code)
                if tip != widget.toolTip():
                    widget.setToolTip(tip)
            if isinstance(widget, QTabWidget):
                for index in range(widget.count()):
                    widget.setTabText(index, self._retranslated(widget, f"tab{index}", widget.tabText(index), code))
            if isinstance(widget, QComboBox) and widget.property("i18n_keyed"):
                # Only combos whose items carry keys; others (AI suggestions, models) show content as is.
                blocked = widget.blockSignals(True)
                for index in range(widget.count()):
                    widget.setItemText(index, i18n.translate(str(widget.itemData(index)), code))
                widget.blockSignals(blocked)
        self.version_button.setToolTip(i18n.translate(
            "Kurulu sürüm: {version}. Güncellemeleri denetlemek için tıklayın.", code).format(
                version=update_service.VERSION))
        self.version_button.setAccessibleName(self.version_button.toolTip())
        self.play_button.setToolTip(i18n.translate("Oynat / duraklat (Boşluk)", code))  # the button is i18n_skip
        if not self.state.source:  # the header shows placeholders until a video is loaded
            self.project_title.setText(i18n.translate("Yeni proje", code))
            self.project_subtitle.setText(i18n.translate("Video ekleyerek başlayın", code))

    def change_language(self) -> None:
        code = self.language.currentData()
        self.settings.setValue("language", code)
        self.apply_language(code)
        self.set_status("Language changed to English." if code == "en" else "Dil Türkçe olarak değiştirildi.")

    @staticmethod
    def stop_story_workers() -> None:
        """Story Studio generation threads outlive a closed dialog; stop them when the module offers it."""
        try:
            from akis import story_workers
        except Exception:
            return
        stop_all = getattr(story_workers, 'stop_all', None)
        if callable(stop_all):
            try:
                stop_all()
            except Exception:
                log.exception("Hikâye işleri durdurulamadı")

    def closeEvent(self, event):
        if self._workers:
            if not self.isVisible():  # a hidden window (tests, scripted runs) has nobody to ask
                self.set_status('İşlem devam ediyor; kapatmadan önce bitmesini bekleyin.')
                event.ignore()
                return
            answer = QMessageBox.question(self, APP_NAME, CANCEL_ON_CLOSE_QUESTION,
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        # Unsaved story scenes (paid generations) first: its Cancel keeps the whole app open.
        story_ok = getattr(self.story_dialog, 'confirm_close', None)
        if callable(story_ok) and not story_ok():
            event.ignore()
            return
        if not self.confirm_close():
            if self.story_dialog is not None and hasattr(self.story_dialog, '_close_approved'):
                self.story_dialog._close_approved = False  # the app stays open: ask again next time
            event.ignore()
            return
        self.autosave_timer.stop()
        self.discard_autosave()  # clean close: saved or deliberately discarded, nothing to recover
        if self._persist_ui:
            try:
                self.save_ui_settings(self.settings)
            except Exception:
                log.exception("Pencere ayarları kaydedilemedi")
        self.play_timer.stop()
        self.playback_clock.stop()
        self.timeline_audio.stop()
        self._shutting_down = True  # from here on, late worker results and errors are dropped
        self.stop_workers()
        if self.story_dialog is not None:
            self.story_dialog.close()  # stops its own generation workers
        self.stop_story_workers()
        # Bounded: a slow or stalled link must not hang the closing window. An interrupted download
        # deletes its partial file itself.
        self.stop_thread(self.update_download)
        self.stop_thread(self.update_check)
        self.proxy_timer.stop()
        self.still_timer.stop()
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
QPushButton#versionTag { background: transparent; color: #7d8194; font-size: 11px; padding: 4px 2px; text-align: left; }
QPushButton#versionTag:hover { color: #c9c2ff; text-decoration: underline; }
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
    try:
        log_path = setup_logging(app_data_dir() / "logs")
    except OSError:
        log_path = None
    automated = app.platformName() in ("offscreen", "minimal")  # tests and scripted runs: nobody to click OK
    sys.excepthook = ExceptionHook(log_path, show_dialogs=not automated)
    log.info("%s başlatıldı (pid %s)", APP_NAME, os.getpid())
    start_temp_cleanup()
    window = MainWindow()
    window.show()
    if not automated:
        QTimer.singleShot(0, window.offer_recovery)
    code = app.exec()
    wait_for_background_threads()
    return code


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

