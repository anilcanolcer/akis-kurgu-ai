"""“Öne çıkan anlar”: the liveliest stretches with their reasons; tick the ones to export as Shorts.

Self-contained: the host passes what akis.highlights.find returned and title ideas, and reads selection().
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from akis import highlights, i18n, shorts_split


class HighlightsDialog(QDialog):
    def __init__(self, parent=None, *, found, titles=(), language='tr'):
        super().__init__(parent)
        self.language = language
        self.found = list(found)
        self.setWindowTitle(self.tr_('Öne çıkan anlar'))
        self.resize(720, 460)
        layout = QVBoxLayout(self)
        intro = QLabel(self.tr_('Videonun en canlı bölümleri, sesine bakılarak bulundu. İşaretlediklerinizi dikey kısa '
                                'video olarak dışa aktarabilirsiniz; başlıkları çift tıklayıp değiştirebilirsiniz.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(len(self.found), 4)
        self.table.setHorizontalHeaderLabels([self.tr_('Zaman'), self.tr_('Süre'), self.tr_('Neden'), self.tr_('Başlık')])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        titles = list(titles) + [''] * len(self.found)
        for row, (start, end, _, details) in enumerate(self.found):
            when = QTableWidgetItem(f'{shorts_split.clock(start)} – {shorts_split.clock(end)}')
            when.setFlags((when.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable)
            when.setCheckState(Qt.CheckState.Checked)
            length = QTableWidgetItem(shorts_split.clock(end - start))
            why = QTableWidgetItem(highlights.reasons(details, self.tr_))
            for item in (length, why):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            for column, item in enumerate((when, length, why, QTableWidgetItem(titles[row]))):
                self.table.setItem(row, column, item)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(1)
        self.table.itemChanged.connect(lambda _item: self._refresh())
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox()
        self.export_button = buttons.addButton(self.tr_('Seçilenleri Shorts olarak dışa aktar'), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.tr_('İptal'), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def tr_(self, text):
        return i18n.translate(text, self.language)

    def _rows(self):
        return [row for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def _refresh(self):
        self.export_button.setEnabled(bool(self._rows()))

    def selection(self):
        """([(start, end)], [title]) of the ticked rows."""
        rows = self._rows()
        return ([self.found[row][:2] for row in rows], [self.table.item(row, 3).text().strip() for row in rows])
