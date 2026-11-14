from __future__ import annotations

import faulthandler
import json
import logging
import logging.handlers
import os
import traceback
import sys
import threading
from pathlib import Path

# Prefer the native Windows backend; retain an explicit user override.
if sys.platform == "win32":
    os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

from akis.timeline_model import Timeline
from akis.timeline_render import duration_frames
from akis import timeline_service
from akis.timeline_audio import TimelineAudio
from akis.preview_controller import PreviewController
from akis.preview_widget import ProxyPlayback
from akis.update_dialog import UpdateProgressDialog
from akis.media_bin import MediaBin
from akis import ai_providers, update_service
from akis import i18n
from akis import shortcuts
from akis import privacy_log
from akis import theme
from akis import app_support
from akis.app_support import (  # re-exported: older code and tests read them from main
    APP_NAME,
    ORG_NAME,
    VIDEO_EXTS,
    runtime_file,
    ffmpeg_path,
    log,
    RECOVERY_QUESTION,
    RECOVERY_DETAIL,
    IDEA_REPLACES_PROMPT_QUESTION,
    STALE_PLAN_QUESTION,
    UPDATE_REMIND_AFTER,
    CANCEL_ON_CLOSE_QUESTION,
    THREAD_STOP_WAIT_MS,
    UNDO_LIMIT,
    STILL_CLIP_SECONDS,
    _background_threads,
    start_temp_cleanup,
    wait_for_background_threads,
    app_data_dir,
    recovery_dir,
    recovery_lock,
    orphan_recovery_files,
    normalize_export_path,
    safe_filename,
    format_time,
    EditState,
)
from akis.ui_style import STYLE
from akis.window.layout import LayoutMixin
from akis.window.playback import PlaybackMixin
from akis.window.timeline_edit import TimelineEditMixin
from akis.window.project import ProjectMixin
from akis.window.assistant import AssistantMixin
from akis.window.exporting import ExportMixin
from akis.window.updates import UpdatesMixin

from PySide6.QtCore import QByteArray, QLocale, QLockFile, QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QWidget,
)


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


class MainWindow(LayoutMixin, PlaybackMixin, TimelineEditMixin, ProjectMixin, AssistantMixin, ExportMixin, UpdatesMixin, QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = EditState()
        self.media_bin = MediaBin()
        self._source_rate = (30, 1)  # frame rate of the video loaded last; a new timeline adopts it
        self.multitrack = Timeline.from_legacy({})
        self.timeline_frame = 0
        self.playback_clock = timeline_service.PlaybackClock()
        self.preview = PreviewController(app_support.ffmpeg_path, self)
        self.preview.frame_ready.connect(self.show_timeline_frame)
        self.preview.failed.connect(self.set_status)
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self.advance_timeline)
        self.proxy = ProxyPlayback(app_support.ffmpeg_path, self)
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
        self.setWindowIcon(QIcon(str(app_support.runtime_file('app.ico'))))

        self.preview_audio_output = QAudioOutput()
        self.preview_audio_output.setVolume(0.8)
        self.preview_audio = QMediaPlayer()
        self.preview_audio.setAudioOutput(self.preview_audio_output)
        self.timeline_audio = TimelineAudio(self.preview_audio, self, player_factory=self.new_preview_player)
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


    # Self-update: check the version, ask, download with a progress dialog into one fixed folder (the install
    # folder is not touched), check free space, ask again, verify, hand over to the installer helper.
    def update_folder(self) -> Path:
        return update_service.update_dir(app_support.app_data_dir())

    @staticmethod
    def install_folder() -> Path:
        return Path(sys.executable).resolve().parent

    def refresh_privacy(self) -> None:
        text = privacy_log.summary(self.ui_template)
        if text != self.privacy_label.text():
            self.privacy_label.setText(text)

    def ui_template(self, template: str) -> str:
        """`template` in the current UI language, placeholders left for the caller to fill."""
        return i18n.translate(template, self.ui_language())

    def ui_text(self, template: str, **values) -> str:
        """A whole-string translation of `template` into the current UI language, then filled in."""
        return i18n.translate(template, self.ui_language()).format(**values)


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


    MARK_COLOURS = {'Kırmızı': 'red', 'Sarı': 'yellow', 'Beyaz': 'white', 'Yeşil': 'green', 'Mavi': 'blue', 'Pembe': 'pink'}


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
        i18n.use_qt_language(self._ui_language)  # Qt's own buttons (Yes/No, Cancel, Save…) follow the UI
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

    def paint_brand(self) -> None:
        self.brand.setText(f"AKIŞ  <span style='color:{theme.hex_('accent_text')}'>KURGU</span>")

    def apply_theme(self, name) -> None:
        """Dark or light: the stylesheets are set again from akis.theme and the painted widgets repaint."""
        name = theme.set_current(name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.css(STYLE))
        self.start_panel.restyle()
        self.paint_brand()
        for widget in self.findChildren(QWidget):
            QWidget.update(widget)  # some subclasses (QListWidget) overload update()

    def change_theme(self) -> None:
        name = list(theme.LABELS)[max(0, self.theme_box.currentIndex())]
        self.settings.setValue("theme", name)
        self.apply_theme(name)
        self.set_status(self.ui_text("Görünüm değiştirildi."))

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
                self.set_status(self.ui_text('İşlem devam ediyor; kapatmadan önce bitmesini bekleyin.'))
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

    def open_path(self, path: str) -> bool:
        """Open a file handed to the app from outside: the command line, “Open with”, or a drop on the window.
        A project file opens as the project (after the usual unsaved-work question); a video is added."""
        file = Path(path)
        if not file.is_file():
            self.set_status(self.ui_text('Dosya bulunamadı: {name}', name=file.name))
            return False
        suffix = file.suffix.lower()
        if suffix == '.json':
            if not self.can_start_work() or not self.confirm_close():
                return False
            return bool(self.open_project_file(str(file)))
        if suffix in VIDEO_EXTS:
            self.add_video(str(file))
            return True
        self.set_status(self.ui_text('Bu dosya türü açılamıyor: {name}', name=file.name))
        return False

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in (*VIDEO_EXTS, '.json'):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.open_path(urls[0].toLocalFile())
            event.acceptProposedAction()


def startup_file(argv) -> str:
    """The file the app was started with, or ''. Options (--name …) are not files."""
    for argument in argv[1:]:
        if argument.startswith('--'):
            return ''
        if argument.strip():
            return argument
    return ''


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyle("Fusion")
    theme.set_current(QSettings(ORG_NAME, APP_NAME).value("theme", theme.DEFAULT))
    app.setStyleSheet(theme.css(STYLE))
    try:
        log_path = setup_logging(app_support.app_data_dir() / "logs")
    except OSError:
        log_path = None
    automated = app.platformName() in ("offscreen", "minimal")  # tests and scripted runs: nobody to click OK
    sys.excepthook = ExceptionHook(log_path, show_dialogs=not automated)
    log.info("%s başlatıldı (pid %s)", APP_NAME, os.getpid())
    app_support.start_temp_cleanup()
    window = MainWindow()
    window.show()
    given = startup_file(sys.argv)
    if given:  # started with a file (“Open with”, a file dropped on the program): open that, not a recovery
        QTimer.singleShot(0, lambda: window.open_path(given))
    elif not automated:
        QTimer.singleShot(0, window.offer_recovery)
    code = app.exec()
    app_support.wait_for_background_threads()
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

