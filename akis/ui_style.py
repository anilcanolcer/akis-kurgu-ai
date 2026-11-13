"""The window's stylesheet; colours are $role names filled from akis.theme."""

STYLE = r"""
* { font-family: 'Segoe UI'; font-size: 13px; color: $text; }
QMainWindow, QWidget { background: $bg; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QFrame#sidebar { background: $surface; border-right: 1px solid $border; }
QLabel#brand { font-size: 18px; font-weight: 800; letter-spacing: 1px; }
QLabel#projectTitle { font-size: 22px; font-weight: 700; }
QLabel#aiHero { font-size: 23px; font-weight: 760; line-height: 1.25; }
QLabel#muted, QLabel#mutedSmall { color: $muted; }
QLabel#mutedSmall { font-size: 11px; }
QLabel#sectionLabel { color: $muted; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 7px; }
QLabel#mono { font-family: 'Cascadia Mono'; color: $text_soft; }
QLabel#statusPill { background: $panel; color: $text_soft; border: 1px solid $border; border-radius: 14px; padding: 6px 11px; max-width: 360px; }
QPushButton { border: 0; border-radius: 9px; padding: 9px 12px; background: $button; text-align: left; }
QPushButton:hover { background: $button_hover; }
QPushButton[nav='true'] { background: transparent; color: $text_soft; padding: 10px 12px; }
QPushButton[nav='true']:hover, QPushButton[active='true'] { background: $accent_bg; color: $text_strong; }
QPushButton#primary, QPushButton#primaryLarge { background: $accent; color: white; font-weight: 700; text-align: center; }
QPushButton#primary:hover, QPushButton#primaryLarge:hover { background: $accent_hover; }
QPushButton#primaryLarge { padding: 13px; }
QPushButton#secondary { border: 1px solid $border_strong; background: $raised; text-align: center; }
QPushButton#ghost { background: transparent; color: $text_soft; text-align: center; }
QPushButton#roundButton { border-radius: 20px; background: $accent; text-align: center; padding: 0; }
QFrame#editor { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#privacyCard { background: $panel; border: 1px solid $border; border-radius: 10px; }
QLabel#localTitle { color: $success; font-weight: 600; }
QPushButton#versionTag { background: transparent; color: $faint; font-size: 11px; padding: 4px 2px; text-align: left; }
QPushButton#versionTag:hover { color: $accent_text; text-decoration: underline; }
QVideoWidget#video { background: $video_bg; border-radius: 10px; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox { background: $field; border: 1px solid $border_strong; border-radius: 8px; padding: 8px; selection-background-color: $accent; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid $accent_line; }
QPlainTextEdit { line-height: 1.35; }
QListWidget#mediaList { background: transparent; border: 0; outline: 0; }
QListWidget#mediaList::item { background: $panel; border-radius: 8px; padding: 9px; margin-bottom: 5px; }
QTabWidget::pane { background: $surface; border: 1px solid $border; border-radius: 12px; top: -1px; }
QTabBar::tab { background: transparent; color: $muted; padding: 10px 12px; }
QTabBar::tab:selected { color: $text_strong; border-bottom: 2px solid $accent_line; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: $border_strong; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSlider::groove:horizontal { height: 4px; background: $border_strong; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent_line; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: $accent_text; }
QProgressBar { background: transparent; border: 0; }
QProgressBar::chunk { background: $accent_line; border-radius: 2px; }
QSplitter::handle { width: 10px; background: transparent; }
QToolTip { background: $tooltip; color: $text_strong; border: 1px solid $border_hover; padding: 5px; }
"""
