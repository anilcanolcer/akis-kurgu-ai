"""Interactive frame-based timeline view."""
from PySide6.QtCore import Qt, Signal
from akis.caption_service import snap_frame
from akis.waveform_service import WaveformWorker, SAMPLE_RATE, WINDOW
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class MultitrackWidget(QWidget):
    seek = Signal(int)
    changed = Signal()
    selection_changed = Signal()

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.waveforms = {}
        self.waveform_worker = None
        self.waveform_executable = None
        self.zoom = 2.0
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

    def x_for(self, frame):
        return 100 + frame * self.zoom

    def frame_for(self, x):
        return max(0, round((x - 100) / self.zoom))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#111218'))
        p.setPen(QColor('#9a9daf'))
        p.drawText(8, 20, 'TRACK / İZ')
        fps = self.model.fps_num / self.model.fps_den
        step = max(1, round(fps * max(1, 80 / (fps * self.zoom))))
        for frame in range(0, self.frame_for(self.width()) + step, step):
            x = int(self.x_for(frame))
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
                p.setBrush(QColor(colors[track.kind]))
                p.setPen(QPen(QColor('#ffffff' if self.selected == (ti, clip.id) else '#282a37'), 2))
                p.drawRoundedRect(x, y + 3, w, 34, 5, 5)
                peaks = self.waveforms.get(clip.source)
                if peaks and track.kind in ('audio', 'video'):
                    p.setPen(QColor('#a4e3db'))
                    for px in range(max(0, x), min(self.width(), x + w), 2):
                        source_frame = clip.source_in + (px - x) / self.zoom
                        sample = int(source_frame / fps * SAMPLE_RATE / WINDOW)
                        if 0 <= sample < len(peaks):
                            height = int(peaks[sample] * 14)
                            p.drawLine(px, y + 21 - height, px, y + 21 + height)
                p.setPen(QColor('white'))
                p.drawText(x + 5, y + 25, (clip.text or clip.source.replace('\\', '/').split('/')[-1])[:max(0, w // 7)])
        p.setPen(QPen(QColor('#ffcd5a'), 2))
        for marker in self.model.markers:
            x = int(self.x_for(marker.get('frame', 0)))
            p.drawLine(x, 20, x, self.height())
            p.drawText(x + 3, 28, str(marker.get('label', ''))[:24])
        p.setPen(QPen(QColor('#ff4fa3'), 2))
        x = int(self.x_for(self.playhead))
        p.drawLine(x, 20, x, self.height())

    def mousePressEvent(self, event):
        x, y = event.position().x(), event.position().y()
        frame = self.frame_for(x)
        if y < 30:
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
            clip = next((c for c in track.clips if c.start <= frame < c.end), None)
            self.selected = (ti, clip.id) if clip else None
            self.selection_changed.emit()
            if clip:
                self.drag_mode = 'trim' if abs(x - self.x_for(clip.end)) < 9 else 'move'
                self.drag_anchor = frame
                self.original = (clip.start, clip.length)
            else:
                self.playhead = frame
                self.seek.emit(frame)
            self.update()

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
        try:
            if self.drag_mode == 'move':
                target = max(0, self.original[0] + delta)
                target = snap_frame(self.model, target, max(1, round(8 / self.zoom)), self.selected)
                track.move(clip.id, target)
            else:
                track.trim_end(clip.id, clip.start + max(1, self.original[1] + delta))
        except ValueError:
            pass
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_mode in ('move', 'trim'):
            self.changed.emit()
        self.drag_mode = None
