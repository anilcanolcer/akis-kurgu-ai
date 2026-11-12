"""“Sessizlikleri çıkar” dialog: measure once, tune with sliders, see what will be cut, then apply.

Self-contained (no import of main.py). The host passes the ffmpeg path, the sources and the current main
cut, and reads `segments` after the dialog is accepted; applying them is the host's job
(edit_plan.apply_plan), so the cut lands in the normal undo history.
"""
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QProgressBar, QSlider,
                               QVBoxLayout, QWidget)

from akis import i18n, silence_cut

TITLE = 'Sessizlikleri çıkar'
KEPT = QColor('#2f9e6e')
CUT = QColor('#d6453d')
EMPTY = QColor('#2a2f37')


class MeasureWorker(QThread):
    """Reads each source's loudness curve off the GUI thread."""
    measured = Signal(int, object)

    def __init__(self, executable, paths, measure=silence_cut.measure):
        super().__init__()
        self.executable, self.paths, self.measure = executable, list(paths), measure

    def run(self):
        for index, path in enumerate(self.paths):
            if self.isInterruptionRequested():
                return
            self.measured.emit(index, self.measure(self.executable, path))


class CutStrip(QWidget):
    """The main cut drawn left to right: green stays, red goes."""

    def __init__(self, tip='Yeşil kalır, kırmızı kesilir.'):
        super().__init__()
        self.setMinimumHeight(34)
        self.segments, self.cuts = [], []
        self.setToolTip(tip)

    def show_cut(self, segments, cuts):
        self.segments, self.cuts = list(segments), list(cuts)
        self.update()

    def ranges(self):
        """(start, end, removed) as fractions of the main cut's length, for painting and for tests."""
        total = silence_cut.duration(self.segments)
        if total <= 0:
            return []
        offsets, cursor = [], 0.0
        for segment in self.segments:
            offsets.append(cursor)
            cursor += segment['end'] - segment['start']
        found = [(0.0, 1.0, False)]
        for number, a, b in self.cuts:
            base = offsets[number] - self.segments[number]['start']
            found.append(((base + a) / total, (base + b) / total, True))
        return found

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), EMPTY)
        width, height = self.width(), self.height()
        for start, end, removed in self.ranges():
            x = round(start * width)
            painter.fillRect(x, 0, max(1, round(end * width) - x), height, CUT if removed else KEPT)
        painter.end()


class SilenceDialog(QDialog):
    def __init__(self, parent=None, *, executable, sources, segments, measure=silence_cut.measure, language='tr'):
        """sources: [{'path', 'duration'}] in the index order `segments` refers to (edit_plan.current_segments)."""
        super().__init__(parent)
        self.language = language
        self.setWindowTitle(self.tr_(TITLE))
        self.resize(560, 320)
        self.before = [dict(segment) for segment in segments]
        self.segments, self.cuts = list(self.before), []
        self.levels = {}
        self._pending = len(sources)

        root = QVBoxLayout(self)
        intro = QLabel(self.tr_('Konuşma olmayan yerler kesilir. Yapay zekâ ve internet kullanılmaz; '
                                'beğenmezseniz tek adımda geri alabilirsiniz.'))
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        self.threshold = self._slider(-60, -20, silence_cut.DEFAULT_THRESHOLD_DB)
        self.min_silence = self._slider(2, 20, round(silence_cut.DEFAULT_MIN_SILENCE * 10))
        self.margin = self._slider(0, 10, round(silence_cut.DEFAULT_MARGIN * 20))
        self.threshold_label, self.min_label, self.margin_label = QLabel(), QLabel(), QLabel()
        form.addRow(self.threshold_label, self.threshold)
        form.addRow(self.min_label, self.min_silence)
        form.addRow(self.margin_label, self.margin)
        root.addLayout(form)
        self.threshold.setToolTip(self.tr_('Bu düzeyin altındaki ses sessizlik sayılır. Sağa çektikçe daha çok yer kesilir.'))
        self.min_silence.setToolTip(self.tr_('Bundan kısa duraklamalara dokunulmaz.'))
        self.margin.setToolTip(self.tr_('Her kesimin iki yanında bırakılan süre; kelimelerin başı ve sonu yutulmasın diye.'))

        self.strip = CutStrip(self.tr_('Yeşil kalır, kırmızı kesilir.'))
        root.addWidget(self.strip)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        root.addWidget(self.progress)
        self.result = QLabel(self.tr_('Ses çözümleniyor…'))
        self.result.setWordWrap(True)
        root.addWidget(self.result)

        self.buttons = QDialogButtonBox()
        self.apply_button = self.buttons.addButton(self.tr_('Sessizlikleri kes'), QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(self.tr_('İptal'), QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.apply_button.setEnabled(False)
        root.addWidget(self.buttons)

        self._labels()
        self.strip.show_cut(self.before, [])
        self.worker = MeasureWorker(executable, [source['path'] for source in sources], measure)
        self.worker.measured.connect(self._measured)
        self.worker.finished.connect(self._measuring_done)
        self.worker.start()

    def tr_(self, text):
        return i18n.translate(text, self.language)

    def _slider(self, low, high, value):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        slider.valueChanged.connect(self.refresh)
        return slider

    def settings(self):
        """(threshold dB, shortest silence s, margin s) as the sliders stand."""
        return self.threshold.value(), self.min_silence.value() / 10, self.margin.value() / 20

    def _labels(self):
        threshold, shortest, margin = self.settings()
        self.threshold_label.setText(self.tr_('Sessizlik eşiği: {value} dB').format(value=threshold))
        self.min_label.setText(self.tr_('En kısa sessizlik: {value} sn').format(value=f'{shortest:.1f}'))
        self.margin_label.setText(self.tr_('Kesim payı: {value} sn').format(value=f'{margin:.2f}'))

    def _measured(self, index, levels):
        self.levels[index] = levels
        self._pending -= 1

    def _measuring_done(self):
        self.progress.hide()
        self.refresh()

    def refresh(self):
        self._labels()
        if self._pending > 0:
            return
        if not any(self.levels.values()):
            self.result.setText(self.tr_('Videoda çözümlenebilir ses bulunamadı.'))
            self.apply_button.setEnabled(False)
            return
        threshold, shortest, margin = self.settings()
        silences = {index: silence_cut.silent_spans(levels, threshold, shortest)
                    for index, levels in self.levels.items()}
        self.segments, self.cuts = silence_cut.keep_segments(self.before, silences, margin)
        self.strip.show_cut(self.before, self.cuts)
        self.result.setText(silence_cut.summary(self.before, self.segments, self.cuts, self.tr_))
        self.apply_button.setEnabled(bool(self.cuts))

    def done(self, code):
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(5000)
        super().done(code)
