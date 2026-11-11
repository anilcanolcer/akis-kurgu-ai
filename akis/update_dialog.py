"""Non-modal download progress for an update: percentage, MB done/total, cancel, retry after a failure."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from akis import i18n

MB = 1024 * 1024


class UpdateProgressDialog(QDialog):
    """Shows one update download. Closing the window only hides it; the download goes on.

    cancel_requested: the user pressed Cancel while downloading.
    retry_requested: the user pressed Retry after a failure.
    """
    cancel_requested = Signal()
    retry_requested = Signal()

    def __init__(self, version: str, language: str = 'tr', parent=None):
        super().__init__(parent)
        self.version = version
        self.language = language
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowTitle(self.text('Akış Kurgu AI güncellemesi'))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        layout.addWidget(self.bar)
        self.detail = QLabel()
        self.detail.setObjectName('muted')
        layout.addWidget(self.detail)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.retry_button = QPushButton(self.text('Yeniden dene'))
        self.retry_button.clicked.connect(self.retry_requested)
        self.cancel_button = QPushButton(self.text('İptal'))
        self.cancel_button.clicked.connect(self.request_cancel)
        self.close_button = QPushButton(self.text('Kapat'))
        self.close_button.clicked.connect(self.hide)
        for button in (self.retry_button, self.cancel_button, self.close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.start()

    def text(self, template: str, **values) -> str:
        """A whole-string translation of `template` (see akis.i18n), then filled in."""
        return i18n.translate(template, self.language).format(**values)

    def start(self) -> None:
        """Back to the downloading state (also used by Retry)."""
        self.status.setText(self.text('Akış Kurgu AI {version} indiriliyor…', version=self.version))
        self.bar.setRange(0, 0)  # indeterminate until the first progress report says the size
        self.bar.setValue(0)
        self.detail.setText(self.text('Bağlanılıyor…'))
        self.retry_button.hide()
        self.close_button.hide()
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)

    def set_progress(self, done: int, total: int) -> None:
        if total > 0:
            done = min(done, total)
            self.bar.setRange(0, 100)
            self.bar.setValue(done * 100 // total)
            self.detail.setText(self.text('{done:.1f} MB / {total:.1f} MB indirildi',
                                          done=done / MB, total=total / MB))
        else:
            self.bar.setRange(0, 0)
            self.detail.setText(self.text('{done:.1f} MB indirildi (toplam boyut bilinmiyor)', done=done / MB))

    def percent(self) -> int:
        """Shown percentage, or -1 while the size is unknown."""
        return self.bar.value() if self.bar.maximum() > 0 else -1

    def request_cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.status.setText(self.text('İndirme iptal ediliyor…'))
        self.cancel_requested.emit()

    def show_verifying(self) -> None:
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.status.setText(self.text('İndirme tamamlandı ve doğrulandı.'))
        self.cancel_button.hide()

    def show_failed(self, message: str) -> None:
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.status.setText(self.text('Güncelleme indirilemedi: {message}', message=message))
        self.detail.setText(self.text('Uygulama değişmedi; çalışmaya devam edebilirsiniz.'))
        self.cancel_button.hide()
        self.retry_button.show()
        self.close_button.show()
        self.show()
        self.raise_()

    def closeEvent(self, event):
        # The window's X only hides it; a running download is cancelled with the Cancel button.
        event.ignore()
        self.hide()
