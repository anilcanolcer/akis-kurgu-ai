"""Editing the timeline: undo history, clip and track operations, cleanup tools."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import math
import os
import tempfile
import subprocess
from pathlib import Path

from akis.timeline_model import CLIP_SPEEDS, Clip, Track
from akis.template_service import TITLE_SECONDS
from akis.media_service import MediaService
from akis import timeline_service
from akis.shape_art import default_tail
from akis import edit_plan
from akis import fillers, speaker_model, speakers, speech_settings
from akis.silence_dialog import SilenceDialog
from akis import clip_fit
from akis.call_worker import CallWorker
from akis import beat_sync, emphasis, retakes, silence_cut

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox
from PySide6.QtCore import Qt, QTimer

from akis import app_support
from akis import i18n
from akis.i18n import decimal
from akis.app_support import APP_NAME, UNDO_LIMIT, format_time, log


STILL_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
MEDIA_FILE_FILTER = ('Medya dosyaları (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp '
                     '*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma);;Tüm dosyalar (*.*)')
AUDIO_FILE_FILTER = ('Ses dosyaları (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma);;'
                     'Tüm dosyalar (*.*)')


class TimelineEditMixin:
    """Editing the timeline: undo history, clip and track operations, cleanup tools."""

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
            selected = self.multitrack_view.selected
            self.show_timeline(copy.deepcopy(snapshot['timeline']), frame=self.timeline_frame)
            self.reselect_clip(selected)

    def reselect_clip(self, selected) -> None:
        """Select the clip with the id of `selected` (track, id) again when it is still on the timeline.

        Undo and redo rebuild the timeline, which clears the selection; keeping it lets the user go on
        with the same clip (volume, speed, split) as CapCut does.
        """
        if not selected:
            return
        for index, track in enumerate(self.multitrack.tracks):
            if any(clip.id == selected[1] for clip in track.clips):
                self.multitrack_view.selected = (index, selected[1])
                self.multitrack_view.selected_track = index
                self.multitrack_view.update()
                return

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._drag_before = None
        step = self._undo_stack.pop()
        self._redo_stack.append(step)
        self.apply_edit_snapshot(step['before'], self.snapshot_changes(step['before'], step['after']))
        self.clear_clean_autosave()
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
        self.clear_clean_autosave()
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

    def title_layer(self):
        """(track, clip) of the title made with the Edit tab's title field, or None."""
        for track in self.multitrack.tracks:
            for clip in track.clips:
                if track.kind == 'text' and clip.style.get('title_layer'):
                    return track, clip
        return None

    def sync_title_field(self) -> None:
        found = self.title_layer()
        text = found[1].text if found else ''
        if self.overlay.text() != text:
            self.overlay.setText(text)

    def set_title_layer(self) -> None:
        """Add, change or remove the title at the start of the video (a text clip; undo takes it back)."""
        text = self.overlay.text().strip()
        found = self.title_layer()
        if (found[1].text if found else '') == text:
            return
        if not any(clip.source for track in self.multitrack.tracks for clip in track.clips):
            self.overlay.clear()
            self.set_status(self.ui_text('Önce bir video ekleyin ve yüklenmesini bekleyin.'))
            return
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        length = max(1, round(TITLE_SECONDS * fps))
        with self.history_step():
            if found and text:
                found[1].text = text
                message = 'Başlık güncellendi.'
            elif found:
                found[0].clips.remove(found[1])
                message = 'Başlık kaldırıldı.'
            else:
                # The first text track that is free at the start (not the captions); otherwise a new one.
                track = next((t for t in self.multitrack.tracks if t.kind == 'text' and t.name != edit_plan.CAPTION_TRACK
                              and all(c.start >= length for c in t.clips)), None)
                if track is None:
                    track = Track('text', 'Text')
                    self.multitrack.tracks.append(track)
                track.add(Clip('', 0, length, text=text, style={'title_layer': True}))
                message = 'Başlık videonun başına eklendi.'
        self.refresh_timeline_view()
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text(message))

    def refresh_timeline_view(self) -> None:
        """Size the track view and its scroll area for the current number of tracks."""
        self.sync_title_field()
        tracks = len(self.multitrack.tracks)
        self.multitrack_view.setMinimumHeight(max(210, 40 + 43 * tracks))
        self.track_scroll.setMinimumHeight(max(160, min(360, 46 + 43 * tracks)))

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
        kind, ok = QInputDialog.getItem(self, self.ui_text('İz ekle'), self.ui_text('Tür'), ['video', 'audio', 'text', 'overlay'], 0, False)
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
                self, APP_NAME, self.ui_text('“{name}” izi ve içindeki {count} klip silinsin mi? Ctrl+Z ile geri alabilirsiniz.',
                                             name=i18n.track_label(track.name, self.ui_language()),
                                             count=len(track.clips)),
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
            keys = list(self.MARK_COLOURS) + ['Sil']
            names = [self.ui_text(name) for name in keys]
            current = next((i for i, n in enumerate(self.MARK_COLOURS) if self.MARK_COLOURS[n] == clip.style.get('color')), 0)
            choice, ok = QInputDialog.getItem(self, self.ui_text('İşareti düzenle'), self.ui_text('Renk seçin veya işareti silin'), names, current, False)
            if not ok:
                return
            with self.history_step():
                choice = keys[names.index(choice)]
                if choice in self.MARK_COLOURS:
                    clip.style['color'] = self.MARK_COLOURS[choice]
                else:
                    track.clips.remove(clip)
                    self.multitrack_view.selected = None
        else:
            value, ok = QInputDialog.getMultiLineText(self, self.ui_text('Metni düzenle'), self.ui_text('Başlık / altyazı'), clip.text)
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
            self.set_status(self.ui_text('Önizleme boyutu belirlenemedi: {error}', error=exc))
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
            self.set_status(self.ui_text('Burada düzenlenecek bir yazı veya işaret yok. Çift tıklamayı bir yazının ya da işaretin üstünde deneyin.'))

    @staticmethod
    def _still_cache_path(source: Path) -> Path:
        stat = source.stat()
        identity = f'{source.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}'
        digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]
        folder = Path(app_support.app_data_dir()) / 'stills'
        # Leave ample room for the digest and extension on Windows, including emoji (two UTF-16 units).
        return folder / f'{source.stem[:100]}-{digest}.mp4'

    def convert_still_to_clip(self, media, path: str) -> str:
        """Persist an image as a five-second video clip in app data so projects can reopen it."""
        source = Path(path)
        if not source.is_file():
            raise ValueError('Görsel dosyası bulunamadı.')
        folder = Path(app_support.app_data_dir()) / 'stills'
        folder.mkdir(parents=True, exist_ok=True)
        base = self._still_cache_path(source)

        # A cached output is safe to reuse only when it still probes as a five-second video.
        candidate, number = base, 2
        while candidate.exists():
            try:
                duration = media.duration(str(candidate))
                media.dimensions(str(candidate))
                if abs(duration - app_support.STILL_CLIP_SECONDS) <= 1 / 30:
                    return str(candidate)
            except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
                pass
            candidate = base.with_name(f'{base.stem}-{number}.mp4')
            number += 1

        fd, partial_name = tempfile.mkstemp(prefix='akis_still_', suffix='.mp4', dir=str(folder))
        os.close(fd)
        partial = Path(partial_name)
        try:
            result = media.run(
                ['-y', '-loop', '1', '-framerate', '30', '-i', str(source), '-t', str(app_support.STILL_CLIP_SECONDS),
                 '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p', '-r', '30', '-c:v', 'libx264',
                 '-pix_fmt', 'yuv420p', '-an', str(partial)], text=True)
            if result.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
                detail = (getattr(result, 'stderr', '') or getattr(result, 'stdout', '') or '').strip()
                raise RuntimeError(detail or 'FFmpeg could not create the clip.')
            # Publish without replacing any pre-existing file, even if another process races this import.
            while True:
                try:
                    os.link(partial, candidate)
                    break
                except FileExistsError:
                    candidate = base.with_name(f'{base.stem}-{number}.mp4')
                    number += 1
            return str(candidate)
        finally:
            # The unique temporary path belongs only to this conversion; never clean a user's existing file.
            partial.unlink(missing_ok=True)

    def _import_media_path(self, path: str, *, selected_track=None, forced_kind=None):
        original_path = str(path)
        try:
            media = MediaService(app_support.ffmpeg_path())
        except (RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Medya eklenemedi: {error}', error=exc))
            return False
        converted_still = Path(path).suffix.lower() in STILL_IMAGE_EXTS
        if converted_still:
            try:
                path = self.convert_still_to_clip(media, path)
            except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
                QMessageBox.warning(self, APP_NAME, self.ui_text('Görsel klibe dönüştürülemedi: {error}', error=exc))
                return False

        try:
            track = self.multitrack.tracks[selected_track] if selected_track is not None and \
                0 <= selected_track < len(self.multitrack.tracks) else None
            detected_kind = timeline_service.infer_media_kind(media, path)
            kind = forced_kind or ('overlay' if detected_kind == 'video' and track is not None and track.kind == 'overlay'
                                   else detected_kind)
            compatible = ('video', 'overlay') if kind in ('video', 'overlay') else ('audio',)
            preferred_track = selected_track if track is not None and track.kind in compatible else None
            seconds = media.duration(path)
            timeline_service.validate_track_media(media, kind, path)
            with self.history_step():
                track_index, clip = timeline_service.append_media_to_kind(
                    self.multitrack, kind, path, seconds, preferred_track=preferred_track)
                if converted_still:
                    # The clip plays the converted video in app data; the photo itself is what the user
                    # added. Kept on the clip so the project shows its name, carries it when the project
                    # folder moves (relative_media) and rebuilds the clip on another computer.
                    clip.style[timeline_service.STILL_IMAGE] = original_path
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Medya eklenemedi: {error}', error=exc))
            return False

        self.media_bin.add(original_path)  # the photo, not its converted copy: adding it again reuses the copy
        self.refresh_media_bin()
        self.multitrack_view.refresh_waveforms()
        self.update_timeline_scroll()
        if kind == 'audio':
            # Make the imported music clip ready for the Clip volume action and its tooltip guidance.
            self.multitrack_view.selected = (track_index, clip.id)
            self.multitrack_view.selected_track = track_index
            self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)
        if kind == 'audio':
            self.set_status(self.ui_text('Müzik zaman çizelgesine eklendi.'))
        elif converted_still:
            self.set_status(self.ui_text('Fotoğraf 5 saniyelik klip olarak eklendi.'))
        else:
            self.set_status(self.ui_text('Medya zaman çizelgesine eklendi.'))
        return True

    def add_timeline_media(self):
        index = self.multitrack_view.selected_track
        track = self.multitrack.tracks[index] if index is not None and 0 <= index < len(self.multitrack.tracks) else None
        if track is not None and track.kind not in ('video', 'audio', 'overlay'):
            self.set_status(self.ui_text('Bu sürümde medya yalnızca video/ses izine eklenir.'))
            return
        path, _ = QFileDialog.getOpenFileName(self, self.ui_text('Medya seç'), '', self.ui_text(MEDIA_FILE_FILTER))
        if not path:
            return
        self._import_media_path(path, selected_track=index)

    def add_timeline_music(self):
        path, _ = QFileDialog.getOpenFileName(self, self.ui_text('Müzik seç'), '', self.ui_text(AUDIO_FILE_FILTER))
        if not path:
            return
        selected = self.multitrack_view.selected_track
        selected_track = selected if selected is not None and 0 <= selected < len(self.multitrack.tracks) and \
            self.multitrack.tracks[selected].kind == 'audio' else None
        self._import_media_path(path, selected_track=selected_track, forced_kind='audio')

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

    def trim_left(self):
        self._trim_to_playhead('left')

    def trim_right(self):
        self._trim_to_playhead('right')

    def _trim_to_playhead(self, side):
        """CapCut's Q / W: drop the selected clip's part before or after the playhead, one undo step."""
        track, clip = self.selected_clip()
        if not clip:
            self.set_status(self.ui_text('Önce kırpılacak klibi seçin.'))
            return
        try:
            with self.history_step():
                timeline_service.trim_to_playhead(self.multitrack, self.multitrack_view.selected,
                                                  self.multitrack_view.playhead, side)
        except ValueError:
            self.set_status(self.ui_text('Kırpılamadı: oynatma çizgisini seçili klibin içine getirin.'))
            return
        self.update_timeline_scroll()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('Klibin oynatma çizgisinden önceki kısmı atıldı.') if side == 'left'
                        else self.ui_text('Klibin oynatma çizgisinden sonraki kısmı atıldı.'))

    def on_range_changed(self):
        chosen = self.multitrack_view.range
        if hasattr(self, 'range_button'):
            self.range_button.setEnabled(bool(chosen))
        if chosen:
            fps = self.multitrack.fps_num / self.multitrack.fps_den
            self.set_status(self.ui_text('Seçili aralık: {start} – {end} ({length} sn). Silmek için Delete ya da “Aralığı sil”.',
                                         start=format_time(chosen[0] / fps), end=format_time(chosen[1] / fps),
                                         length=decimal(f'{(chosen[1] - chosen[0]) / fps:.1f}', self.ui_text)))

    def delete_range(self):
        """Cut the chosen time range out of every track and close the gap (one undo step)."""
        chosen = self.multitrack_view.range
        if not chosen:
            self.set_status(self.ui_text('Önce zaman çizelgesinde boş bir yerden sürükleyerek bir aralık seçin.'))
            return
        try:
            with self.history_step():
                frames = timeline_service.delete_range(self.multitrack, *chosen)
        except ValueError as exc:
            self.set_status(self.ui_text('Aralık silinemedi: {error}', error=exc))
            return
        self.multitrack_view.selected = None
        self.multitrack_view.set_range(None)
        self.update_timeline_scroll()
        self.seek_timeline(min(self.timeline_frame, chosen[0]))
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        self.set_status(self.ui_text('{seconds} sn kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     seconds=decimal(f'{frames / fps:.1f}', self.ui_text)))

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
            self.set_status(self.ui_text('Klip silinemedi: {error}', error=exc))
            self.multitrack_view.update()
            return
        self.multitrack_view.selected = None
        self.update_timeline_scroll()
        self.seek_timeline(self.timeline_frame)

    def set_clip_volume(self):
        track, clip = self.selected_clip()
        if not clip or track.kind not in ('audio', 'video'):
            self.set_status(self.ui_text('Bir ses veya video klibi seçin.'))
            return
        value, ok = QInputDialog.getInt(self, self.ui_text('Klip sesi'), self.ui_text('Ses düzeyi (%)'), round(clip.volume * 100), 0, 100)
        if ok:
            with self.history_step():
                timeline_service.set_clip_volume(self.multitrack, self.multitrack_view.selected, value / 100)
            # A proxy is a pre-mixed render of the old volume. Seeking runs the usual edit refresh,
            # which stops that proxy when its signature no longer matches the timeline.
            self.seek_timeline(self.timeline_frame)
            self.set_status(self.ui_text('Klip sesi: %{value}', value=value))

    def set_clip_speed(self):
        """Play the selected clip faster or slower (slow motion, time-lapse); one undo step."""
        track, clip = self.selected_clip()
        if not clip or not clip.source or track.kind not in ('audio', 'video', 'overlay'):
            self.set_status(self.ui_text('Bir ses veya video klibi seçin.'))
            return
        labels = [f'{value:g}×' for value in CLIP_SPEEDS]
        current = min(range(len(CLIP_SPEEDS)), key=lambda i: abs(CLIP_SPEEDS[i] - clip.speed))
        chosen, ok = QInputDialog.getItem(self, self.ui_text('Klip hızı'),
                                          self.ui_text('Bu klip hangi hızda oynasın? Uzunluğu buna göre değişir; '
                                                       'izdeki sonraki klipler kayar.'), labels, current, False)
        if not ok:
            return
        speed = CLIP_SPEEDS[labels.index(chosen)]
        try:
            with self.history_step():
                timeline_service.set_clip_speed(self.multitrack, self.multitrack_view.selected, speed)
        except ValueError:
            self.set_status(self.ui_text('Bu hız uygulanamadı: klip kaynağın sonunu aşıyor.'))
            return
        self.refresh_timeline_view()
        self.seek_timeline(self.timeline_frame)
        self.sync_timeline_audio(force=True)
        self.set_status(self.ui_text('Klip hızı: {value}', value=chosen))

    def set_clip_fit(self):
        """Fit the selected video clip inside the canvas or let it fill the canvas (cropped), one undo step."""
        track, clip = self.selected_clip()
        if not clip or track.kind not in ('video', 'overlay'):
            self.set_status(self.ui_text('Önce bir video klibi seçin.'))
            return
        labels = [self.ui_text(label) for label, _, _ in clip_fit.CHOICES]
        chosen, ok = QInputDialog.getItem(self, self.ui_text('Kadraj'), self.ui_text('Klip tuvale nasıl yerleşsin?'), labels,
                                          clip_fit.choice_index(clip.style), False)
        if not ok:
            return
        _, fit, focus = clip_fit.CHOICES[labels.index(chosen)]
        with self.history_step():
            clip_fit.apply(clip, fit, focus)
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('Kadraj: {choice}', choice=chosen))

    def sound_check_paths(self):
        """Files whose loudness tells a separate microphone track apart from music (empty without one)."""
        return edit_plan.sound_paths(self.multitrack)

    def local_cut(self, sources, segments):
        """The timeline with a local tool's segments applied; a sound clip recorded together with the main
        picture (a separate microphone track) is cut with it instead of being left out of sync."""
        executable = app_support.ffmpeg_path()
        follow = set()
        if self.sound_check_paths():
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                follow = edit_plan.synced_sound(self.multitrack, lambda source: silence_cut.cached_levels(executable, source))
            finally:
                QApplication.restoreOverrideCursor()
        return edit_plan.apply_plan(self.multitrack, sources, {'segments': segments}, follow=follow)

    def remove_silences(self) -> None:
        """Cut the pauses out of the main cut: measured locally, previewed in a dialog, one undo step."""
        if not self.can_start_work() or not self.ensure_video():
            return
        try:
            sources = [{'path': path, 'duration': seconds} for path, seconds in self.edit_sources()]
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Video okunamadı: {error}', error=exc))
            return
        segments = edit_plan.current_segments(self.multitrack, sources, keep=True)
        if not segments:
            QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde kesilecek video yok.'))
            return
        dialog = SilenceDialog(self, executable=app_support.ffmpeg_path(), sources=sources, segments=segments,
                               language=self.ui_language())
        if not dialog.exec() or not dialog.cuts:  # exec() is 0 when the dialog is dismissed
            return
        try:
            timeline = self.local_cut(sources, dialog.segments)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Sessizlikler kesilemedi: {error}', error=exc))
            return
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(self.ui_text('{count} sessiz yer kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=len(dialog.cuts)))

    def remove_retakes(self) -> None:
        """Keep only the last try of sentences said again, using the local transcript (akis.retakes)."""
        if not self.can_start_work() or not self.ensure_video():
            return
        if not self.caption_segments or not self.caption_source:
            QMessageBox.information(self, APP_NAME, self.ui_text(
                'Önce “Konuşma metni ve seslendirme” bölümünden yerel konuşma metnini çıkarın; '
                'tekrarlar bu metinden bulunur.'))
            return
        cuts = retakes.find(self.caption_segments)
        if not cuts:
            QMessageBox.information(self, APP_NAME, self.ui_text('Tekrar çekim bulunamadı.'))
            return
        try:
            sources = [{'path': path, 'duration': seconds} for path, seconds in self.edit_sources()]
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Video okunamadı: {error}', error=exc))
            return
        index = next((i for i, source in enumerate(sources) if source['path'] == self.caption_source), None)
        segments = edit_plan.current_segments(self.multitrack, sources, keep=True)
        if index is None or not any(segment['source'] == index for segment in segments):
            QMessageBox.information(self, APP_NAME, self.ui_text('Konuşma metninin videosu zaman çizelgesinde yok.'))
            return
        new, removed = silence_cut.keep_segments(segments, {index: [(a, b) for a, b, _, _ in cuts]}, margin=0,
                                                 whole=True)
        if not removed:
            QMessageBox.information(self, APP_NAME, self.ui_text('Tekrarlar zaten kesilmiş.'))
            return
        if not new:
            QMessageBox.information(self, APP_NAME, self.ui_text('Tekrarlar kesilince videoda hiçbir şey kalmıyor.'))
            return
        if QMessageBox.question(self, APP_NAME, retakes.summary(cuts, self.ui_template),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        try:
            timeline = self.local_cut(sources, new)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Tekrarlar kesilemedi: {error}', error=exc))
            return
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(self.ui_text('{count} tekrar çekim kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=len(cuts)))

    def remove_fillers(self) -> None:
        """Cut "ııı", "eee", "hmm" and pause-words ("şey", "yani") out of the main video (akis.fillers).

        A separate local recognition run writes the fillers down (captions keep their clean transcript);
        it runs off the window's thread, then the cuts are shown for confirmation and applied in one step."""
        if not self.can_start_work() or not self.ensure_video():
            return
        main = next((track for track in self.multitrack.tracks if track.kind == 'video'), None)
        sources = sorted({clip.source for clip in (main.clips if main else []) if clip.source})
        if not sources:
            QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde video yok.'))
            return
        model, download = self.local_model.currentText(), self.download_model.isChecked()
        vocabulary = ' '.join(filter(None, [fillers.PROMPT, speech_settings.vocabulary(None)]))
        sound_paths, executable = self.sound_check_paths(), app_support.ffmpeg_path()

        def listen():
            from akis.ai_service import local_transcribe

            def heard(source):
                # The smallest model writes a hesitation as a too-short "E": use a larger one already on
                # this computer when there is one (akis.fillers.MODELS), else the one chosen for captions.
                for name in fillers.models_to_try(model):
                    try:
                        return local_transcribe(source, name, download=download and name == model, timed=True,
                                                vocabulary=vocabulary)
                    except RuntimeError:
                        if name == model:
                            raise
                return []
            found = {source: fillers.find(fillers.words_of(heard(source))) for source in sources}
            for path in sound_paths:   # read now, off the window's thread, for the microphone check
                silence_cut.cached_levels(executable, path)
            return found
        self.run_analysis(self.ui_text('Dolgu sözcükleri aranıyor (yerel konuşma tanıma)…'), listen, self.finish_fillers)

    def separate_speakers(self) -> None:
        """Find who speaks when in the main video (akis.speakers); mark the changes or keep one speaker."""
        if not self.can_start_work() or not self.ensure_video():
            return
        main = next((track for track in self.multitrack.tracks if track.kind == 'video'), None)
        source = next((clip.source for clip in (main.clips if main else []) if clip.source), None)
        if not source:
            QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde video yok.'))
            return
        model, download = self.local_model.currentText(), self.download_model.isChecked()
        known = fillers.words_of(self.caption_segments) if self.caption_source == source else []
        executable = app_support.ffmpeg_path()

        folder = app_support.app_data_dir()
        sound_paths = self.sound_check_paths()

        def listen():
            from akis.ai_service import local_transcribe
            from akis.media_service import MediaService
            words = known or fillers.words_of(local_transcribe(source, model, download=download, timed=True))
            embedder = None
            try:   # the speaker model tells similar voices apart; downloaded once (26.5 MB)
                embedder = speaker_model.Embedder(speaker_model.download(folder))
            except Exception as exc:     # offline or blocked: pitch still separates clearly different voices
                log.warning('Konuşmacı modeli kullanılamadı, perdeyle ayrılıyor: %s', exc)
            found = speakers.find(speakers.decode(MediaService(executable), source), words, embedder)
            for path in sound_paths:   # read now, off the window's thread, for the microphone check
                silence_cut.cached_levels(executable, path)
            return source, found, embedder is not None
        text = 'Konuşmacılar ayırt ediliyor…' if speaker_model.available(folder) else \
            'Konuşmacılar ayırt ediliyor (ilk kullanımda {size} MB ses modeli indirilir)…'
        self.run_analysis(self.ui_text(text, size=decimal(str(speaker_model.SIZE_MB), self.ui_text)), listen, self.finish_speakers)

    def finish_speakers(self, result) -> None:
        source, found, with_model = result
        totals = speakers.summary(found)
        if len(totals) < 2:
            QMessageBox.information(self, APP_NAME, self.ui_text('Tek konuşmacı bulundu.') if with_model else self.ui_text(
                'Tek konuşmacı bulundu. (Ses modeli indirilemediği için sesler perdeden ayrıldı; '
                'iki erkek sesi gibi benzer sesler böyle ayırt edilemez.)'))
            return
        lines = [self.ui_text('{count} konuşmacı bulundu:', count=len(totals)), '']
        for speaker, (seconds, sample) in sorted(totals.items()):
            short = sample if len(sample) <= 50 else sample[:49].rstrip() + '…'
            lines.append(self.ui_text('Konuşmacı {number}: {seconds} sn — “{sample}”', number=speaker + 1,
                                      seconds=round(seconds), sample=short))
        box = QMessageBox(QMessageBox.Icon.Question, APP_NAME, '\n'.join(lines), parent=self)
        mark = box.addButton(self.ui_text('Değişimleri işaretle'), QMessageBox.ButtonRole.AcceptRole)
        keeps = {box.addButton(self.ui_text('Yalnız Konuşmacı {number}', number=speaker + 1),
                               QMessageBox.ButtonRole.ActionRole): speaker for speaker in sorted(totals)}
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        chosen = box.clickedButton()
        main = next((track for track in self.multitrack.tracks if track.kind == 'video'), None)
        clips = [clip for clip in (main.clips if main else []) if clip.source == source]
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        if chosen is mark:
            with self.history_step():
                self.multitrack.markers = [m for m in self.multitrack.markers
                                           if not str(m.get('label', '')).startswith('Konuşmacı ')]
                added = speakers.markers(found, clips, fps)
                self.multitrack.markers += added
            self.multitrack_view.update()
            self.set_status(self.ui_text('{count} konuşmacı değişimi işaretlendi.', count=len(added)))
        elif chosen in keeps:
            keep = keeps[chosen]
            self.keep_only_speaker(source, [(a, b) for a, b, speaker, _ in found if speaker != keep], keep)

    def keep_only_speaker(self, source, spans, keep) -> None:
        try:
            sources = [{'path': path, 'duration': seconds} for path, seconds in self.edit_sources()]
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Video okunamadı: {error}', error=exc))
            return
        index = next((i for i, item in enumerate(sources) if item['path'] == source), None)
        segments = edit_plan.current_segments(self.multitrack, sources, keep=True)
        # whole=True: a clip where only the other speakers talk goes entirely.
        new, removed = silence_cut.keep_segments(segments, {index: spans}, margin=0, min_keep=0.3, whole=True)
        if index is None or not removed:
            QMessageBox.information(self, APP_NAME, self.ui_text('Kesilecek bir yer kalmadı.'))
            return
        if not new:
            QMessageBox.information(self, APP_NAME, self.ui_text('Ana videoda bu konuşmacının konuştuğu bir yer yok.'))
            return
        try:
            timeline = self.local_cut(sources, new)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(self.ui_text('Yalnız Konuşmacı {number} kaldı. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     number=keep + 1))

    def finish_fillers(self, found) -> None:
        cuts = [cut for source_cuts in found.values() for cut in source_cuts]
        if not cuts:
            QMessageBox.information(self, APP_NAME, self.ui_text('Dolgu sözcüğü bulunamadı.'))
            return
        try:
            sources = [{'path': path, 'duration': seconds} for path, seconds in self.edit_sources()]
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Video okunamadı: {error}', error=exc))
            return
        index = {source['path']: i for i, source in enumerate(sources)}
        segments = edit_plan.current_segments(self.multitrack, sources, keep=True)
        wanted = {index[path]: [(a, b) for a, b, _ in source_cuts] for path, source_cuts in found.items()
                  if path in index and source_cuts}
        new, removed = silence_cut.keep_segments(segments, wanted, margin=0, min_keep=0.05, whole=True)
        if removed and not new:
            QMessageBox.information(self, APP_NAME, self.ui_text('Dolgu sözcükleri kesilince videoda hiçbir şey kalmıyor.'))
            return
        if not removed:
            QMessageBox.information(self, APP_NAME, self.ui_text('Dolgu sözcükleri zaten kesilmiş.'))
            return
        if QMessageBox.question(self, APP_NAME, fillers.summary(cuts, self.ui_template),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        try:
            timeline = self.local_cut(sources, new)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Dolgu sözcükleri kesilemedi: {error}', error=exc))
            return
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(self.ui_text('{count} dolgu sözcüğü kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=len(removed)))

    def snap_cuts_to_beat(self) -> None:
        """Move each cut of the main video to the nearest beat of the music (akis.beat_sync)."""
        if not self.can_start_work() or not self.ensure_video():
            return
        music = beat_sync.music_clip(self.multitrack)
        if music is None:
            QMessageBox.information(self, APP_NAME, self.ui_text('Önce bir ses izine müzik ekleyin; kesimler onun vuruşuna oturtulur.'))
            return
        try:
            sources = [{'path': path, 'duration': seconds} for path, seconds in self.edit_sources()]
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Video okunamadı: {error}', error=exc))
            return
        segments = edit_plan.current_segments(self.multitrack, sources, keep=True)
        if len(segments) < 2:
            QMessageBox.information(self, APP_NAME, self.ui_text('Ritme oturtulacak kesim yok; önce videoyu bölün ya da birkaç klip ekleyin.'))
            return
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        executable = app_support.ffmpeg_path()
        sound_paths = self.sound_check_paths()
        self.run_analysis(self.ui_text('Müziğin ritmi çözümleniyor…'),
                          # The music's own stretch of source: at 1.5× its clip plays 1.5 × length of it.
                          lambda: ([silence_cut.cached_levels(executable, path) for path in sound_paths],
                                   beat_sync.beats(beat_sync.read_onsets(
                                       executable, music.source, (music.source_in + music.source_phase) / fps,
                                       music.length * music.speed / fps)))[1],
                          lambda beats: self.finish_beat_snap(beats, music, sources, segments))

    def finish_beat_snap(self, beats, music, sources, segments) -> None:
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        found = beat_sync.timeline_beats(beats, music, fps)
        if not found:
            QMessageBox.information(self, APP_NAME, self.ui_text('Müzikte belirgin bir ritim bulunamadı.'))
            return
        new, moved = beat_sync.snap_segments(segments, found, {i: s['duration'] for i, s in enumerate(sources)})
        if not moved:
            QMessageBox.information(self, APP_NAME, self.ui_text('Kesimler zaten vuruşta ya da yakınlarında vuruş yok.'))
            return
        try:
            timeline = self.local_cut(sources, new)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Kesimler ritme oturtulamadı: {error}', error=exc))
            return
        # The music sets the beat: it stays exactly where it was, whatever happened to the picture.
        # A microphone track on another sound track was cut with the picture and stays that way.
        for index, track in enumerate(self.multitrack.tracks):
            if (track.kind == 'audio' and any(clip.id == music.id for clip in track.clips)
                    and index < len(timeline.tracks) and timeline.tracks[index].name == track.name):
                timeline.tracks[index].clips = copy.deepcopy(track.clips)
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(self.ui_text('{count} kesim müziğin vuruşuna oturtuldu. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=moved))

    def punch_in_on_emphasis(self) -> None:
        """Zoom in briefly at large source-audio loudness peaks; music peaks may also trigger it."""
        if not self.can_start_work() or not self.ensure_video():
            return
        if any('punch' in clip.style for track in self.multitrack.tracks for clip in track.clips):
            answer = QMessageBox.question(self, APP_NAME, self.ui_text('Ses düzeyi artışlarında yakınlaştırmalar var. Kaldırılsın mı?'),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.Yes)
            if answer == QMessageBox.StandardButton.Yes:
                with self.history_step():
                    count = emphasis.clear(self.multitrack)
                self.seek_timeline(self.timeline_frame)
                self.set_status(self.ui_text('{count} ses düzeyi artışı yakınlaştırması kaldırıldı.', count=count))
            return
        main = next((track for track in self.multitrack.tracks if track.kind == 'video'), None)
        sources = sorted({clip.source for clip in (main.clips if main else []) if clip.source})
        if not sources:
            QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde video yok.'))
            return
        executable = app_support.ffmpeg_path()
        self.run_analysis(self.ui_text('Kaynak sesindeki ani ses düzeyi artışları aranıyor…'),
                          lambda: {source: emphasis.find_moments(silence_cut.measure(executable, source)) for source in sources},
                          self.finish_punch_in)

    def finish_punch_in(self, moments) -> None:
        with self.history_step():
            placed = emphasis.apply(self.multitrack, moments)
        if not placed:
            QMessageBox.information(self, APP_NAME, self.ui_text('Belirgin ses düzeyi artışı bulunamadı.'))
            return
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('{count} ses düzeyi artışı anında yakınlaştırma eklendi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=placed))

    def run_analysis(self, text, function, done) -> None:
        """Run a slow, self-contained step off the window's thread; `done(result)` follows on this thread.

        The window stays usable meanwhile; other work waits, as for any running task."""
        self.worker = CallWorker(function)
        self.begin_work(text)

        result = {'value': None, 'received': False, 'error': None}

        def completed(value):
            result['value'], result['received'] = value, True

        def failed(message):
            result['error'] = message

        def deliver_result():
            if self._shutting_down:
                return
            if result['error'] is not None:
                self.on_worker_error(result['error'])
                return
            if not result['received']:
                self.on_worker_error(self.ui_text('Analiz işlemi sonuç vermeden kapandı.'))
                return
            self.finish_work('')
            done(result['value'])

        def thread_finished():
            # Result callbacks can open nested dialogs or start another QThread; wait until this one
            # has actually exited, then run after MainWindow.worker_finished clears its reference.
            QTimer.singleShot(0, deliver_result)

        self.worker.completed.connect(completed)
        self.worker.failed.connect(failed)
        self.worker.finished.connect(thread_finished)
        self.start_worker()
