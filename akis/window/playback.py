"""Playing and previewing: the proxy, seeking, still frames, sound and the look controls."""
from __future__ import annotations

import math

from akis.media_service import MediaService
from akis.timeline_render import duration_frames
from akis import timeline_service
from akis.preview_controller import PreviewController
from akis.preview_widget import timeline_signature
from akis import i18n

from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from akis import app_support
from akis.app_support import format_time, log


class PlaybackMixin:
    """Playing and previewing: the proxy, seeking, still frames, sound and the look controls."""

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
        self.set_status(self.ui_text('Akıcı önizleme kullanılamadı, kare kare önizlemeye geçildi: {error}', error=message[:120]))

    def update_range_label(self) -> None:
        selected = max(0, self.state.end - self.state.start)
        self.selection_label.setText(f"Seçim: {format_time(selected)}")

    def seek_timeline(self, frame, *, from_clock=False):
        total = duration_frames(self.multitrack)
        self.start_panel.setVisible(not total and not self.state.source)  # gone once there is something to edit
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
            self.set_status(self.ui_text('Önizleme oluşturulamadı: {error}', error=exc))
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
        return timeline_service.canvas_size(self.aspect.currentData(), self.multitrack, MediaService(app_support.ffmpeg_path()))

    def export_canvas_size(self):
        return timeline_service.output_canvas_size(self.aspect.currentData(), self.multitrack,
                                                   MediaService(app_support.ffmpeg_path()), self.export_profile.currentData())

    def sync_timeline_audio(self, force=False):
        if self.play_timer.isActive():
            self.preview_audio_output.setVolume(timeline_service.playback_volume(self.multitrack, self.timeline_frame, self.master_volume))
            self.timeline_audio.sync(self.multitrack, self.timeline_frame, self.state.speed, force, master=self.master_volume)

    def new_preview_player(self):
        """Another player for frame-by-frame playback, so the video's voice and the music sound together."""
        output = QAudioOutput(self)
        player = QMediaPlayer(self)
        player.setAudioOutput(output)
        return player, output

    def change_master_volume(self, value):
        self.master_volume = value / 100
        self.proxy.set_volume(self.master_volume)
        self.sync_timeline_audio()

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
