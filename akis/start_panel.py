"""The first thing an empty project shows: three steps, each with the button that does it.

Sits over the preview while there is no video. Self-contained: the host passes what each button does and
shows or hides the panel; the texts are plain Turkish widget texts, so the window's language switch
translates them like every other label.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout

from akis import theme

STYLE = """
QFrame#startPanel { background: $panel; border: 1px solid $border_strong; border-radius: 14px; }
QFrame#startPanel QLabel { background: transparent; }
QLabel#startHeading { font-size: 19px; font-weight: 700; }
QLabel#startNumber { color: $accent_text; font-size: 22px; font-weight: 800; }
QLabel#startHint { color: $muted; }
QPushButton#startPrimary { background: $accent; border: 1px solid $accent; color: white; font-weight: 700; padding: 8px 16px; }
QPushButton#startPrimary:hover { background: $accent_hover; }
QPushButton#startSecondary { background: $raised; border: 1px solid $border_strong; padding: 8px 16px; }
"""
STEPS = (
    ('Video ekleyin', 'Bilgisayarınızdan bir video seçin ya da pencereye sürükleyin.', 'Video seç', 'add'),
    ('Nasıl kurgulanacağını seçin', 'Hazır bir şablon uygulayın ya da AI sekmesine isteğinizi yazın.', 'Şablonlar', 'templates'),
    ('Dışa aktarın', 'Beğendiğinizde sağ üstteki “Dışa aktar” düğmesiyle videonuzu kaydedin.', '', ''),
)


class StartPanel(QFrame):
    def restyle(self):
        self.setStyleSheet(theme.css(STYLE))

    def __init__(self, parent=None, *, add_video, show_templates):
        super().__init__(parent)
        self.setObjectName('startPanel')
        self.restyle()
        self.setMaximumWidth(560)
        actions = {'add': add_video, 'templates': show_templates}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        heading = QLabel('Üç adımda ilk videonuz')
        heading.setObjectName('startHeading')
        outer.addWidget(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        self.buttons = {}
        for row, (title, hint, button_text, action) in enumerate(STEPS):
            number = QLabel(str(row + 1))
            number.setObjectName('startNumber')
            number.setProperty('i18n_skip', True)
            grid.addWidget(number, row, 0, Qt.AlignmentFlag.AlignTop)
            text = QVBoxLayout()
            text.setSpacing(2)
            name = QLabel(title)
            name.setStyleSheet('font-weight: 700;')
            note = QLabel(hint)
            note.setObjectName('startHint')
            note.setWordWrap(True)
            text.addWidget(name)
            text.addWidget(note)
            grid.addLayout(text, row, 1)
            if action:
                button = QPushButton(button_text)
                button.setObjectName('startPrimary' if row == 0 else 'startSecondary')
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(actions[action])
                self.buttons[action] = button
                grid.addWidget(button, row, 2, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(grid)
