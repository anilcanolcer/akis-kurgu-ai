"""Media and projects: adding videos, saving, opening, autosave and recovery."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from akis.timeline_model import Timeline
from akis import project_service
from akis.media_service import MediaService
from akis import timeline_service
from PySide6.QtCore import QLockFile

from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox

from akis import app_support
from akis.app_support import APP_NAME, EditState, RECOVERY_DETAIL, RECOVERY_QUESTION, VIDEO_EXTS, log, safe_filename

RECOVERED_SIGNATURE = object()



def project_name(path) -> str:
    """'Hafta sonu.akis.json' -> 'Hafta sonu' ('' for no path)."""
    return Path(path).name.removesuffix('.akis.json').removesuffix('.json') if path else ''

class ProjectMixin:
    """Media and projects: adding videos, saving, opening, autosave and recovery."""

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

    def record_media(self) -> None:
        """Kayıt al: record from a camera, a screen or the microphone (akis.record_dialog) and add it:
        a video like "Video ekle" does, sound only at the playhead on a voiceover track (one undo step)."""
        from akis.record_dialog import RecordDialog
        try:
            executable = app_support.ffmpeg_path()
        except RuntimeError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        dialog = RecordDialog(self, language=self.ui_language(), executable=executable)
        if not dialog.exec() or not dialog.path:
            return
        if dialog.kind == 'video':
            if self.add_video(dialog.path):
                self.set_status(self.ui_text('Kayıt projeye eklendi: {name}', name=Path(dialog.path).name))
            return
        try:
            seconds = MediaService(executable).duration(dialog.path)
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Kayıt eklenemedi: {error}', error=exc))
            return
        with self.history_step():
            self.place_voiceover(dialog.path, self.multitrack_view.playhead, seconds)
        self.media_bin.add(dialog.path)
        self.refresh_media_bin()
        self.refresh_timeline_view()
        self.multitrack_view.refresh_waveforms()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('Ses kaydı oynatma çizgisine eklendi: {name}', name=Path(dialog.path).name))

    def add_video(self, path: str) -> bool:
        if not self.state.source:
            return self.load_video(path)
        file = Path(path)
        if file.suffix.lower() not in VIDEO_EXTS or not file.is_file():
            QMessageBox.warning(self, APP_NAME, 'Desteklenen bir video dosyası seçin.')
            return False
        try:
            seconds = MediaService(app_support.ffmpeg_path()).duration(str(file))
            with self.history_step():
                timeline_service.append_video(self.multitrack, str(file), seconds, self.multitrack_view.selected_track)
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f'Video eklenemedi: {exc}')
            return False
        self.media_bin.add(str(file))
        self.refresh_media_bin()
        self.refresh_timeline_view()
        self.multitrack_view.refresh_waveforms()
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('Video zaman çizelgesine eklendi.'))
        return True

    def load_video(self, path: str) -> bool:
        """Make `path` the main video; returns False (and has told the user why) when it was refused."""
        if not self.can_start_work():  # a running worker would deliver its result into the new video
            return False
        file = Path(path)
        if file.suffix.lower() not in VIDEO_EXTS or not file.is_file():
            QMessageBox.warning(self, APP_NAME, "Desteklenen bir video dosyası seçin.")
            return False
        try:
            media = MediaService(app_support.ffmpeg_path())
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

    def project_document(self) -> dict:
        publish = {'title': self.publish_title.text(),
                   'caption': self.publish_caption.toPlainText(),
                   'hashtags': self.publish_tags.toPlainText()}
        return project_service.make_document(asdict(self.state), self.multitrack, publish,
                                             self.ai_prompt.toPlainText())

    def write_project(self, path: str, snapshot: bool = False) -> project_service.SaveResult:
        return project_service.save_with_snapshot(path, self.project_document(), snapshot)

    def save_project(self) -> None:
        if not self.can_save_project():
            QMessageBox.information(self, APP_NAME, self.ui_text("Kaydetmek için önce bir video veya medya ekleyin."))
            return
        if not self.project_path:
            self.save_project_as()
            return
        self._save_project_to(self.project_path)

    def save_project_as(self) -> None:
        """Choose a new project file without changing the current project unless its save succeeds."""
        if not self.can_save_project():
            QMessageBox.information(self, APP_NAME, self.ui_text("Kaydetmek için önce bir video veya medya ekleyin."))
            return
        default = safe_filename(self.project_title.text()) + ".akis.json"
        initial = self.project_path or str(Path.home() / "Documents" / default)
        chosen, _ = QFileDialog.getSaveFileName(
            self, self.ui_text("Projeyi farklı kaydet"), initial, "Akış projesi (*.akis.json)"
        )
        if not chosen:
            return
        path = project_service.normalize_project_path(chosen)
        if not self.confirm_overwrite(chosen, path):
            return
        self._save_project_to(path)

    def _save_project_to(self, path: str) -> None:
        try:
            result = self.write_project(path, snapshot=True)
        except PermissionError as exc:
            log.exception("Proje kaydedilemedi: %s", path)
            QMessageBox.critical(self, APP_NAME, self.ui_text(
                "Windows bu konuma yazmayı engelledi: {path}. Dosya başka bir uygulamada açıksa kapatın. "
                "Klasöre yazma izniniz yoksa farklı bir konum seçin. Windows Defender'da Denetimli klasör erişimi "
                "bu uygulamayı engelliyorsa, uygulamaya izin verin. Ayrıntı: {error}", path=path, error=exc))
            return
        except (OSError, ValueError) as exc:
            log.exception("Proje kaydedilemedi: %s", path)
            QMessageBox.critical(self, APP_NAME, self.ui_text(
                "Proje kaydedilemedi: {error} (konum: {path})", error=exc, path=path))
            return
        self.project_path = path
        self.project_title.setText(project_name(path))
        self.mark_saved()
        self.discard_autosave()  # the project file now holds everything the autosave did
        snapshot_error = getattr(result, 'snapshot_error', None)
        if snapshot_error is not None:
            log.warning("Proje kaydedildi ancak sürüm anlık görüntüsü oluşturulamadı (%s): %s", path, snapshot_error)
            self.set_status(self.ui_text("Proje kaydedildi; sürüm anlık görüntüsü oluşturulamadı: {error}",
                                         error=snapshot_error))
        else:
            self.set_status(self.ui_text("Proje ve sürüm anlık görüntüsü kaydedildi."))

    def project_signature(self) -> str:
        document = self.project_document()
        document.pop('saved_at', None)
        return hashlib.sha1(json.dumps(document, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    def mark_saved(self) -> None:
        self._saved_signature = self.project_signature()

    def has_content(self) -> bool:
        """There is work to keep: a main video, or any clip on the timeline (media added with ＋ Medya or a
        template's title before any video, text, ...)."""
        return bool(self.state.source) or any(track.clips for track in self.multitrack.tracks)

    def can_save_project(self) -> bool:
        # Removing the last clip is an edit in a saved or recovered project.
        return bool(self.project_path) or self._saved_signature is RECOVERED_SIGNATURE or self.has_content()

    def has_unsaved_changes(self) -> bool:
        return self.can_save_project() and self.project_signature() != self._saved_signature

    def confirm_close(self) -> bool:
        """Ask before work is lost. A hidden window (tests, scripted runs) has nobody to ask."""
        self.clear_clean_autosave()
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
        """Open a project file, offering its unclaimed recovery copy if one exists."""
        autosave = Path(str(Path(path).resolve()) + '.autosave')
        if not autosave.is_file():
            return self.load_project_document(path, path)
        lock = self.lock_project_autosave(str(autosave))
        if lock is None:
            # A live editor still owns these changes. Open the saved project without touching its recovery.
            return self.load_project_document(path, path)
        try:
            return self.open_with_autosave(path, autosave, lock)
        finally:
            if self._project_autosave_lock != (str(autosave), lock):
                lock.unlock()

    def open_with_autosave(self, path: str, autosave: Path, lock: QLockFile) -> bool:
        load_from, recovered = path, False
        # A later manual save may be from another window and need not include these edits.
        if autosave.is_file():
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
        opened = self.load_project_document(load_from, path, recovered=recovered)
        if opened and recovered:
            self._autosave_file = str(autosave)  # ours now: removed on save, discard or clean close
            self._project_autosave_lock = (str(autosave), lock)
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
            self.set_status(self.ui_text('Proje açılamadı; önceki çalışma olduğu gibi korundu.'))
            return False
        if not loaded:  # load_video refused the source and already told the user why
            self.restore_open_snapshot(snapshot)
            return False
        # The previous project was saved or discarded in confirm_close; never delete the file just recovered.
        self.discard_autosave(keep=load_from if recovered else None)
        self.project_path = project_path
        self.project_title.setText(project_name(project_path))  # the project's own name, not its video's
        if recovered:
            self._saved_signature = RECOVERED_SIGNATURE
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
        self.project_title.setText(project_name(project_path) or self.ui_text('Yeni proje'))
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
                (self.apply_captions_button, self.apply_captions_button.isEnabled, self.apply_captions_button.setEnabled)] + [
                (box, box.isChecked, box.setChecked) for box, _name in self.audio_boxes()]

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
                            media = media or MediaService(app_support.ffmpeg_path())
                            known[clip.source] = media.duration(clip.source)
                        except (ValueError, RuntimeError, OSError):
                            log.warning("Medya süresi okunamadı: %s", clip.source)
                frames = round(known[clip.source] * fps)
                if frames > 0:  # never shorter than what the clip already uses
                    clip.source_length = max(frames, clip.source_end)

    def untitled_recovery_path(self, *, separate=False) -> Path:
        """Reserve a startup recovery copy, optionally separate from the usual untitled copy."""
        if self._recovery_lock is not None:
            return self._recovery_lock[0]
        suffix = f'-{uuid4().hex}' if separate else ''
        path = app_support.recovery_dir() / f"recovery-{os.getpid()}{suffix}.akis.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = app_support.recovery_lock(path)
        if not lock.tryLock(0):
            raise OSError(f'Kurtarma dosyası kilitlenemedi: {lock.error()}')
        self._recovery_lock = (path, lock)
        return path

    def autosave_path(self) -> str:
        if self._recovery_lock is not None:
            return str(self._recovery_lock[0])
        return str(Path(self.project_path).resolve()) + '.autosave' if self.project_path else str(self.untitled_recovery_path())

    def lock_project_autosave(self, path: str) -> QLockFile | None:
        if self._project_autosave_lock and self._project_autosave_lock[0] == path:
            return self._project_autosave_lock[1]
        lock = QLockFile(path + '.lock')
        lock.setStaleLockTime(0)  # a long edit is valid; Qt can still detect a dead local process
        return lock if lock.tryLock(0) else None

    def clear_clean_autosave(self) -> None:
        if self._autosave_file and not self.has_unsaved_changes():
            self.discard_autosave()

    def autosave_project(self) -> bool:
        """Write unsaved work where a crash can be recovered from. Returns whether a file was written."""
        if not self.has_unsaved_changes():  # also False when there is nothing to keep
            self.discard_autosave()
            return False
        lock = None
        try:
            path = self.autosave_path()
            if self.project_path and self._recovery_lock is None:
                lock = self.lock_project_autosave(path)
                # Acquiring a stale lock does not confer ownership of the file left behind.
                if lock is None or (self._project_autosave_lock != (path, lock) and Path(path).exists()):
                    if lock is not None:
                        lock.unlock()
                        lock = None
                    path = str(self.untitled_recovery_path(separate=True))
            self.write_project(path, snapshot=False)
        except Exception as exc:
            if lock is not None and self._project_autosave_lock != (path, lock):
                lock.unlock()
            log.exception("Otomatik kayıt başarısız")
            self.set_status(self.ui_text('Otomatik kayıt yapılamadı: {error}', error=exc))
            return False
        if self._autosave_file and self._autosave_file != path:
            self.discard_autosave(keep=path)
        self._autosave_file = path
        if lock is not None:
            self._project_autosave_lock = (path, lock)
        return True

    @staticmethod
    def remove_file(path: Path) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            log.exception("Dosya silinemedi: %s", path)

    def discard_autosave(self, keep: str | None = None) -> None:
        """Remove this window's autosave/recovery file: the work is saved, discarded or the window closes."""
        target = self._autosave_file
        if target and keep is not None and Path(target).resolve() == Path(keep).resolve():
            return
        if target:
            self.remove_file(Path(target))
        self._autosave_file = ""
        if self._project_autosave_lock is not None and self._project_autosave_lock[0] != keep:
            self._project_autosave_lock[1].unlock()
            self._project_autosave_lock = None
        if self._recovery_lock is not None:
            path, lock = self._recovery_lock
            if str(path) != keep:
                if str(path) != target:
                    self.remove_file(path)
                lock.unlock()
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
        for path, lock in app_support.orphan_recovery_files():
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
