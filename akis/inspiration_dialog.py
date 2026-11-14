"""İlham: creative video ideas, laid out like the template gallery (akis.template_dialog).

Cards on the left (a small picture in the idea's frame shape with its category's mark and colour),
a detail panel on the right (the opening line, the shot list, the ready edit request, the matching
template), category chips and a search box on top. The caller reads selection() -> (idea, action)
after exec(); action is 'prompt' or 'prompt+template'.

`language` ('tr' or 'en') translates the dialog's own texts; the ideas themselves are content and are
shown as written. Categories filter by their text, so they are not translated either.
"""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView,
                               QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from akis import i18n, theme
from akis import inspiration_service as service
from akis.template_dialog import DIALOG_STYLE, thumbnail

THUMB = QSize(132, 104)
# Each category's colour and mark on its cards and chips.
CATEGORY_LOOK = {
    'Hikâye anlatımı': ('#8f78ff', '📖'),
    'Ürün / tanıtım': ('#f0b657', '🛍'),
    'Eğitim': ('#4fc79a', '🎓'),
    'Vlog / günlük': ('#5fb3ff', '🎒'),
    'Trend / eğlence': ('#ff6fae', '🔥'),
    'Sinematik': ('#c9a46b', '🎬'),
}
EXTRA_STYLE = """
QLabel#ideaHook { background: $accent_bg; border: 1px solid $accent_line; border-radius: 10px; padding: 10px 12px; color: $text; }
QLabel#ideaPrompt { background: $field; border: 1px solid $border_strong; border-radius: 10px; padding: 10px 12px; color: $text_soft; }
QLabel#ideaStep { color: $text; }
QLabel#ideaNumber { background: $raised; border-radius: 10px; color: $accent_text; font-weight: 700; min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px; qproperty-alignment: AlignCenter; }
QLineEdit#ideaSearch { border-radius: 14px; padding: 6px 12px; }
QWidget#ideaRow { background: transparent; }
"""


def _frame_ratio(platform):
    """The frame shape an idea is made for, from its platform."""
    text = platform.lower()
    if 'youtube' in text and 'shorts' not in text:
        return 16, 9
    if 'instagram' in text:
        return 4, 5
    return 9, 16


def card_picture(idea) -> QPixmap:
    """The idea's card: its frame shape, its category mark in the middle, a hint of a timeline below."""
    colour, mark = CATEGORY_LOOK.get(idea.category, ('#8f78ff', '✦'))
    ratio_w, ratio_h = _frame_ratio(idea.platform)
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
    path.addRoundedRect(frame, 8, 8)
    tint = QColor(colour)
    tint.setAlpha(46)
    painter.fillPath(path, theme.color('video_bg'))
    painter.fillPath(path, tint)
    painter.setPen(QPen(QColor(colour), 1.4))
    painter.drawPath(path)
    font = QFont('Segoe UI Emoji')
    font.setPixelSize(int(min(box_w, box_h) * 0.36))
    painter.setFont(font)
    painter.setPen(theme.color('text'))
    painter.drawText(QRectF(frame.left(), frame.top(), box_w, box_h * 0.72), Qt.AlignmentFlag.AlignCenter, mark)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colour))
    bar_y = frame.bottom() - box_h * 0.2
    for x, width in ((0.12, 0.34), (0.5, 0.2), (0.74, 0.14)):
        painter.drawRoundedRect(QRectF(frame.left() + box_w * x, bar_y, box_w * width, max(4.0, box_h * 0.07)), 2, 2)
    painter.end()
    return pixmap


class InspirationDialog(QDialog):
    """Browse creative video ideas; the caller reads selection() -> (idea, action) after exec()."""

    def __init__(self, parent=None, language='tr'):
        super().__init__(parent)
        self.language = language
        t = self.tr_text
        self.setWindowTitle(t('İlham'))
        self.resize(1000, 720)
        self.setMinimumSize(780, 560)
        self.setStyleSheet(theme.css(DIALOG_STYLE + EXTRA_STYLE))
        self._action = None
        self._shown = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        heading = QLabel(t('Bir fikirle başlayın'))
        heading.setObjectName('tplHeading')
        top.addWidget(heading, 1)
        self.search = QLineEdit()
        self.search.setObjectName('ideaSearch')
        self.search.setPlaceholderText(t('Fikir ara…'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        top.addWidget(self.search)
        layout.addLayout(top)
        intro = QLabel(t('Yaratıcı video fikirleri: bir fikir seçin, kurgu isteğine yazın ve isterseniz uygun şablonu da uygulayın.'))
        intro.setObjectName('tplMuted')
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # The category combo is the source of truth (and what scripts use); the chips drive it.
        self.category = QComboBox()
        self.category.addItem(t('Tümü'))  # index 0 means every category, whatever it shows
        self.category.addItems(service.categories())
        self.category.hide()
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_buttons = []
        for index in range(self.category.count()):
            category = None if index == 0 else self.category.itemText(index)
            count = len(service.ideas(category))
            button = QPushButton(f'{self.category.itemText(index)}  {count}')
            button.setObjectName('tplFilter')
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.list.setGridSize(QSize(168, 206))
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setAccessibleName(t('Fikir listesi'))
        body.addWidget(self.list, 3)

        detail = QFrame()
        detail.setObjectName('tplDetail')
        self.detail_layout = dv = QVBoxLayout(detail)
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
        self.category_chip, self.platform_chip = QLabel(), QLabel()
        for chip in (self.category_chip, self.platform_chip):
            chip.setObjectName('tplChip')
            chips.addWidget(chip)
        chips.addStretch(1)
        dv.addLayout(chips)
        dv.addWidget(self.section('AÇILIŞ'))
        self.hook = QLabel()
        self.hook.setObjectName('ideaHook')
        self.hook.setWordWrap(True)
        dv.addWidget(self.hook)
        dv.addWidget(self.section('ÇEKİM LİSTESİ'))
        self.shots_box = QVBoxLayout()
        self.shots_box.setSpacing(6)
        dv.addLayout(self.shots_box)
        dv.addWidget(self.section('ÖNERİLEN KURGU İSTEĞİ'))
        self.prompt = QLabel()
        self.prompt.setObjectName('ideaPrompt')
        self.prompt.setWordWrap(True)
        self.prompt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dv.addWidget(self.prompt)
        self.template_title = self.section('UYGUN ŞABLON')
        dv.addWidget(self.template_title)
        template_row = QHBoxLayout()
        template_row.setSpacing(10)
        self.template_picture = QLabel()
        self.template_name = QLabel()
        self.template_name.setWordWrap(True)
        template_row.addWidget(self.template_picture)
        template_row.addWidget(self.template_name, 1)
        dv.addLayout(template_row)
        dv.addStretch(1)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_scroll.setWidget(detail)
        detail_scroll.setMinimumWidth(360)
        body.addWidget(detail_scroll, 2)
        layout.addLayout(body, 1)

        row = QHBoxLayout()
        row.setSpacing(10)
        hint = QLabel(t('Fikir, kurgu isteği kutusuna yazılır; videonuz değişmez.'))
        hint.setObjectName('tplMuted')
        hint.setWordWrap(True)
        row.addWidget(hint, 1)
        self.random_button = QPushButton(t('Rastgele fikir'))
        self.close_button = QPushButton(t('Kapat'))
        self.prompt_button = QPushButton(t('Fikri kurgu isteğine yaz'))
        self.template_button = QPushButton(t('Fikri yaz ve şablonunu uygula'))
        for button in (self.random_button, self.close_button, self.prompt_button):
            button.setObjectName('tplCancel')
            button.setAutoDefault(False)
        self.template_button.setObjectName('tplApply')
        self.template_button.setDefault(True)
        for button in (self.random_button, self.close_button, self.prompt_button, self.template_button):
            row.addWidget(button)
        layout.addLayout(row)

        self.filter_group.idClicked.connect(self.category.setCurrentIndex)
        self.category.currentIndexChanged.connect(self._category_changed)
        self.search.textChanged.connect(self.refresh)
        self.list.currentRowChanged.connect(self.changed)
        self.list.itemDoubleClicked.connect(lambda _item: self.finish('prompt'))
        self.random_button.clicked.connect(self.pick_random)
        self.prompt_button.clicked.connect(lambda: self.finish('prompt'))
        self.template_button.clicked.connect(lambda: self.finish('prompt+template'))
        self.close_button.clicked.connect(self.reject)
        self.refresh()

    def tr_text(self, text):
        return i18n.translate(text, self.language)

    def section(self, text):
        label = QLabel(self.tr_text(text))
        label.setObjectName('tplSection')
        return label

    def _category_changed(self, index):
        button = self.filter_group.button(index)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self.refresh()

    def refresh(self, *_):
        category = None if self.category.currentIndex() <= 0 else self.category.currentText()
        self._shown = service.ideas(category, self.search.text())
        self.list.clear()
        for idea in self._shown:
            item = QListWidgetItem(QIcon(card_picture(idea)), f'{idea.title}\n{idea.platform}')
            item.setToolTip(idea.hook)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.list.addItem(item)
        if self._shown:
            self.list.setCurrentRow(0)
        else:
            self.changed(-1)

    def current_idea(self):
        row = self.list.currentRow()
        return self._shown[row] if 0 <= row < len(self._shown) else None

    def _clear_shots(self):
        while self.shots_box.count():
            widget = self.shots_box.takeAt(0).widget()
            if widget is not None:      # off screen at once: a deferred delete would leave it painted meanwhile
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def changed(self, index):
        idea = self.current_idea()
        self.prompt_button.setEnabled(idea is not None)
        template = service.template_for(idea) if idea else None
        self.template_button.setEnabled(template is not None)
        self._clear_shots()
        if idea is None:
            self.name.setText(self.tr_text('Bu aramaya uygun fikir bulunamadı.'))
            for widget in (self.summary, self.hook, self.prompt, self.template_name):
                widget.clear()
            self.category_chip.hide()
            self.platform_chip.hide()
            self.template_title.hide()
            self.template_picture.clear()
            return
        colour = CATEGORY_LOOK.get(idea.category, ('#8f78ff', '✦'))[0]
        self.name.setText(idea.title)
        self.summary.setText(idea.description)
        self.category_chip.setText(idea.category)
        self.category_chip.setStyleSheet(f'border: 1px solid {colour};')
        self.platform_chip.setText(idea.platform)
        self.category_chip.show()
        self.platform_chip.show()
        self.hook.setText(idea.hook)
        for number, shot in enumerate(idea.shots, 1):
            line = QHBoxLayout()
            line.setSpacing(8)
            badge = QLabel(str(number))
            badge.setObjectName('ideaNumber')
            text = QLabel(shot)
            text.setObjectName('ideaStep')
            text.setWordWrap(True)
            line.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            line.addWidget(text, 1)
            holder = QWidget()
            holder.setObjectName('ideaRow')
            holder.setLayout(line)
            line.setContentsMargins(0, 0, 0, 0)
            self.shots_box.addWidget(holder)
        self.prompt.setText(idea.prompt)
        self.template_title.setVisible(template is not None)
        if template is not None:
            self.template_picture.setPixmap(thumbnail(template).scaled(
                66, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.template_name.setText(f'<b>{i18n.translate(template.name, self.language)}</b><br>'
                                       f'<span style="color:{theme.hex_("muted")}">{template.ratio}</span>')
        else:
            self.template_picture.clear()
            self.template_name.clear()

    def pick_random(self):
        category = None if self.category.currentIndex() <= 0 else self.category.currentText()
        idea = service.random_idea(category)
        if idea is None:
            return
        self.search.clear()
        if idea in self._shown:
            self.list.setCurrentRow(self._shown.index(idea))
            self.list.scrollToItem(self.list.currentItem())

    def finish(self, action):
        if self.current_idea() is None:
            return
        if action == 'prompt+template' and service.template_for(self.current_idea()) is None:
            return
        self._action = action
        self.accept()

    def selection(self):
        return self.current_idea(), self._action
