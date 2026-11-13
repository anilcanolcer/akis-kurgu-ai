"""Interactive frame-based timeline view."""
from PySide6.QtCore import Qt, Signal
from akis.caption_service import snap_frame
from akis.waveform_service import WaveformWorker, SAMPLE_RATE, WINDOW
from akis.thumbnail_service import ThumbnailWorker
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class MultitrackWidget(QWidget):
    seek = Signal(int)
    changed = Signal()  # after a drag (move/trim) that actually changed a clip, on mouse release
    edit_started = Signal()  # a drag that may change a clip begins; the model is still unchanged
    selection_changed = Signal()
    clip_activated = Signal(int, str)
    viewport_resized = Signal()

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.waveforms = {}
        self.waveform_worker = None
        self.thumbnails = {}            # source -> thumbnail_service.Strip (None while made or when impossible)
        self.thumbnail_worker = None
        self.waveform_executable = None
        self.zoom = 2.0
        self.offset = 0
        self.playhead = 0
        self.selected = None
        self.selected_track = None
        self.drag_mode = None
        self.drag_anchor = 0
        self.original = None
        self.setMinimumHeight(210)
        self.setMouseTracking(True)

    def set_model(self, model):
        self.model = model
        self.selected = None
        self.selected_track = None
        self.updateGeometry()
        self.update()
        self.refresh_waveforms()

    def refresh_waveforms(self):
        self.refresh_thumbnails()  # the film strips are made alongside, from the same calls
        if not self.waveform_executable or self.waveform_worker:
            return
        source = next((c.source for t in self.model.tracks if t.kind in ('audio', 'video')
                       for c in t.clips if c.source and c.source not in self.waveforms), None)
        if source:
            self.waveforms[source] = None
            try:
                executable = self.waveform_executable() if callable(self.waveform_executable) else self.waveform_executable
            except RuntimeError:
                self.waveforms[source] = []
                return
            self.waveform_worker = WaveformWorker(executable, source)
            self.waveform_worker.ready.connect(self._waveform_ready)
            self.waveform_worker.finished.connect(self._waveform_finished)
            self.waveform_worker.start()

    def refresh_thumbnails(self):
        """Make the film strip of the next video on the timeline that has none yet, one at a time."""
        if not self.waveform_executable or self.thumbnail_worker:
            return
        source = next((c.source for t in self.model.tracks if t.kind in ('video', 'overlay')
                       for c in t.clips if c.source and c.source not in self.thumbnails), None)
        if not source:
            return
        self.thumbnails[source] = None
        try:
            executable = self.waveform_executable() if callable(self.waveform_executable) else self.waveform_executable
        except RuntimeError:
            return
        self.thumbnail_worker = ThumbnailWorker(executable, source)
        self.thumbnail_worker.ready.connect(self._thumbnail_ready)
        self.thumbnail_worker.finished.connect(self._thumbnail_finished)
        self.thumbnail_worker.start()

    def _thumbnail_ready(self, source, strip):
        self.thumbnails[source] = strip
        self.update()

    def _thumbnail_finished(self):
        self.thumbnail_worker = None
        self.refresh_thumbnails()

    def _draw_strip(self, painter, strip, clip, x, y, left, right, fps):
        """The video's frames inside its clip box, each tile showing the moment under it."""
        width = strip.tile_width
        if width <= 0:
            return
        painter.save()
        painter.setClipRect(left + 1, y + 4, max(0, right - left - 2), 32)
        painter.setOpacity(0.55)
        first = left - (left - x) % width
        for px in range(first, right, width):
            index = strip.tile_for((clip.source_in + (px - x) / self.zoom) / fps)
            if index is not None:
                painter.drawImage(px, y + 4, strip.image, index * width, 0, width, strip.image.height())
        painter.restore()

    def _waveform_ready(self, source, peaks):
        self.waveforms[source] = peaks
        self.update()

    def _waveform_finished(self):
        self.waveform_worker = None
        self.refresh_waveforms()

    def stop_waveforms(self):
        self.waveform_executable = None
        if self.waveform_worker:
            self.waveform_worker.wait()
            self.waveform_worker = None
        if self.thumbnail_worker:
            self.thumbnail_worker.wait()
            self.thumbnail_worker = None

    def set_offset(self, pixels):
        self.offset = max(0, pixels)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewport_resized.emit()

    def x_for(self, frame):
        return 100 + frame * self.zoom - self.offset

    def frame_for(self, x):
        return max(0, round((x - 100 + self.offset) / self.zoom))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#111218'))
        p.setPen(QColor('#9a9daf'))
        p.drawText(8, 20, 'TRACK / İZ')
        fps = self.model.fps_num / self.model.fps_den
        step = max(1, round(fps * max(1, 80 / (fps * self.zoom))))
        first_frame = (self.frame_for(100) // step) * step
        for frame in range(first_frame, self.frame_for(self.width()) + step, step):
            x = int(self.x_for(frame))
            if x < 100:
                continue
            p.drawText(x + 2, 18, f'{frame / fps:.1f}s')
            p.setPen(QColor('#292c37'))
            p.drawLine(x, 24, x, self.height())
            p.setPen(QColor('#9a9daf'))
        colors = {'video': '#5a49a8', 'audio': '#257e77', 'text': '#a55a83', 'overlay': '#9c703c'}
        for ti, track in enumerate(self.model.tracks):
            y = 30 + ti * 43
            p.fillRect(0, y, self.width(), 40, QColor('#1b1d25'))
            p.setPen(QColor('#dddded'))
            p.drawText(6, y + 25, track.name[:14])
            for clip in track.clips:
                x, w = int(self.x_for(clip.start)), max(2, int(clip.length * self.zoom))
                if x + w <= 100 or x >= self.width():
                    continue
                left = max(100, x)
                right = min(self.width(), x + w)
                p.setBrush(QColor(colors[track.kind]))
                p.setPen(QPen(QColor('#ffffff' if self.selected == (ti, clip.id) else '#282a37'), 2))
                p.drawRoundedRect(left, y + 3, max(2, right-left), 34, 5, 5)
                strip = self.thumbnails.get(clip.source) if track.kind in ('video', 'overlay') else None
                if strip is not None:
                    self._draw_strip(p, strip, clip, x, y, left, right, fps)
                peaks = self.waveforms.get(clip.source)
                if peaks and track.kind in ('audio', 'video'):
                    p.setPen(QColor('#a4e3db'))
                    for px in range(left, right, 2):
                        source_frame = clip.source_in + (px - x) / self.zoom
                        sample = int(source_frame / fps * SAMPLE_RATE / WINDOW)
                        if 0 <= sample < len(peaks):
                            height = int(peaks[sample] * 14)
                            p.drawLine(px, y + 21 - height, px, y + 21 + height)
                p.setPen(QColor('white'))
                p.drawText(left + 5, y + 25, (clip.text or {'circle': '◯ daire', 'arrow': '➜ ok'}.get(clip.style.get('shape')) or clip.source.replace('\\', '/').split('/')[-1])[:max(0, (right-left) // 7)])
        p.setPen(QPen(QColor('#ffcd5a'), 2))
        for marker in self.model.markers:
            x = int(self.x_for(marker.get('frame', 0)))
            if x < 100 or x > self.width():
                continue
            p.drawLine(x, 20, x, self.height())
            p.drawText(x + 3, 28, str(marker.get('label', ''))[:24])
        p.setPen(QPen(QColor('#ff4fa3'), 2))
        x = int(self.x_for(self.playhead))
        if 100 <= x <= self.width():
            p.drawLine(x, 20, x, self.height())

    def mousePressEvent(self, event):
        x, y = event.position().x(), event.position().y()
        frame = self.frame_for(x)
        if y < 30 and x >= 100:
            self.drag_mode = 'scrub'
            frame = snap_frame(self.model, frame, max(1, round(8 / self.zoom)))
            self.playhead = frame
            self.seek.emit(frame)
            self.update()
            return
        ti = int((y - 30) // 43)
        if 0 <= ti < len(self.model.tracks):
            self.selected_track = ti
            track = self.model.tracks[ti]
            clip = next((c for c in track.clips if c.start <= frame < c.end), None) if x >= 100 else None
            self.selected = (ti, clip.id) if clip else None
            self.selection_changed.emit()
            if clip:
                # Either edge trims; the right edge wins on a clip too narrow to tell them apart.
                self.drag_mode = ('trim' if abs(x - self.x_for(clip.end)) < 9
                                  else 'trim_start' if abs(x - self.x_for(clip.start)) < 9 else 'move')
                self.drag_anchor = frame
                self.original = (clip.start, clip.length)
                self.original_track = ti
                self.edit_started.emit()
            elif x >= 100:
                self.playhead = frame
                self.seek.emit(frame)
            self.update()

    def mouseDoubleClickEvent(self, event):
        x, y = event.position().x(), event.position().y()
        ti = int((y - 30) // 43)
        if x >= 100 and y >= 30 and 0 <= ti < len(self.model.tracks):
            frame = self.frame_for(x)
            clip = next((c for c in self.model.tracks[ti].clips if c.start <= frame < c.end), None)
            if clip:
                self.drag_mode = None
                self.selected, self.selected_track = (ti, clip.id), ti
                self.update()
                self.clip_activated.emit(ti, clip.id)

    def mouseMoveEvent(self, event):
        if self.drag_mode == 'scrub':
            self.playhead = snap_frame(self.model, self.frame_for(event.position().x()), max(1, round(8 / self.zoom)))
            self.seek.emit(self.playhead)
            self.update()
            return
        if not self.drag_mode or not self.selected:
            return
        ti, clip_id = self.selected
        track = self.model.tracks[ti]
        clip = track.find(clip_id)
        delta = self.frame_for(event.position().x()) - self.drag_anchor
        if self.drag_mode == 'move':
            # Dragged over another track of the same kind: the clip goes there when it has room.
            over = int((event.position().y() - 30) // 43)
            if 0 <= over < len(self.model.tracks) and over != ti and self.model.tracks[over].kind == track.kind:
                track.clips.remove(clip)
                try:
                    self.model.tracks[over].add(clip)
                except ValueError:
                    track.clips.append(clip)        # no room there: it stays where it was
                else:
                    ti, track = over, self.model.tracks[over]
                    self.selected, self.selected_track = (over, clip.id), over
                    self.selection_changed.emit()
        try:
            if self.drag_mode == 'move':
                target = max(0, self.original[0] + delta)
                target = snap_frame(self.model, target, max(1, round(8 / self.zoom)), self.selected)
                track.move(clip.id, target)
            elif self.drag_mode == 'trim_start':
                track.trim_start(clip.id, max(0, self.original[0] + delta))
            else:
                track.trim_end(clip.id, clip.start + max(1, self.original[1] + delta))
        except ValueError:
            pass
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_mode in ('move', 'trim', 'trim_start') and self.original and self.selected:
            ti, clip_id = self.selected
            clip = next((c for c in self.model.tracks[ti].clips if c.id == clip_id), None)
            if clip and ((clip.start, clip.length) != self.original or ti != getattr(self, 'original_track', ti)):
                self.changed.emit()
        self.original = None
        self.drag_mode = None
