"""“Shorts'a böl”: how long each part may be, how it looks; shows how many parts it makes before starting.

Self-contained: the host passes the edit's length and its pauses, and reads selection() when accepted.
"""
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout

from akis import i18n, shorts_split


class ShortsDialog(QDialog):
    def __init__(self, parent=None, *, total, pauses=(), language='tr'):
        super().__init__(parent)
        self.language = language
        self.total, self.pauses = float(total), list(pauses)
        self.setWindowTitle(self.tr_("Shorts'a böl"))
        self.resize(520, 380)
        layout = QVBoxLayout(self)
        intro = QLabel(self.tr_('Videonun tamamı, hiçbir yeri atılmadan, art arda dikey kısa videolara bölünür. '
                                'Parçalar mümkün olduğunca konuşmadaki bir duraklamadan bölünür.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.limit = QSpinBox()
        self.limit.setRange(shorts_split.MIN_LIMIT, shorts_split.MAX_LIMIT)
        self.limit.setValue(shorts_split.DEFAULT_LIMIT)
        self.limit.setSuffix(self.tr_(' sn'))
        self.limit.setToolTip(self.tr_('YouTube Shorts en çok 3 dakika kabul eder; 60 saniye en yaygın uzunluktur.'))
        self.limit.valueChanged.connect(self._refresh)
        form.addRow(self.tr_('Bir parça en çok'), self.limit)
        layout.addLayout(form)
        self.fill = QCheckBox(self.tr_('Dikey ekranı doldur (yatay videonun kenarları kırpılır)'))
        self.fill.setChecked(True)
        layout.addWidget(self.fill)
        self.label = QCheckBox(self.tr_('Her parçanın başına “Bölüm 1/N” yaz'))
        self.label.setChecked(True)
        layout.addWidget(self.label)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary, 1)
        buttons = QDialogButtonBox()
        self.start_button = buttons.addButton(self.tr_('Parçaları dışa aktar'), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.tr_('İptal'), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def tr_(self, text):
        return i18n.translate(text, self.language)

    def parts(self):
        return shorts_split.plan_parts(self.total, self.limit.value(), self.pauses)

    def _refresh(self):
        parts = self.parts()
        lengths = ', '.join(shorts_split.clock(b - a) for a, b in parts[:12]) + (' …' if len(parts) > 12 else '')
        self.summary.setText(self.tr_('{total} sürelik video {count} parçaya bölünecek: {lengths}').format(
            total=shorts_split.clock(self.total), count=len(parts), lengths=lengths))
        self.start_button.setEnabled(bool(parts))

    def selection(self):
        """(parts, fill, label)."""
        return self.parts(), self.fill.isChecked(), self.label.isChecked()
