from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QLabel, QComboBox, QPushButton,
                               QLineEdit, QTextBrowser)
from PySide6.QtCore import Qt
from akis import i18n
from akis import inspiration_service as service


class InspirationDialog(QDialog):
    """Browse creative video ideas; the caller reads selection() -> (idea, action) after exec().

    `language` ('tr' or 'en') translates the dialog's own texts; the ideas themselves are content and are
    shown as written. Categories filter by their text, so they are not translated either.
    """

    def __init__(self, parent=None, language='tr'):
        super().__init__(parent)
        self.language = language
        t = self.tr_text
        self.setWindowTitle(t('İlham'))
        self.resize(760, 600)
        self._action = None
        self._shown = []
        layout = QVBoxLayout(self)
        intro = QLabel(t('Yaratıcı video fikirleri: bir fikir seçin, kurgu isteğine yazın ve isterseniz uygun şablonu da uygulayın.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        filters = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItem(t('Tümü'))  # index 0 means every category, whatever it shows
        self.category.addItems(service.categories())
        self.search = QLineEdit()
        self.search.setPlaceholderText(t('Fikir ara…'))
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.category)
        filters.addWidget(self.search, 1)
        layout.addLayout(filters)
        self.list = QListWidget()
        self.list.setMaximumHeight(190)
        layout.addWidget(self.list)
        self.details = QTextBrowser()
        layout.addWidget(self.details, 1)
        row = QHBoxLayout()
        self.random_button = QPushButton(t('Rastgele fikir'))
        self.prompt_button = QPushButton(t('Fikri kurgu isteğine yaz'))
        self.template_button = QPushButton(t('Fikri yaz ve şablonunu uygula'))
        self.close_button = QPushButton(t('Kapat'))
        for button in (self.random_button, self.prompt_button, self.template_button):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.category.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.list.currentRowChanged.connect(self.changed)
        self.random_button.clicked.connect(self.pick_random)
        self.prompt_button.clicked.connect(lambda: self.finish('prompt'))
        self.template_button.clicked.connect(lambda: self.finish('prompt+template'))
        self.close_button.clicked.connect(self.reject)
        self.refresh()

    def tr_text(self, text):
        return i18n.translate(text, self.language)

    def refresh(self, *_):
        category = None if self.category.currentIndex() <= 0 else self.category.currentText()
        self._shown = service.ideas(category, self.search.text())
        self.list.clear()
        self.list.addItems([f'{i.title}  ·  {i.category}  ·  {i.platform}' for i in self._shown])
        if self._shown:
            self.list.setCurrentRow(0)
        else:
            self.changed(-1)

    def current_idea(self):
        row = self.list.currentRow()
        return self._shown[row] if 0 <= row < len(self._shown) else None

    def changed(self, index):
        idea = self.current_idea()
        self.prompt_button.setEnabled(idea is not None)
        self.template_button.setEnabled(idea is not None and service.template_for(idea) is not None)
        if idea is None:
            self.details.setHtml(f"<p>{self.tr_text('Bu aramaya uygun fikir bulunamadı.')}</p>")
            return
        esc = lambda text: str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        t = lambda text: esc(self.tr_text(text))
        template = service.template_for(idea)
        shots = ''.join(f'<li>{esc(s)}</li>' for s in idea.shots)
        self.details.setHtml(
            f'<h3>{esc(idea.title)}</h3><p><i>{esc(idea.category)} · {esc(idea.platform)}</i></p>'
            f'<p><b>{t("Açılış:")}</b> {esc(idea.hook)}</p><p>{esc(idea.description)}</p>'
            f'<p><b>{t("Çekim listesi")}</b></p><ol>{shots}</ol>'
            f'<p><b>{t("Önerilen kurgu isteği")}</b><br>{esc(idea.prompt)}</p>'
            + (f'<p><b>{t("Uygun şablon:")}</b> {esc(i18n.translate(template.name, self.language))}</p>'
               if template else ''))

    def pick_random(self):
        category = None if self.category.currentIndex() <= 0 else self.category.currentText()
        idea = service.random_idea(category)
        if idea is None:
            return
        self.search.clear()
        if idea in self._shown:
            self.list.setCurrentRow(self._shown.index(idea))

    def finish(self, action):
        if self.current_idea() is None:
            return
        self._action = action
        self.accept()

    def selection(self):
        return self.current_idea(), self._action
