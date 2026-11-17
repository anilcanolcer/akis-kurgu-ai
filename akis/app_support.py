"""What the window and its parts share: names, paths, the recovery folder, small helpers.

Moved out of main.py; main.py re-exports these names. Tests patch the functions here
(akis.app_support.recovery_dir, ...), which every caller reaches through this module."""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import shutil
import sys
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path

from akis import update_service
from akis import i18n
from akis.temp_cleanup import cleanup_stale_temp_dirs

from PySide6.QtCore import QLockFile, QStandardPaths, QThread

APP_NAME = "Akış Kurgu AI"
ORG_NAME = "AkisStudio"
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
def runtime_file(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # the project folder
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
STALE_PLAN_QUESTION = "Kurgu ayarları veya içerik bu sırada değişti. Plan yine de uygulansın mı?"
UPDATE_REMIND_AFTER = 24 * 3600  # a postponed update is not offered again for this many seconds
CANCEL_ON_CLOSE_QUESTION = "Devam eden işlem iptal edilip çıkılsın mı?"
THREAD_STOP_WAIT_MS = 2000  # how long closing the window waits for a background thread
UNDO_LIMIT = 50  # timeline edit steps kept for undo
STILL_CLIP_SECONDS = 5  # a generated still image is added to the timeline as a clip of this length
_background_threads: list[QThread] = []  # still stopping after their window closed; waited for in main()
_background_threads_lock = threading.Lock()


def retain_background_thread(thread) -> None:
    """Keep a QThread alive after its window closes, until Qt reports that it finished."""
    with _background_threads_lock:
        if thread in _background_threads:
            return
        _background_threads.append(thread)
    finished = getattr(thread, "finished", None)
    connect = getattr(finished, "connect", None)
    if callable(connect):
        reference = weakref.ref(thread)
        connect(lambda ref=reference: release_background_thread(ref()))


def release_background_thread(thread) -> None:
    """Drop a retained thread only after its run() method has ended."""
    if thread is None:
        return
    with _background_threads_lock:
        try:
            _background_threads.remove(thread)
        except ValueError:
            pass


def _background_thread_finished(thread) -> bool:
    """Tell a completed QThread from one whose start() has not reached the OS yet."""
    is_finished = getattr(thread, "isFinished", None)
    if callable(is_finished):
        return bool(is_finished())
    is_running = getattr(thread, "isRunning", None)
    return callable(is_running) and not is_running()


def start_temp_cleanup(root=None) -> threading.Thread:
    """Remove scratch folders a crash left in the temp directory, off the GUI thread (a big folder or a
    slow disk must not delay the window). Never raises; the thread is a daemon so it cannot block exit."""
    thread = threading.Thread(target=cleanup_stale_temp_dirs, args=(root,), name="akis-temp-cleanup", daemon=True)
    thread.start()
    return thread


def wait_for_background_threads() -> None:
    """After the event loop, stop and drain retained QThreads without dropping live wrappers.

    A bounded wait is repeated while a thread remains alive.  This runs after the UI event loop has closed,
    so a slow non-cancellable operation may delay process exit, but it cannot destroy a running QThread.
    Cancellable workers are asked to stop first and should drain promptly.
    """
    asked_to_stop = set()
    while True:
        with _background_threads_lock:
            threads = list(_background_threads)
        if not threads:
            return
        for thread in threads:
            if _background_thread_finished(thread):
                release_background_thread(thread)
                continue
            identity = id(thread)
            if identity not in asked_to_stop:
                asked_to_stop.add(identity)
                cancel = getattr(thread, "cancel", None)
                if callable(cancel):
                    cancel()
                else:
                    request = getattr(thread, "requestInterruption", None)
                    if callable(request):
                        request()
            wait = getattr(thread, "wait", None)
            if callable(wait) and wait(THREAD_STOP_WAIT_MS):
                if _background_thread_finished(thread):
                    release_background_thread(thread)
                else:
                    # QThread.wait() returns immediately before start() has reached the OS thread.
                    # Keep the wrapper registered and avoid a busy loop until it starts or finishes.
                    threading.Event().wait(0.01)
            else:
                log.warning("Arka plan işi hâlâ bitmedi; güvenli kapanış için bekleniyor")


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
