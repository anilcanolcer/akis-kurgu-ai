"""“Şablonlarım”: the templates the user saved from their own projects.

Opened from the Şablonlar dialog. Self-contained; the host passes
    saved            the user's templates (akis.user_templates items)
    save(name)       saves the open project under that name and returns the new list
    delete(name)     deletes a saved template and returns the new list
and reads selection() after the dialog is accepted.
"""
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox, QPushButton,
                               QVBoxLayout)

from akis import i18n, user_templates

TITLE = 'Şablonlarım'


class SavedTemplatesDialog(QDialog):
    def __init__(self, parent=None, *, saved=(), save=None, delete=None, language='tr'):
        super().__init__(parent)
        self.language = language
        self.saved, self._save, self._delete = list(saved), save, delete
        self.setWindowTitle(self.tr_(TITLE))
        self.resize(560, 460)
        layout = QVBoxLayout(self)
        intro = QLabel(self.tr_('Bir projenizin izlerini, tuval oranını, renk ve hız ayarını, ses düğmelerini '
                                'şablon olarak saklayın; sonraki videoya tek seçimle uygulayın.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        row = QHBoxLayout()
        self.save_button = QPushButton(self.tr_('Bu projeyi şablon olarak kaydet'))
        self.save_button.clicked.connect(self.save_current)
        self.save_button.setVisible(save is not None)
        row.addWidget(self.save_button)
        self.delete_button = QPushButton(self.tr_('Şablonu sil'))
        self.delete_button.clicked.connect(self.delete_selected)
        row.addWidget(self.delete_button)
        row.addStretch(1)
        cancel = QPushButton(self.tr_('İptal'))
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.apply_button = QPushButton(self.tr_('Şablonu uygula'))
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.accept)
        row.addWidget(self.apply_button)
        layout.addLayout(row)
        self.list.currentRowChanged.connect(lambda _row: self.changed())
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.fill()

    def tr_(self, text):
        return i18n.translate(text, self.language)

    def fill(self, select=0):
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems([item['name'] for item in self.saved])
        self.list.blockSignals(False)
        if self.saved:
            self.list.setCurrentRow(max(0, min(select, len(self.saved) - 1)))
        self.changed()

    def selection(self):
        """The selected template, or None when the list is empty."""
        row = self.list.currentRow()
        return self.saved[row] if 0 <= row < len(self.saved) else None

    def changed(self):
        item = self.selection()
        self.apply_button.setEnabled(item is not None)
        self.delete_button.setEnabled(item is not None and self._delete is not None)
        self.details.setText(user_templates.describe(item) if item is not None
                             else self.tr_('Henüz kayıtlı şablonunuz yok.'))

    def save_current(self):
        name, ok = QInputDialog.getText(self, self.tr_('Şablon olarak kaydet'), self.tr_('Şablonun adı:'))
        name = user_templates.clean_name(name)
        if not ok or not name:
            return
        if any(item['name'].casefold() == name.casefold() for item in self.saved) and QMessageBox.question(
                self, self.tr_(TITLE), self.tr_('“{name}” adlı şablon zaten var. Üzerine yazılsın mı?').format(name=name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.saved = list(self._save(name))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, self.tr_(TITLE), self.tr_('Şablon kaydedilemedi: {error}').format(error=exc))
            return
        self.fill(next((i for i, item in enumerate(self.saved) if item['name'].casefold() == name.casefold()), 0))

    def delete_selected(self):
        item = self.selection()
        if item is None or self._delete is None:
            return
        if QMessageBox.question(self, self.tr_(TITLE),
                                self.tr_('“{name}” şablonu silinsin mi? Bu geri alınamaz.').format(name=item['name']),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.saved = list(self._delete(item['name']))
        except OSError as exc:
            QMessageBox.warning(self, self.tr_(TITLE), self.tr_('Şablon silinemedi: {error}').format(error=exc))
            return
        self.fill(self.list.currentRow())
