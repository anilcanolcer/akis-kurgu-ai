"""Şablonlar: pick a ready-made project structure, see exactly what it adds, adjust it and apply it."""
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QListView, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout)

from akis import i18n, theme
from akis.template_service import TEMPLATES, STYLES, TEMPOS, TITLE_SECONDS, missing_tracks

def kind_color(kind):
    return theme.hex_('kind_' + kind)


KIND_LABELS = {'video': 'Video izi', 'audio': 'Ses izi', 'text': 'Metin izi'}
FILTERS = (('Tümü', None), ('Dikey 9:16', '9:16'), ('Yatay 16:9', '16:9'), ('Kare 1:1', '1:1'))
THUMB = QSize(132, 104)

DIALOG_STYLE = """
QLabel#tplHeading { font-size: 20px; font-weight: 700; }
QLabel#tplName { font-size: 17px; font-weight: 700; }
QLabel#tplMuted { color: $muted; }
QLabel#tplSection { color: $muted; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 6px; }
QLabel#tplChip { background: $raised; border: 1px solid $border_strong; border-radius: 10px; padding: 3px 9px; color: $text_soft; font-size: 12px; }
QLabel#tplNotice { background: $notice_bg; border: 1px solid $notice_border; border-radius: 8px; padding: 8px 10px; color: $notice_text; }
QFrame#tplDetail { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#tplDetail QLabel { background: transparent; }
QFrame#tplDetail QLabel#tplChip { background: $raised; }
QFrame#tplDetail QLabel#tplNotice { background: $notice_bg; }
QPushButton#tplFilter { background: $field; border: 1px solid $border_strong; border-radius: 14px; padding: 6px 13px; color: $text_soft; text-align: center; }
QPushButton#tplFilter:hover { background: $button; }
QPushButton#tplFilter:checked { background: $accent_bg; border: 1px solid $accent; color: $text_strong; }
QPushButton#tplFilter:focus, QPushButton#tplCancel:focus { border: 1px solid $accent_text; }
QPushButton#tplApply { background: $accent; color: white; font-weight: 700; text-align: center; padding: 10px 20px; border: 1px solid $accent; }
QPushButton#tplApply:hover { background: $accent_hover; }
QPushButton#tplApply:focus { border: 1px solid $accent_text; }
QPushButton#tplApply:disabled { background: $disabled; border: 1px solid $disabled; color: $disabled_text; }
QPushButton#tplCancel { background: $raised; border: 1px solid $border_strong; text-align: center; padding: 10px 18px; }
QListWidget#tplList { background: transparent; border: 0; outline: 0; }
QListWidget#tplList::item { background: $panel; border: 1px solid $border; border-radius: 10px; padding: 8px 4px; margin: 4px; color: $text; }
QListWidget#tplList::item:hover { background: $button_hover; border: 1px solid $border_hover; }
QListWidget#tplList::item:selected { background: $accent_bg; border: 2px solid $accent_line; color: $text_strong; }
"""


def thumbnail(template) -> QPixmap:
    """A small picture of the template: its frame shape with one bar per track, coloured by kind."""
    ratio_w, ratio_h = (int(part) for part in template.ratio.split(':'))
    pixmap = QPixmap(THUMB)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    box_h = THUMB.height() - 12
    box_w = box_h * ratio_w / ratio_h
    if box_w > THUMB.width() - 12:
        box_w = THUMB.width() - 12
        box_h = box_w * ratio_h / ratio_w
    frame = QRectF((THUMB.width() - box_w) / 2, (THUMB.height() - box_h) / 2, box_w, box_h)
    path = QPainterPath()
    path.addRoundedRect(frame, 7, 7)
    painter.fillPath(path, theme.color('video_bg'))
    painter.setPen(QPen(theme.color('border_hover'), 1.2))
    painter.drawPath(path)
    bars = len(template.tracks)
    bar_h = min(9.0, (box_h - 16) / (bars * 1.6))
    y = frame.bottom() - 8 - bars * bar_h * 1.6 + bar_h * 0.6
    widths = (0.86, 0.6, 0.78, 0.46)
    painter.setPen(Qt.PenStyle.NoPen)
    for index, (kind, _name) in enumerate(template.tracks):
        painter.setBrush(QColor(kind_color(kind)))
        painter.drawRoundedRect(QRectF(frame.left() + 7, y, (box_w - 14) * widths[index % len(widths)], bar_h), 3, 3)
        y += bar_h * 1.6
    painter.end()
    return pixmap


class TemplateDialog(QDialog):
    """`selection()` -> (template, style key, tempo key) after exec().

    exec() returns SAVED when the user asked for their own templates instead (akis.saved_templates_dialog).

    `language` is 'tr' or 'en'. `current_aspect` (a bare ratio such as '16:9') and `timeline` describe the
    open project, so the dialog can say what applying the template changes in it.
    """

    SAVED = 2  # exec() result: open “Şablonlarım”

    def __init__(self, parent=None, language: str = 'tr', current_aspect: str = '', timeline=None):
        super().__init__(parent)
        self.language = language
        self.current_aspect = current_aspect
        self.timeline = timeline
        self.setWindowTitle(self.tr_('Şablonlar'))
        self.resize(960, 700)
        self.setMinimumSize(760, 540)
        self.setStyleSheet(theme.css(DIALOG_STYLE))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        heading = QLabel(self.tr_('Bir şablonla başlayın'))
        heading.setObjectName('tplHeading')
        layout.addWidget(heading)
        intro = QLabel(self.tr_('Şablon; projenize hazır izler, tuval oranı, renk stili ve tempo ekler. '
                                'Medyanızı izlere siz yerleştirirsiniz; mevcut klipleriniz değişmez.'))
        intro.setObjectName('tplMuted')
        intro.setWordWrap(True)
        layout.addWidget(intro)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_buttons = []
        for index, (text, ratio) in enumerate(FILTERS):
            count = sum(1 for t in TEMPLATES if ratio in (None, t.ratio))
            button = QPushButton(f'{self.tr_(text)}  {count}')
            button.setObjectName('tplFilter')
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty('ratio', ratio)
            self.filter_group.addButton(button, index)
            self.filter_buttons.append(button)
            filters.addWidget(button)
        filters.addStretch(1)
        layout.addLayout(filters)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.list = QListWidget()
        self.list.setObjectName('tplList')
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(THUMB)
        self.list.setGridSize(QSize(168, 198))
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setAccessibleName(self.tr_('Şablon listesi'))
        body.addWidget(self.list, 3)

        detail = QFrame()
        detail.setObjectName('tplDetail')
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(18, 16, 18, 16)
        dv.setSpacing(8)
        self.name = QLabel()
        self.name.setObjectName('tplName')
        self.name.setWordWrap(True)
        dv.addWidget(self.name)
        self.summary = QLabel()
        self.summary.setObjectName('tplMuted')
        self.summary.setWordWrap(True)
        dv.addWidget(self.summary)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.ratio_chip, self.length_chip = QLabel(), QLabel()
        for chip in (self.ratio_chip, self.length_chip):
            chip.setObjectName('tplChip')
            chips.addWidget(chip)
        chips.addStretch(1)
        dv.addLayout(chips)
        self.platforms = QLabel()
        self.platforms.setObjectName('tplMuted')
        self.platforms.setWordWrap(True)
        dv.addWidget(self.platforms)
        dv.addWidget(self.section('PROJENİZE EKLENECEKLER'))
        self.contents = QLabel()
        self.contents.setTextFormat(Qt.TextFormat.RichText)
        self.contents.setWordWrap(True)
        dv.addWidget(self.contents)
        dv.addWidget(self.section('UYARLAYIN'))
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.style = QComboBox()
        for key in STYLES:
            self.style.addItem(self.tr_(key), key)
        self.style.setToolTip(self.tr_('Parlaklık, kontrast ve doygunluğu ayarlar; sonra Düzenle sekmesinden değiştirebilirsiniz.'))
        self.tempo = QComboBox()
        for key, speed in TEMPOS.items():
            self.tempo.addItem(f'{self.tr_(key)}  ·  {speed}', key)
        self.tempo.setToolTip(self.tr_('Tüm projenin oynatma hızıdır; 1.00× özgün hızdır.'))
        style_label, tempo_label = QLabel(self.tr_('Renk stili')), QLabel(self.tr_('Oynatma hızı'))
        style_label.setBuddy(self.style)
        tempo_label.setBuddy(self.tempo)
        form.addRow(style_label, self.style)
        form.addRow(tempo_label, self.tempo)
        dv.addLayout(form)
        self.notice = QLabel()
        self.notice.setObjectName('tplNotice')
        self.notice.setWordWrap(True)
        dv.addWidget(self.notice)
        dv.addStretch(1)
        # Scrolls instead of clipping when the window is small or a translation runs long.
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_scroll.setMinimumWidth(350)
        detail_scroll.setWidget(detail)
        body.addWidget(detail_scroll, 2)
        layout.addLayout(body, 1)

        footer = QHBoxLayout()
        hint = QLabel(self.tr_('Tek adımda uygulanır; beğenmezseniz Ctrl+Z ile geri alabilirsiniz.'))
        hint.setObjectName('tplMuted')
        footer.addWidget(hint, 1)
        self.cancel_button = QPushButton(self.tr_('İptal'))
        self.cancel_button.setObjectName('tplCancel')
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button = QPushButton(self.tr_('Şablonu uygula'))
        self.apply_button.setObjectName('tplApply')
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.accept)
        self.saved_button = QPushButton(self.tr_('Şablonlarım…'))
        self.saved_button.setObjectName('tplCancel')
        self.saved_button.setAutoDefault(False)
        self.saved_button.setToolTip(self.tr_('Kendi projelerinizden kaydettiğiniz şablonlar.'))
        self.saved_button.clicked.connect(lambda: self.done(self.SAVED))
        footer.addWidget(self.saved_button)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.apply_button)
        layout.addLayout(footer)

        self.filter_group.idClicked.connect(lambda _id: self.refresh())
        self.list.currentItemChanged.connect(lambda *_: self.changed())
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.refresh()
        self.list.setFocus()

    def tr_(self, text: str) -> str:
        return i18n.translate(text, self.language)

    def section(self, text: str) -> QLabel:
        label = QLabel(self.tr_(text))
        label.setObjectName('tplSection')
        return label

    def length_text(self, seconds: int) -> str:
        if seconds < 60:
            return self.tr_('~{n} sn').format(n=seconds)
        return self.tr_('~{n} dk').format(n=f'{seconds / 60:g}')

    def refresh(self):
        """Fill the grid for the chosen format filter, keeping the selected template when it is still shown."""
        keep = self.current_template()
        ratio = self.filter_group.checkedButton().property('ratio')
        self.list.blockSignals(True)
        self.list.clear()
        for index, template in enumerate(TEMPLATES):
            if ratio not in (None, template.ratio):
                continue
            icon, picture = QIcon(), thumbnail(template)
            for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
                icon.addPixmap(picture, mode)  # same picture in every state: no selection tint over it
            item = QListWidgetItem(icon,
                                   f'{self.tr_(template.name)}\n{template.ratio} · {self.length_text(template.seconds)}')
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            item.setToolTip(self.tr_(template.summary))
            self.list.addItem(item)
            if template is keep:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.changed()

    def current_template(self):
        item = self.list.currentItem()
        return TEMPLATES[item.data(Qt.ItemDataRole.UserRole)] if item is not None else None

    def changed(self):
        t = self.current_template()
        self.apply_button.setEnabled(t is not None)
        if t is None:
            return
        self.name.setText(self.tr_(t.name))
        self.summary.setText(self.tr_(t.summary))
        self.ratio_chip.setText(t.ratio)
        self.length_chip.setText(self.length_text(t.seconds))
        self.platforms.setText(self.tr_('Uygun olduğu yerler: {places}').format(places=self.tr_(t.platforms)))
        self.platforms.setVisible(bool(t.platforms))
        existing = set() if self.timeline is None else set(t.tracks) - set(missing_tracks(self.timeline, t))
        rows = []
        for kind, name in t.tracks:
            note = f" <span style='color:{theme.hex_("faint")}'>· {self.tr_('projede var')}</span>" if (kind, name) in existing else ''
            rows.append(f"<tr><td style='color:{kind_color(kind)}; padding-right:8px'>■</td>"
                        f"<td style='padding-right:10px'>{self.tr_(name)}{note}</td>"
                        f"<td style='color:{theme.hex_("muted")}'>{self.tr_(KIND_LABELS[kind])}</td></tr>")
        title = self.tr_('Düzenlenebilir başlık: “{title}” ({n} sn)').format(title=self.tr_(t.title), n=TITLE_SECONDS)
        self.contents.setText(f"<table cellspacing='0' cellpadding='2'>{''.join(rows)}</table>"
                              f"<p style='margin-top:6px'><span style='color:{kind_color("text")}'>■</span>&nbsp; {title}</p>")
        self.style.setCurrentIndex(self.style.findData(t.style))
        self.tempo.setCurrentIndex(self.tempo.findData(t.tempo))
        if self.current_aspect and self.current_aspect != t.ratio:
            self.notice.setText(self.tr_('Tuval oranı {old} yerine {new} olacak.').format(old=self.current_aspect, new=t.ratio))
            self.notice.show()
        else:
            self.notice.hide()

    def selection(self):
        return self.current_template(), self.style.currentData(), self.tempo.currentData()
