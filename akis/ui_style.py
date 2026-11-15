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
QPushButton { border: 1px solid $button_border; border-radius: 9px; padding: 8px 12px; background: $button; text-align: left; }
QPushButton:hover { background: $button_hover; border-color: $border_hover; }
QPushButton[nav='true'] { background: transparent; color: $text_soft; padding: 10px 12px; }
QPushButton[nav='true']:hover, QPushButton[active='true'] { background: $accent_bg; color: $text_strong; }
QPushButton#primary, QPushButton#primaryLarge { background: $accent; color: white; font-weight: 700; text-align: center; }
QPushButton#primary:hover, QPushButton#primaryLarge:hover { background: $accent_hover; }
QPushButton#primaryLarge { padding: 13px; }
QPushButton#secondary { border: 1px solid $border_strong; background: $raised; text-align: center; }
QPushButton#ghost { background: transparent; color: $text_soft; text-align: center; }
QPushButton#roundButton { border-radius: 20px; background: $accent; text-align: center; padding: 0; }
QPushButton[nav='true'], QPushButton[nav='true']:hover, QPushButton#ghost, QPushButton#versionTag, QPushButton#primary,
QPushButton#primary:hover, QPushButton#primaryLarge, QPushButton#primaryLarge:hover, QPushButton#roundButton { border: 0; }
QPushButton#secondary:hover { border-color: $border_hover; }
QFrame#segment { background: $raised; border: 1px solid $border; border-radius: 9px; }
QPushButton#segmentButton { background: transparent; border: 0; border-radius: 7px; padding: 6px 4px; color: $muted; text-align: center; font-weight: 600; }
QPushButton#segmentButton:hover { color: $text; background: $button_hover; }
QPushButton#segmentButton:checked { background: $accent_bg; color: $accent_text; }
QWidget#inspectorPage { background: $surface; }
QFrame#editor { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#privacyCard { background: $panel; border: 1px solid $border; border-radius: 10px; }
QLabel#localTitle { color: $success; font-weight: 600; }
QPushButton#versionTag { background: transparent; color: $faint; font-size: 11px; padding: 4px 2px; text-align: left; }
QPushButton#versionTag:hover { color: $accent_text; text-decoration: underline; }
QVideoWidget#video { background: $video_bg; border-radius: 10px; }
QLineEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox { background: $field; border: 1px solid $border_strong; border-radius: 8px; padding: 8px; selection-background-color: $accent; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QAbstractSpinBox:focus { border: 1px solid $accent_line; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: 0; background: transparent; }
QComboBox::down-arrow { image: url($down_mark); width: 11px; height: 11px; }
QAbstractSpinBox { padding-right: 24px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { subcontrol-origin: border; width: 22px; border: 0; background: transparent; }
QAbstractSpinBox::up-button { subcontrol-position: top right; }
QAbstractSpinBox::down-button { subcontrol-position: bottom right; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background: $button_hover; border-radius: 6px; }
QAbstractSpinBox::up-arrow { image: url($up_mark); width: 9px; height: 9px; }
QAbstractSpinBox::down-arrow { image: url($down_mark); width: 9px; height: 9px; }
QCheckBox, QRadioButton { spacing: 9px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QRadioButton::indicator { width: 14px; height: 14px; }
QCheckBox::indicator { border: 1px solid $border_hover; border-radius: 5px; background: $field; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $accent_line; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($check_mark); }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { background: $disabled; border-color: $border; }
QCheckBox::indicator:checked:disabled { background: $disabled_text; border-color: $disabled_text; }
QRadioButton::indicator { border: 1px solid $border_hover; border-radius: 8px; background: $field; }
QRadioButton::indicator:checked { border-color: $accent; background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5, stop: 0 white, stop: 0.38 white, stop: 0.44 $accent, stop: 1 $accent); }
QPlainTextEdit { line-height: 1.35; }
QDialog { background: $surface; }
QListWidget, QTableWidget, QTreeWidget { background: $field; border: 1px solid $border_strong; border-radius: 8px; outline: 0; }
QListWidget::item, QTableWidget::item { padding: 4px; }
QListWidget::item:selected, QTableWidget::item:selected { background: $accent_bg; color: $text_strong; }
QHeaderView::section { background: $raised; color: $muted; border: 0; border-bottom: 1px solid $border; padding: 6px 8px; font-weight: 600; }
QTableCornerButton::section { background: $raised; border: 0; }
QListWidget#mediaList { background: transparent; border: 0; outline: 0; }
QListWidget#mediaList::item { background: $panel; border-radius: 8px; padding: 9px; margin-bottom: 5px; }
QTabWidget::pane { background: $surface; border: 1px solid $border; border-radius: 12px; top: -1px; }
QTabBar::tab { background: transparent; color: $muted; padding: 10px 12px; }
QTabBar::tab:selected { color: $text_strong; border-bottom: 2px solid $accent_line; }
QScrollArea { background: transparent; border: 0; }
QWidget#sidebarInner { background: $surface; }
QComboBox QAbstractItemView { background: $field; color: $text; border: 1px solid $border_strong; selection-background-color: $accent_bg; selection-color: $text_strong; outline: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; }
QScrollBar::handle:horizontal { background: $border_strong; border-radius: 4px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
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
