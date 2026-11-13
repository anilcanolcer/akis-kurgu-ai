"""Editing the timeline: undo history, clip and track operations, cleanup tools."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import math

from akis.timeline_model import CLIP_SPEEDS, Track
from akis.media_service import MediaService
from akis import timeline_service
from akis.shape_art import default_tail
from akis import edit_plan
from akis.silence_dialog import SilenceDialog
from akis import clip_fit
from akis.call_worker import CallWorker
from akis import beat_sync, emphasis, retakes, silence_cut

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from akis import app_support
from akis.app_support import APP_NAME, UNDO_LIMIT


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

    def refresh_timeline_view(self) -> None:
        """Size the track view and its scroll area for the current number of tracks."""
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

    def add_timeline_media(self):
        index = self.multitrack_view.selected_track
        track = self.multitrack.tracks[index] if index is not None and index < len(self.multitrack.tracks) else None
        if track is None:
            self.set_status(self.ui_text('Önce hedef izi seçin.'))
            return
        if track.kind not in ('video', 'audio', 'overlay'):
            self.set_status(self.ui_text('Bu sürümde medya yalnızca video/ses izine eklenir.'))
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Medya seç', '', 'Media (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mp3 *.wav *.m4a)')
        if not path:
            return
        # Probe without decoding the file or relying on an additional ffprobe binary.
        try:
            media = MediaService(app_support.ffmpeg_path())
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
        value, ok = QInputDialog.getInt(self, 'Klip sesi / Clip volume', 'Ses / Volume (%)', round(clip.volume * 100), 0, 100)
        if ok:
            with self.history_step():
                timeline_service.set_clip_volume(self.multitrack, self.multitrack_view.selected, value / 100)
            self.sync_timeline_audio(force=True)
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
            QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde kesilecek video yok.'))
            return
        dialog = SilenceDialog(self, executable=app_support.ffmpeg_path(), sources=sources, segments=segments,
                               language=self.ui_language())
        if not dialog.exec() or not dialog.cuts:  # exec() is 0 when the dialog is dismissed
            return
        try:
            timeline = edit_plan.apply_plan(self.multitrack, sources, {'segments': dialog.segments})
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
            QMessageBox.warning(self, APP_NAME, f'Video okunamadı: {exc}')
            return
        index = next((i for i, source in enumerate(sources) if source['path'] == self.caption_source), None)
        segments = edit_plan.current_segments(self.multitrack, sources)
        if index is None or not any(segment['source'] == index for segment in segments):
            QMessageBox.information(self, APP_NAME, self.ui_text('Konuşma metninin videosu zaman çizelgesinde yok.'))
            return
        new, removed = silence_cut.keep_segments(segments, {index: [(a, b) for a, b, _, _ in cuts]}, margin=0)
        if not removed:
            QMessageBox.information(self, APP_NAME, self.ui_text('Tekrarlar zaten kesilmiş.'))
            return
        if QMessageBox.question(self, APP_NAME, retakes.summary(cuts, self.ui_template),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        try:
            timeline = edit_plan.apply_plan(self.multitrack, sources, {'segments': new})
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Tekrarlar kesilemedi: {error}', error=exc))
            return
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(self.ui_text('{count} tekrar çekim kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=len(cuts)))

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
            QMessageBox.warning(self, APP_NAME, f'Video okunamadı: {exc}')
            return
        segments = edit_plan.current_segments(self.multitrack, sources)
        if len(segments) < 2:
            QMessageBox.information(self, APP_NAME, self.ui_text('Ritme oturtulacak kesim yok; önce videoyu bölün ya da birkaç klip ekleyin.'))
            return
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        executable = app_support.ffmpeg_path()
        self.run_analysis(self.ui_text('Müziğin ritmi çözümleniyor…'),
                          lambda: beat_sync.beats(beat_sync.read_onsets(executable, music.source, music.source_in / fps,
                                                                       music.length / fps)),
                          lambda beats: self.finish_beat_snap(beats, music, sources, segments))

    def finish_beat_snap(self, beats, music, sources, segments) -> None:
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        found = [music.start / fps + beat for beat in beats]
        if not found:
            QMessageBox.information(self, APP_NAME, self.ui_text('Müzikte belirgin bir ritim bulunamadı.'))
            return
        new, moved = beat_sync.snap_segments(segments, found, {i: s['duration'] for i, s in enumerate(sources)})
        if not moved:
            QMessageBox.information(self, APP_NAME, self.ui_text('Kesimler zaten vuruşta ya da yakınlarında vuruş yok.'))
            return
        try:
            timeline = edit_plan.apply_plan(self.multitrack, sources, {'segments': new})
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, self.ui_text('Kesimler ritme oturtulamadı: {error}', error=exc))
            return
        # The music sets the beat: it stays exactly where it was, whatever happened to the picture.
        for index, track in enumerate(self.multitrack.tracks):
            if track.kind == 'audio' and index < len(timeline.tracks) and timeline.tracks[index].name == track.name:
                timeline.tracks[index].clips = copy.deepcopy(track.clips)
        with self.history_step():
            self.show_timeline(timeline)
        self.set_status(self.ui_text('{count} kesim müziğin vuruşuna oturtuldu. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=moved))

    def punch_in_on_emphasis(self) -> None:
        """Zoom in briefly where the speaker gets louder (akis.emphasis); asks to remove existing ones first."""
        if not self.can_start_work() or not self.ensure_video():
            return
        if any('punch' in clip.style for track in self.multitrack.tracks for clip in track.clips):
            answer = QMessageBox.question(self, APP_NAME, self.ui_text('Videoda vurgu yakınlaştırmaları var. Kaldırılsın mı?'),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.Yes)
            if answer == QMessageBox.StandardButton.Yes:
                with self.history_step():
                    count = emphasis.clear(self.multitrack)
                self.seek_timeline(self.timeline_frame)
                self.set_status(self.ui_text('{count} vurgu yakınlaştırması kaldırıldı.', count=count))
            return
        main = next((track for track in self.multitrack.tracks if track.kind == 'video'), None)
        sources = sorted({clip.source for clip in (main.clips if main else []) if clip.source})
        if not sources:
            QMessageBox.information(self, APP_NAME, self.ui_text('Zaman çizelgesinde video yok.'))
            return
        executable = app_support.ffmpeg_path()
        self.run_analysis(self.ui_text('Konuşmadaki vurgular aranıyor…'),
                          lambda: {source: emphasis.find_moments(silence_cut.measure(executable, source)) for source in sources},
                          self.finish_punch_in)

    def finish_punch_in(self, moments) -> None:
        with self.history_step():
            placed = emphasis.apply(self.multitrack, moments)
        if not placed:
            QMessageBox.information(self, APP_NAME, self.ui_text('Belirgin bir vurgu anı bulunamadı.'))
            return
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('{count} vurgu anında yakınlaştırma eklendi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).',
                                     count=placed))

    def run_analysis(self, text, function, done) -> None:
        """Run a slow, self-contained step off the window's thread; `done(result)` follows on this thread.

        The window stays usable meanwhile; other work waits, as for any running task."""
        self.worker = CallWorker(function)
        self.begin_work(text)

        def finished(result):
            if self._shutting_down:
                return
            self.finish_work('')
            done(result)
        self.worker.completed.connect(finished)
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()
