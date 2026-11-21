"""Exporting: one video, FCPXML, batches, Shorts, highlights, three formats, publish text."""
from __future__ import annotations

import copy
import os
from pathlib import Path

from akis.media_service import MediaService
from akis.timeline_render import duration_frames, export_failure
from akis import timeline_service
from akis.render_worker import TimelineRenderWorker
from akis import export_progress
from akis import preflight
from akis import user_templates
from akis import fast_export
from akis import multi_export
from akis import fcpxml_export
from akis.batch_dialog import BatchDialog
from akis import shorts_split
from akis.shorts_dialog import ShortsDialog
from akis import highlights
from akis.highlights_dialog import HighlightsDialog
from akis.batch_export import BatchExportWorker, outputs_for
from akis import silence_cut

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from akis import app_support
from akis.app_support import APP_NAME, safe_filename


class ExportMixin:
    """Exporting: one video, FCPXML, batches, Shorts, highlights, three formats, publish text."""

    def safe_export_paths(self, outputs) -> bool:
        sources = [self.state.source, *self.media_bin.paths]
        if any(timeline_service.output_overwrites_source(self.multitrack, path, sources) for path in outputs):
            QMessageBox.warning(self, APP_NAME, self.ui_text('Çıktı yolu kaynak medya ile aynı olamaz; başka bir dosya adı seçin.'))
            return False
        return True

    def ensure_export_timeline(self) -> bool:
        if duration_frames(self.multitrack) > 0:
            return True
        QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde video yok.'))
        return False

    def export_video(self) -> None:
        if not self.can_start_work():
            return
        if not self.ensure_export_timeline():
            return
        try:
            canvas = self.export_canvas_size()
        except (ValueError, RuntimeError, OSError) as exc:  # e.g. "Kaynak oranı" with no usable video clip
            QMessageBox.warning(self, APP_NAME, self.ui_text('Dışa aktarma boyutu belirlenemedi: {error}', error=exc))
            self.set_status(self.ui_text('Dışa aktarma başlatılamadı.'))
            return
        findings = preflight.check(self.multitrack, say=self.ui_template)
        if findings and QMessageBox.question(self, APP_NAME, preflight.question(findings, self.ui_template),
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.set_status(self.ui_text('Dışa aktarma başlatılmadı.'))
            return
        default = safe_filename(self.project_title.text()) + "_akis.mp4"
        chosen, _ = QFileDialog.getSaveFileName(self, "Videoyu dışa aktar", str(Path.home() / "Videos" / default), "MP4 Video (*.mp4)")
        if not chosen:
            return
        path = app_support.normalize_export_path(chosen)
        if not self.confirm_overwrite(chosen, path):
            return
        if not self.safe_export_paths([path]):
            return
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        seconds = duration_frames(self.multitrack) / fps / self.state.speed
        problem = export_progress.space_problem(path, export_progress.estimated_bytes(canvas, fps, seconds),
                                                say=self.ui_template)
        if problem and QMessageBox.question(self, APP_NAME, problem + '\n\n' + self.ui_text('Yine de devam edilsin mi?'),
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.set_status(self.ui_text('Dışa aktarma başlatılmadı.'))
            return
        self.state.aspect = self.aspect.currentData()
        self.state.export_profile = self.export_profile.currentData()
        # Nothing but cuts of one video: offer to copy it instead of encoding it again (akis.fast_export).
        pieces = fast_export.plan(self.multitrack, self.render_adjustments(), canvas, MediaService(app_support.ffmpeg_path()))
        copying = bool(pieces) and QMessageBox.question(
            self, APP_NAME, self.ui_text(fast_export.QUESTION),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes) == QMessageBox.StandardButton.Yes
        if copying:
            self.worker = fast_export.FastExportWorker(self.multitrack, pieces, path, app_support.ffmpeg_path(),
                                                       say=self.ui_template)
        else:
            self.worker = TimelineRenderWorker(self.multitrack, path, canvas, app_support.ffmpeg_path(),
                                               adjustments=self.render_adjustments(), say=self.ui_template)
        self.begin_work(self.ui_text("Dışa aktarma hazırlanıyor…"))
        self._export_estimator = export_progress.Estimator()
        self.worker.progress.connect(self.on_export_progress)
        self.worker.finished.connect(lambda: self.progress.setRange(0, 0))  # back to the "busy" look
        self.worker.completed.connect(self.on_exported)
        if copying:  # a copy that fails says how to get the normal export instead
            self.worker.failed.connect(lambda message: self.on_worker_error(
                self.ui_text('Hızlı dışa aktarma yapılamadı: {error}\n\nYeniden dışa aktarıp soruya “Hayır” diyerek '
                             'olağan dışa aktarmayı kullanın.', error=message)))
        else:
            self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_export_cancelled)
        self.start_worker()

    def on_export_progress(self, percent: int) -> None:
        if self._shutting_down:
            return
        shown, remaining = self._export_estimator.update(percent / 100)
        self.progress.setRange(0, 100)
        self.progress.setValue(shown)
        self.set_status(export_progress.text(shown, remaining, self.ui_template))

    def confirm_overwrite(self, chosen: str, path: str) -> bool:
        """The file dialog only confirmed overwriting `chosen`; ask again when the final name differs and exists."""
        if os.path.normcase(os.path.abspath(chosen)) == os.path.normcase(os.path.abspath(path)) or not Path(path).exists():
            return True
        answer = QMessageBox.question(self, APP_NAME, self.ui_text('“{name}” zaten var. Üzerine yazılsın mı?', name=Path(path).name),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def export_fcpxml(self) -> None:
        """Write the cut as an FCPXML file for DaVinci Resolve / Final Cut Pro (akis.fcpxml_export)."""
        if not self.can_start_work() or not self.ensure_export_timeline():
            return
        try:
            canvas = self.export_canvas_size()
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Kurgu dosyası yazılamadı: {error}', error=exc))
            return
        default = safe_filename(self.project_title.text()) + ".fcpxml"
        chosen, _ = QFileDialog.getSaveFileName(self, self.ui_text("Kurgu dosyası olarak aktar (DaVinci Resolve)"),
                                                str(Path.home() / "Videos" / default), "FCPXML (*.fcpxml)")
        if not chosen:
            return
        path = Path(chosen) if Path(chosen).suffix.lower() == '.fcpxml' else Path(chosen + '.fcpxml')
        if not self.confirm_overwrite(chosen, str(path)):
            return
        try:
            text, report = fcpxml_export.build(self.multitrack, canvas, MediaService(app_support.ffmpeg_path()),
                                               name=self.project_title.text() or APP_NAME)
            from akis.story_workers import write_atomic
            write_atomic(path, text.encode('utf-8'))
        except (OSError, ValueError, RuntimeError) as exc:
            details = export_failure(exc, path, self.ui_template)
            QMessageBox.warning(self, APP_NAME, self.ui_text('Kurgu dosyası yazılamadı: {error}', error=details))
            return
        summary = fcpxml_export.describe(report, self.ui_template)
        self.set_status(self.ui_text('Kurgu dosyası kaydedildi: {name}', name=path.name))
        QMessageBox.information(self, APP_NAME, self.ui_text('Kurgu dosyası kaydedildi:\n{path}', path=str(path))
                                + '\n\n' + summary)

    def export_batch(self) -> None:
        """Process several videos the same way and export each (akis.batch_export)."""
        if not self.can_start_work():
            return
        dialog = BatchDialog(self, templates=user_templates.load(app_support.app_data_dir()), language=self.ui_language(),
                             folder=str(Path.home() / "Videos"))
        if not dialog.exec():
            return
        videos, folder, cut_silences, template = dialog.selection()
        outputs = outputs_for(videos, folder)
        if not self.safe_export_paths(outputs):
            return
        existing = [Path(path).name for path in outputs if Path(path).exists()]
        if existing and QMessageBox.question(
                self, APP_NAME, self.ui_text('Şu dosyalar zaten var ve üzerine yazılacak:\n{names}\n\nDevam edilsin mi?',
                                             names='\n'.join(existing)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.worker = BatchExportWorker(videos, folder, app_support.ffmpeg_path(), aspect=self.aspect.currentData(),
                                        profile=self.export_profile.currentData(),
                                        adjustments={k: v for k, v in self.render_adjustments().items()},
                                        cut_silences=cut_silences, template=template, say=self.ui_template)
        self.begin_work(self.ui_text("Dışa aktarma hazırlanıyor…"))
        self._export_estimator = export_progress.Estimator()
        self.worker.progress.connect(self.on_export_progress)
        self.worker.finished.connect(lambda: self.progress.setRange(0, 0))
        self.worker.completed.connect(self.on_batch_exported)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_export_cancelled)
        self.start_worker()

    def on_batch_exported(self, report: str) -> None:
        if self._shutting_down:
            return
        self.finish_work(self.ui_text("Dışa aktarma tamamlandı."))
        QMessageBox.information(self, APP_NAME, report)

    def export_shorts(self) -> None:
        """Divide the whole edit into consecutive vertical Shorts and export them all (akis.shorts_split)."""
        if not self.can_start_work() or not self.ensure_export_timeline():
            return
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        total = duration_frames(self.multitrack) / fps
        if total <= 0:
            QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde video yok.'))
            return
        executable = app_support.ffmpeg_path()
        timeline = copy.deepcopy(self.multitrack)
        self.run_analysis(self.ui_text('Konuşmadaki duraklamalar aranıyor…'),
                          lambda: shorts_split.timeline_pauses(timeline, lambda source: silence_cut.cached_levels(executable, source)),
                          lambda pauses: self.choose_shorts(pauses, total))

    def find_highlights(self) -> None:
        """List the liveliest stretches of the edit and export the chosen ones as Shorts (akis.highlights)."""
        if not self.can_start_work() or not self.ensure_export_timeline():
            return
        if duration_frames(self.multitrack) / (self.multitrack.fps_num / self.multitrack.fps_den) < 60:
            QMessageBox.information(self, APP_NAME, self.ui_text('Öne çıkan anlar en az bir dakikalık videolarda aranır.'))
            return
        executable = app_support.ffmpeg_path()
        timeline = copy.deepcopy(self.multitrack)

        def work():
            levels = {}
            read = lambda source: levels.setdefault(source, silence_cut.cached_levels(executable, source))
            pauses = shorts_split.timeline_pauses(timeline, read)
            return highlights.find(timeline, read, pauses=pauses)
        self.run_analysis(self.ui_text('Öne çıkan anlar aranıyor…'), work, self.choose_highlights)

    def choose_highlights(self, found) -> None:
        if not found:
            QMessageBox.information(self, APP_NAME, self.ui_text('Öne çıkan bir an bulunamadı.'))
            return
        said = shorts_split.spoken_on_timeline(self.multitrack, self.caption_source, self.caption_segments) \
            if self.caption_source and self.caption_segments else []
        titles = shorts_split.suggest_titles([item[:2] for item in found], said)
        dialog = HighlightsDialog(self, found=found, titles=titles, language=self.ui_language())
        if not dialog.exec():
            return
        parts, titles = dialog.selection()
        # The native Windows picker has produced fatal COM errors on this path. Qt's
        # own picker avoids that integration while keeping the same folder selection.
        folder = QFileDialog.getExistingDirectory(self, self.ui_text('Kaydedilecek klasör'),
                                                  str(Path.home() / "Videos"), QFileDialog.Option.DontUseNativeDialog)
        if not folder:
            return
        outputs = shorts_split.outputs_for(folder, titles, safe_filename(self.project_title.text()) + '-one-cikan')
        if not self.safe_export_paths(outputs):
            return
        existing = [Path(path).name for path in outputs if Path(path).exists()]
        if existing and QMessageBox.question(
                self, APP_NAME, self.ui_text('Şu dosyalar zaten var ve üzerine yazılacak:\n{names}\n\nDevam edilsin mi?',
                                             names='\n'.join(existing)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.worker = shorts_split.ShortsExportWorker(self.multitrack, parts, outputs, app_support.ffmpeg_path(),
                                                      adjustments=self.render_adjustments(), titles=titles,
                                                      say=self.ui_template, numbered=False)
        self.begin_work(self.ui_text("Dışa aktarma hazırlanıyor…"))
        self._export_estimator = export_progress.Estimator()
        self.worker.progress.connect(self.on_export_progress)
        self.worker.finished.connect(lambda: self.progress.setRange(0, 0))
        self.worker.completed.connect(self.on_exported)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_export_cancelled)
        self.start_worker()

    def choose_shorts(self, pauses, total) -> None:
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        speed = self.state.speed
        said = shorts_split.spoken_on_timeline(self.multitrack, self.caption_source, self.caption_segments) \
            if self.caption_source and self.caption_segments else []
        # The dialog's duration limit describes the finished video. Plan in playback seconds, then
        # turn the selected ranges back into timeline seconds for slicing every track together.
        dialog = ShortsDialog(self, total=total / speed, pauses=[pause / speed for pause in pauses],
                              said=[(second / speed, text) for second, text in said], language=self.ui_language())
        if not dialog.exec():
            return
        parts, framing, card, titles = dialog.selection()
        parts = [(start * speed, end * speed) for start, end in parts]
        folder = QFileDialog.getExistingDirectory(self, self.ui_text('Kaydedilecek klasör'),
                                                  str(Path.home() / "Videos"), QFileDialog.Option.DontUseNativeDialog)
        if not folder:
            return
        outputs = shorts_split.outputs_for(folder, titles, safe_filename(self.project_title.text()))
        if not self.safe_export_paths(outputs):
            return
        existing = [Path(path).name for path in outputs if Path(path).exists()]
        if existing and QMessageBox.question(
                self, APP_NAME, self.ui_text('Şu dosyalar zaten var ve üzerine yazılacak:\n{names}\n\nDevam edilsin mi?',
                                             names='\n'.join(existing[:12]) + ('\n…' if len(existing) > 12 else '')),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        needed = export_progress.estimated_bytes(shorts_split.CANVAS, fps, total / speed)
        problem = export_progress.space_problem(outputs[0], needed, say=self.ui_template)
        if problem and QMessageBox.question(self, APP_NAME, problem + '\n\n' + self.ui_text('Yine de devam edilsin mi?'),
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.set_status(self.ui_text('Dışa aktarma başlatılmadı.'))
            return
        self.worker = shorts_split.ShortsExportWorker(self.multitrack, parts, outputs, app_support.ffmpeg_path(),
                                                      adjustments=self.render_adjustments(), framing=framing, card=card,
                                                      titles=titles, say=self.ui_template)
        self.begin_work(self.ui_text("Dışa aktarma hazırlanıyor…"))
        self._export_estimator = export_progress.Estimator()
        self.worker.progress.connect(self.on_export_progress)
        self.worker.finished.connect(lambda: self.progress.setRange(0, 0))
        self.worker.completed.connect(self.on_exported)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_export_cancelled)
        self.start_worker()

    def export_three_formats(self) -> None:
        """The same edit as vertical, square and landscape files, one after the other (akis.multi_export)."""
        if not self.can_start_work() or not self.ensure_export_timeline():
            return
        findings = preflight.check(self.multitrack, say=self.ui_template)
        if findings and QMessageBox.question(self, APP_NAME, preflight.question(findings, self.ui_template),
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.set_status(self.ui_text('Dışa aktarma başlatılmadı.'))
            return
        default = safe_filename(self.project_title.text()) + "_akis.mp4"
        chosen, _ = QFileDialog.getSaveFileName(self, self.ui_text("Üç biçimde dışa aktar"),
                                                str(Path.home() / "Videos" / default), "MP4 Video (*.mp4)")
        if not chosen:
            return
        outputs = multi_export.targets(app_support.normalize_export_path(chosen))
        if not self.safe_export_paths(path for _, _, path in outputs):
            return
        existing = [Path(path).name for _, _, path in outputs if Path(path).exists()]
        if existing and QMessageBox.question(
                self, APP_NAME, self.ui_text('Şu dosyalar zaten var ve üzerine yazılacak:\n{names}\n\nDevam edilsin mi?',
                                             names='\n'.join(existing)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        seconds = duration_frames(self.multitrack) / fps / self.state.speed
        needed = sum(export_progress.estimated_bytes(canvas, fps, seconds) for _, canvas, _ in outputs)
        problem = export_progress.space_problem(outputs[0][2], needed, say=self.ui_template)
        if problem and QMessageBox.question(self, APP_NAME, problem + '\n\n' + self.ui_text('Yine de devam edilsin mi?'),
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.set_status(self.ui_text('Dışa aktarma başlatılmadı.'))
            return
        self.worker = multi_export.MultiExportWorker(self.multitrack, outputs, app_support.ffmpeg_path(),
                                                     adjustments=self.render_adjustments(), say=self.ui_template)
        self.begin_work(self.ui_text("Dışa aktarma hazırlanıyor…"))
        self._export_estimator = export_progress.Estimator()
        self.worker.progress.connect(self.on_export_progress)
        self.worker.finished.connect(lambda: self.progress.setRange(0, 0))
        self.worker.completed.connect(self.on_exported)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_export_cancelled)
        self.start_worker()

    def on_exported(self, path: str) -> None:
        if self._shutting_down:
            return
        self.finish_work(self.ui_text("Dışa aktarma tamamlandı."))
        QMessageBox.information(self, APP_NAME, self.ui_text("Video başarıyla oluşturuldu:\n{path}", path=path))

    def on_export_cancelled(self) -> None:
        if not self._shutting_down:
            self.finish_work(self.ui_text('Dışa aktarma iptal edildi.'))

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
