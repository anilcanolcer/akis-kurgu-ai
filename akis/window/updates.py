"""Updates: checking, offering, downloading and installing a new version."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from akis.update_worker import UpdateCheckWorker, UpdateDownloadWorker
from akis.update_dialog import UpdateProgressDialog
from akis import update_service

from PySide6.QtWidgets import QMessageBox

from akis.app_support import APP_NAME, UPDATE_REMIND_AFTER, log


class UpdatesMixin:
    """Updates: checking, offering, downloading and installing a new version."""

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
