"""“Toplu dışa aktar”: choose videos, an output folder, what to do to each; the host runs the export.

Self-contained (no import of main.py). The host passes the saved templates and reads selection()
after the dialog is accepted.
"""
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPushButton, QVBoxLayout)

from akis import i18n

VIDEO_FILTER = 'Video (*.mp4 *.mov *.mkv *.webm *.avi *.m4v)'


class BatchDialog(QDialog):
    def __init__(self, parent=None, *, templates=(), folder='', language='tr'):
        super().__init__(parent)
        self.language = language
        self.templates = list(templates)
        self.setWindowTitle(self.tr_('Toplu dışa aktar'))
        self.resize(580, 520)
        layout = QVBoxLayout(self)
        intro = QLabel(self.tr_('Seçtiğiniz her video aynı biçimde işlenip ayrı bir dosya olarak kaydedilir. Renk, hız, '
                                'ses düğmeleri ve tuval oranı açık projedeki ayarlardan alınır.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.files = QListWidget()
        layout.addWidget(self.files, 1)
        row = QHBoxLayout()
        add = QPushButton(self.tr_('Video ekle'))
        add.clicked.connect(self.choose_videos)
        remove = QPushButton(self.tr_('Seçileni çıkar'))
        remove.clicked.connect(lambda: [self.files.takeItem(self.files.row(item)) for item in self.files.selectedItems()]
                               and self._refresh())
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        self.silences = QCheckBox(self.tr_('Sessizlikleri çıkar'))
        self.silences.setChecked(True)
        layout.addWidget(self.silences)
        layout.addWidget(QLabel(self.tr_('Şablon')))
        self.template = QComboBox()
        self.template.addItem(self.tr_('Şablon yok'), None)
        for index, item in enumerate(self.templates):
            self.template.addItem(item['name'], index)
        layout.addWidget(self.template)
        layout.addWidget(QLabel(self.tr_('Kaydedilecek klasör')))
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(folder)
        self.folder.textChanged.connect(lambda _text: self._refresh())
        browse = QPushButton(self.tr_('Seç…'))
        browse.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)
        buttons = QDialogButtonBox()
        self.start_button = buttons.addButton(self.tr_('Başlat'), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.tr_('İptal'), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def tr_(self, text):
        return i18n.translate(text, self.language)

    def add_videos(self, paths):
        known = set(self.videos())
        for path in paths:
            if path and path not in known:
                self.files.addItem(path)
                known.add(path)
        self._refresh()

    def choose_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr_('Video ekle'), '', VIDEO_FILTER)
        self.add_videos(paths)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr_('Kaydedilecek klasör'), self.folder.text())
        if folder:
            self.folder.setText(folder)

    def videos(self):
        return [self.files.item(i).text() for i in range(self.files.count())]

    def _refresh(self):
        self.start_button.setEnabled(bool(self.videos()) and bool(self.folder.text().strip())
                                     and Path(self.folder.text().strip()).is_dir())

    def selection(self):
        """(videos, folder, cut silences, template or None)."""
        index = self.template.currentData()
        return (self.videos(), self.folder.text().strip(), self.silences.isChecked(),
                self.templates[index] if index is not None else None)
