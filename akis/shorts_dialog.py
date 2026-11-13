"""“Shorts'a böl”: how long each part may be, how it looks, a title per part; shows the parts before starting.

Self-contained: the host passes the edit's length, its pauses and what is said when (for title ideas),
and reads selection() when accepted.
"""
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHeaderView, QLabel, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)
from PySide6.QtCore import Qt

from akis import clip_fit, i18n, shorts_split

FRAMING_NAMES = {clip_fit.BLUR: 'Bulanık arka plan (kırpmadan doldurur)', clip_fit.FILL: 'Doldur (kenarlar kırpılır)',
                 clip_fit.FIT: 'Sığdır (üstte ve altta siyah boşluk)'}


class ShortsDialog(QDialog):
    def __init__(self, parent=None, *, total, pauses=(), said=(), language='tr'):
        super().__init__(parent)
        self.language = language
        self.total, self.pauses, self.said = float(total), list(pauses), list(said)
        self.typed = {}            # part number -> title the user wrote
        self._filling = False
        self.setWindowTitle(self.tr_("Shorts'a böl"))
        self.resize(640, 620)
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
        self.framing = QComboBox()
        for key in shorts_split.FRAMINGS:
            self.framing.addItem(self.tr_(FRAMING_NAMES[key]), key)
        form.addRow(self.tr_('Görüntü'), self.framing)
        layout.addLayout(form)
        self.card = QCheckBox(self.tr_('Üstte sıra numarası ve başlık kartı göster (ör. “4 / 7”)'))
        self.card.setChecked(True)
        layout.addWidget(self.card)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        hint = QLabel(self.tr_('Başlıklar kartta ve dosya adında kullanılır; çift tıklayıp değiştirebilirsiniz.'))
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        layout.addWidget(hint)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['#', self.tr_('Süre'), self.tr_('Başlık')])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.itemChanged.connect(self._typed)
        layout.addWidget(self.table, 1)
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

    def _typed(self, item):
        if item.column() == 2 and not self._filling:
            self.typed[item.row()] = item.text()

    def _refresh(self):
        parts = self.parts()
        self.summary.setText(self.tr_('{total} sürelik video {count} parçaya bölünecek.').format(
            total=shorts_split.clock(self.total), count=len(parts)))
        suggested = shorts_split.suggest_titles(parts, self.said)
        self._filling = True
        self.table.setRowCount(len(parts))
        for row, ((start, end), title) in enumerate(zip(parts, suggested)):
            for column, value in enumerate((str(row + 1), shorts_split.clock(end - start), self.typed.get(row, title))):
                item = QTableWidgetItem(value)
                if column < 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
        self._filling = False
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(1)
        self.start_button.setEnabled(bool(parts))

    def titles(self):
        return [self.table.item(row, 2).text().strip() for row in range(self.table.rowCount())]

    def selection(self):
        """(parts, framing, card, titles)."""
        return self.parts(), self.framing.currentData(), self.card.isChecked(), self.titles()
