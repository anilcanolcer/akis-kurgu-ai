"""Hikâye Stüdyosu: premise → story bible → scenes → image → video → project media.

Self-contained (no import of main.py). The host passes:
    api_key      callable returning the Gemini API key (or a plain string); read on the GUI thread per call
    output_dir   folder (or callable returning one) where generated images/videos are written
    add_media    callable(path: str) called on the GUI thread with an existing .png/.jpg/.webp/.mp4 file;
                 may return False to report that the file was not added
    default_aspect  e.g. '16:9' or the editor's '9:16 · Reels / Shorts' (only the ratio part is used)
"""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QSplitter, QTabWidget,
                               QVBoxLayout, QWidget)

from akis import gemini_api, story_service as ss
from akis.story_workers import CallWorker, ImageWorker, TextWorker, VideoWorker

TITLE = 'Hikâye Stüdyosu'
UNSAVED_QUESTION = 'Hikâyede kaydedilmemiş değişiklikler var (üretilen sahneler dahil). Kaydedilsin mi?'
DELETE_SCENE_QUESTION = '"{title}" sahnesi silinsin mi? Bu işlem geri alınamaz.'
REPLACE_BIBLE_QUESTION = ('Rehberdeki karakterler ve olay örgüsü yeni üretilen rehberle değiştirilecek; elle yaptığınız '
                          'düzenlemeler kaybolur. Devam edilsin mi?')


def _combo(items, editable=False, data=None):
    combo = QComboBox()
    combo.setEditable(editable)
    for index, item in enumerate(items):
        combo.addItem(item, data[index] if data else item)
    return combo


def _aspect_part(value):
    text = str(value or '').split(' ')[0].strip()
    return text if text in gemini_api.ASPECT_RATIOS else '16:9'


class StoryDialog(QDialog):
    def __init__(self, parent=None, *, api_key, output_dir, add_media, default_aspect='16:9',
                 transport=None, file_getter=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.setModal(False)
        self.resize(1100, 760)
        self._api_key, self._output_dir, self._add_media = api_key, output_dir, add_media
        self._transport, self._file_getter = transport, file_getter
        self.state = ss.StoryState()
        self.story_path = ''
        self.current_id = ''
        self.worker = None
        self._loading = False
        self._closing = False
        self._close_approved = False   # confirm_close() already answered for the close in progress
        self._saved_snapshot = None
        self.style_reference = ''
        self.character_references = []
        self.last_usage = ''

        root = QVBoxLayout(self)
        root.addLayout(self._model_row())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._idea_tab(), 'Fikir ve rehber')
        self.tabs.addTab(self._scene_tab(), 'Sahneler')
        self.tabs.addTab(self._media_tab(), 'Görsel ve video')
        root.addWidget(self.tabs, 1)
        root.addLayout(self._status_row())
        aspect = _aspect_part(default_aspect)
        self.image_aspect.setCurrentText(aspect)
        width, height = (int(x) for x in aspect.split(':'))
        self.video_aspect.setCurrentText('9:16' if height > width else '16:9')
        self.refresh_bible_editor()
        self.refresh_scene_list()
        self.update_cost_line()
        self.set_busy(False)
        self.mark_clean()

    # ------------------------------------------------------------ unsaved changes

    def _snapshot(self):
        """The story as it would be saved, plus the guide editor's text (edits not yet applied count too)."""
        self.store_scene()
        self.read_idea_fields()
        return json.dumps([self.state.to_dict(), self.bible_editor.toPlainText()], ensure_ascii=False,
                          sort_keys=True, default=str)

    def mark_clean(self):
        self._saved_snapshot = self._snapshot()

    def is_dirty(self):
        return self._snapshot() != self._saved_snapshot

    def can_ask(self):
        """Questions need someone to answer them: never on the offscreen platform (tests, scripted runs) or
        while neither this dialog nor its parent window is on screen."""
        if QGuiApplication.platformName() == 'offscreen':
            return False
        parent = self.parentWidget()
        return self.isVisible() or (parent is not None and parent.isVisible())

    def ask(self, text, buttons, default):
        """One modal question; returns the StandardButton chosen. Tests replace this."""
        return QMessageBox.question(self, TITLE, text, buttons, default)

    def confirm(self, text):
        """Yes/No question; True without asking when nobody can answer (see can_ask)."""
        if not self.can_ask():
            return True
        yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
        return self.ask(text, yes | no, no) == yes

    def maybe_save(self):
        """Before the story is replaced or closed: offer to save unsaved changes.

        Returns True when it is fine to go on (nothing unsaved, saved, deliberately discarded, or nobody can
        be asked), False when the user cancelled or saving failed.
        """
        if not self.is_dirty() or not self.can_ask():
            return True
        buttons = QMessageBox.StandardButton
        answer = self.ask(UNSAVED_QUESTION, buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        if answer == buttons.Save:
            return self.save_story()
        if answer == buttons.Discard:
            self.mark_clean()  # the user chose to drop them: do not ask again for the same changes
            return True
        return False

    def confirm_close(self):
        """For the host before it closes (e.g. at application exit): False means stay open.

        The answer covers the next closeEvent/reject, so the question is not asked twice."""
        if self._close_approved:
            return True
        self._close_approved = self.maybe_save()
        return self._close_approved

    # ------------------------------------------------------------ layout

    def _model_row(self):
        row = QHBoxLayout()
        self.text_model = _combo(gemini_api.TEXT_MODELS, editable=True)
        self.quality = _combo(['Taslak', 'Final'], data=['draft', 'final'])
        self.quality.setToolTip('\n'.join(f'{a}: {b} ({c}) — {d}' for a, b, c, d in ss.ROUTING_TABLE))
        self.image_model = _combo(gemini_api.IMAGE_MODELS, editable=True)
        self.video_model = _combo(gemini_api.VIDEO_MODELS, editable=True)
        self.check_models_button = QPushButton('Modelleri denetle')
        self.check_models_button.clicked.connect(self.check_models)
        for label, widget in (('Metin', self.text_model), ('Kalite', self.quality), ('Görsel', self.image_model),
                              ('Video', self.video_model)):
            row.addWidget(QLabel(label))
            row.addWidget(widget, 1)
        row.addWidget(self.check_models_button)
        return row

    def _idea_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.premise = QPlainTextEdit()
        self.premise.setPlaceholderText('Hikâyenin ana fikri: kim, ne istiyor, ne engel oluyor, nerede geçiyor…')
        self.premise.setMaximumHeight(110)
        self.style = _combo([p.name for p in ss.STYLE_PROFILES.values()], data=list(ss.STYLE_PROFILES))
        self.pov = _combo(ss.POV_CHOICES)
        self.tense = _combo(ss.TENSE_CHOICES)
        self.genre = QLineEdit()
        self.genre.setPlaceholderText('Tür (ör. dram, polisiye, fantastik)')
        form.addRow('Ana fikir', self.premise)
        form.addRow('Üslup', self.style)
        form.addRow('Anlatıcı', self.pov)
        form.addRow('Anlatı zamanı', self.tense)
        form.addRow('Tür', self.genre)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.bible_button = QPushButton('Rehberi üret')
        self.bible_button.clicked.connect(self.generate_bible)
        self.outline_button = QPushButton('Taslak çıkar')
        self.outline_button.clicked.connect(self.generate_outline)
        self.apply_bible_button = QPushButton('Rehberdeki değişiklikleri uygula')
        self.apply_bible_button.clicked.connect(self.apply_bible_editor)
        for button in (self.bible_button, self.outline_button, self.apply_bible_button):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addWidget(QLabel('Hikâye rehberi (JSON; karakterlerin "visual" alanı görsellerde aynen kullanılır)'))
        self.bible_editor = QPlainTextEdit()
        self.bible_editor.setProperty('i18n_skip', True)
        layout.addWidget(self.bible_editor, 1)
        return page

    def _scene_tab(self):
        splitter = QSplitter()
        left = QWidget()
        lv = QVBoxLayout(left)
        self.scene_list = QListWidget()
        self.scene_list.setProperty('i18n_skip', True)
        self.scene_list.currentRowChanged.connect(self.select_scene)
        lv.addWidget(self.scene_list, 1)
        self.add_scene_button = QPushButton('Boş sahne ekle')
        self.add_scene_button.clicked.connect(self.add_empty_scene)
        self.delete_scene_button = QPushButton('Sahneyi sil')
        self.delete_scene_button.clicked.connect(self.delete_scene)
        self.split_button = QPushButton('Metni sahnelere böl')
        self.split_button.setToolTip('Seçili sahnenin metnini model yardımıyla sahnelere ayırır.')
        self.split_button.clicked.connect(self.split_text)
        for button in (self.add_scene_button, self.delete_scene_button, self.split_button):
            lv.addWidget(button)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        self.scene_title = QLineEdit()
        self.scene_title.setPlaceholderText('Sahne başlığı')
        self.scene_title.setProperty('i18n_skip', True)
        self.scene_title.textChanged.connect(self.store_scene)
        self.scene_text = QPlainTextEdit()
        self.scene_text.setProperty('i18n_skip', True)
        self.scene_text.textChanged.connect(self.store_scene)
        self.instruction = QLineEdit()
        self.instruction.setPlaceholderText('Talimat (isteğe bağlı): ne olsun, neye odaklanılsın…')
        rv.addWidget(self.scene_title)
        rv.addWidget(self.scene_text, 1)
        rv.addWidget(self.instruction)
        row = QHBoxLayout()
        row.addWidget(QLabel('Kelime'))
        self.words = QSpinBox()
        self.words.setRange(100, 4000)
        self.words.setSingleStep(100)
        self.words.setValue(ss.DEFAULT_SCENE_WORDS)
        row.addWidget(self.words)
        self.write_button = QPushButton('Sahneyi yaz')
        self.write_button.setToolTip('Hikâyenin sonuna yeni bir sahne yazar.')
        self.write_button.clicked.connect(self.write_scene)
        self.continue_button = QPushButton('Devam et')
        self.continue_button.clicked.connect(self.continue_scene)
        self.rewrite_mode = _combo(['Yeniden yaz', 'Uzat', 'Kısalt'], data=['rewrite', 'extend', 'shorten'])
        self.rewrite_button = QPushButton('Yeniden yaz')
        self.rewrite_button.clicked.connect(self.rewrite_scene)
        self.auto_memory = QCheckBox('Sonra özeti güncelle')
        self.auto_memory.setChecked(True)
        for widget in (self.write_button, self.continue_button, self.rewrite_mode, self.rewrite_button, self.auto_memory):
            row.addWidget(widget)
        row.addStretch()
        rv.addLayout(row)
        splitter.addWidget(right)
        splitter.setSizes([260, 800])
        return splitter

    def _media_tab(self):
        page = QWidget()
        grid = QGridLayout(page)
        prompts = QGroupBox('İstemler (İngilizce; üretmeden önce düzenleyebilirsiniz)')
        pv = QVBoxLayout(prompts)
        self.visual_prompt = QPlainTextEdit()
        self.visual_prompt.setProperty('i18n_skip', True)
        self.visual_prompt.textChanged.connect(self.store_scene)
        self.motion_prompt = QPlainTextEdit()
        self.motion_prompt.setProperty('i18n_skip', True)
        self.motion_prompt.setMaximumHeight(80)
        self.motion_prompt.textChanged.connect(self.store_scene)
        self.visual_button = QPushButton('İstemleri sahneden çıkar')
        self.visual_button.clicked.connect(self.extract_visual)
        pv.addWidget(QLabel('Görsel istemi'))
        pv.addWidget(self.visual_prompt, 1)
        pv.addWidget(QLabel('Hareket ve ses istemi (video)'))
        pv.addWidget(self.motion_prompt)
        pv.addWidget(self.visual_button)
        grid.addWidget(prompts, 0, 0, 2, 1)

        image = QGroupBox('Görsel')
        iv = QFormLayout(image)
        self.image_aspect = _combo(gemini_api.ASPECT_RATIOS)
        self.image_size = _combo(list(gemini_api.IMAGE_SIZES) + ['512'])
        self.style_ref_label = QLabel('Yok')
        self.style_ref_button = QPushButton('Stil referansı seç')
        self.style_ref_button.clicked.connect(self.choose_style_reference)
        self.char_ref_label = QLabel('Yok')
        self.char_ref_button = QPushButton('Karakter referansları seç')
        self.char_ref_button.clicked.connect(self.choose_character_references)
        self.clear_refs_button = QPushButton('Referansları temizle')
        self.clear_refs_button.clicked.connect(self.clear_references)
        self.image_button = QPushButton('Bu sahnenin görselini üret')
        self.image_button.clicked.connect(self.generate_image)
        iv.addRow('En-boy', self.image_aspect)
        iv.addRow('Boyut', self.image_size)
        iv.addRow(self.style_ref_button, self.style_ref_label)
        iv.addRow(self.char_ref_button, self.char_ref_label)
        iv.addRow(self.clear_refs_button)
        iv.addRow(self.image_button)
        grid.addWidget(image, 0, 1)

        video = QGroupBox('Video')
        vv = QFormLayout(video)
        self.duration = QSpinBox()
        self.duration.setRange(gemini_api.VIDEO_MIN_SECONDS, gemini_api.VIDEO_MAX_SECONDS)
        self.duration.setValue(6)
        self.duration.setSuffix(' sn')
        self.resolution = _combo(gemini_api.VIDEO_RESOLUTIONS)
        self.resolution.setCurrentText('720p')
        self.video_aspect = _combo(gemini_api.VIDEO_ASPECTS)
        self.video_from_image_button = QPushButton('Görselden video üret')
        self.video_from_image_button.clicked.connect(lambda: self.generate_video(from_image=True))
        self.video_from_text_button = QPushButton('Metinden video üret')
        self.video_from_text_button.clicked.connect(lambda: self.generate_video(from_image=False))
        vv.addRow('Süre', self.duration)
        vv.addRow('Çözünürlük', self.resolution)
        vv.addRow('En-boy', self.video_aspect)
        vv.addRow(self.video_from_image_button)
        vv.addRow(self.video_from_text_button)
        grid.addWidget(video, 1, 1)

        output = QGroupBox('Sonuç')
        ov = QVBoxLayout(output)
        self.preview = QLabel('Görsel yok')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 180)
        self.video_label = QLabel('Video yok')
        self.video_label.setProperty('i18n_skip', True)
        self.video_label.setWordWrap(True)
        self.add_image_button = QPushButton('Görseli projeye ekle')
        self.add_image_button.clicked.connect(lambda: self.add_to_project('image'))
        self.add_video_button = QPushButton('Videoyu projeye ekle')
        self.add_video_button.clicked.connect(lambda: self.add_to_project('video'))
        ov.addWidget(self.preview, 1)
        ov.addWidget(self.video_label)
        row = QHBoxLayout()
        row.addWidget(self.add_image_button)
        row.addWidget(self.add_video_button)
        ov.addLayout(row)
        grid.addWidget(output, 0, 2, 2, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(2, 2)
        for widget in (self.image_model, self.image_size, self.video_model, self.resolution, self.duration):
            signal = widget.valueChanged if isinstance(widget, QSpinBox) else widget.currentTextChanged
            signal.connect(self.update_cost_line)
        return page

    def _status_row(self):
        layout = QVBoxLayout()
        self.cost_label = QLabel()
        self.cost_label.setProperty('i18n_skip', True)
        self.usage_label = QLabel()
        self.usage_label.setProperty('i18n_skip', True)
        self.status_label = QLabel('Hazır.')
        self.status_label.setProperty('i18n_skip', True)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.cost_label)
        layout.addWidget(self.usage_label)
        row = QHBoxLayout()
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(140)
        self.cancel_button = QPushButton('İptal')
        self.cancel_button.clicked.connect(self.cancel_work)
        self.save_button = QPushButton('Hikâyeyi kaydet')
        self.save_button.clicked.connect(lambda: self.save_story())
        self.open_button = QPushButton('Hikâye aç')
        self.open_button.clicked.connect(lambda: self.open_story())
        self.close_button = QPushButton('Kapat')
        self.close_button.clicked.connect(self.close)
        row.addWidget(self.status_label, 1)
        for widget in (self.busy, self.cancel_button, self.save_button, self.open_button, self.close_button):
            row.addWidget(widget)
        layout.addLayout(row)
        return layout

    # ------------------------------------------------------------ helpers

    def key(self):
        value = self._api_key() if callable(self._api_key) else self._api_key
        return (value or '').strip()

    def output_folder(self):
        value = self._output_dir() if callable(self._output_dir) else self._output_dir
        return Path(value) if value else None

    def set_status(self, text):
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def action_buttons(self):
        return (self.bible_button, self.outline_button, self.write_button, self.continue_button, self.rewrite_button,
                self.split_button, self.visual_button, self.image_button, self.video_from_image_button,
                self.video_from_text_button, self.check_models_button, self.open_button, self.delete_scene_button)

    def set_busy(self, busy):
        for button in self.action_buttons():
            button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.busy.setVisible(busy)

    def current_scene(self):
        return self.state.scene(self.current_id)

    def update_cost_line(self, *_):
        image = ss.image_cost_line(self.image_model.currentText().strip(), self.image_size.currentText())
        video = ss.video_cost_line(self.video_model.currentText().strip(), self.resolution.currentText(),
                                   self.duration.value())
        self.cost_label.setText(f'Görsel — {image} · Video — {video}')

    # ------------------------------------------------------------ state <-> widgets

    def refresh_bible_editor(self):
        import json
        bible = self.state.bible
        self._loading = True
        self.premise.setPlainText(bible.premise)
        index = self.style.findData(bible.style)
        self.style.setCurrentIndex(max(0, index))
        if bible.pov:
            self.pov.setCurrentText(bible.pov)
        if bible.tense:
            self.tense.setCurrentText(bible.tense)
        self.genre.setText(bible.genre)
        data = {k: v for k, v in self.state.to_dict()['bible'].items()
                if k not in ('premise', 'style', 'pov', 'tense')}
        self.bible_editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        self._loading = False

    def read_idea_fields(self):
        bible = self.state.bible
        bible.premise = self.premise.toPlainText().strip()
        bible.style = self.style.currentData()
        bible.pov = self.pov.currentText()
        bible.tense = self.tense.currentText()
        bible.genre = self.genre.text().strip() or bible.genre

    def apply_bible_editor(self):
        data = ss.extract_json(self.bible_editor.toPlainText())
        if not isinstance(data, dict):
            self.set_status('Rehber geçerli JSON değil; düzeltip tekrar uygulayın.')
            return False
        self.read_idea_fields()
        merged = ss.bible_from_dict(data)
        for name in ('premise', 'style', 'pov', 'tense'):
            setattr(merged, name, getattr(self.state.bible, name))
        merged.genre = self.genre.text().strip() or merged.genre
        self.state.bible = merged
        self.set_status('Rehber güncellendi.')
        return True

    def refresh_scene_list(self, select=None):
        self._loading = True
        self.scene_list.clear()
        for index, scene in enumerate(self.state.scenes, 1):
            marks = ('▣' if scene.image_path else '') + ('▶' if scene.video_path else '')
            item = QListWidgetItem(f'{index}. {scene.title or "Adsız"} {marks}'.strip())
            item.setData(Qt.ItemDataRole.UserRole, scene.id)
            self.scene_list.addItem(item)
        self._loading = False
        target = select or self.current_id
        row = self.state.index_of(target) if target else -1
        if row < 0 and self.state.scenes:
            row = len(self.state.scenes) - 1
        self.scene_list.setCurrentRow(row)
        self.select_scene(row)

    def select_scene(self, row):
        if self._loading:
            return
        scene = self.state.scenes[row] if 0 <= row < len(self.state.scenes) else None
        self.current_id = scene.id if scene else ''
        self._loading = True
        self.scene_title.setText(scene.title if scene else '')
        self.scene_text.setPlainText(scene.text if scene else '')
        self.visual_prompt.setPlainText(scene.visual_prompt if scene else '')
        self.motion_prompt.setPlainText(scene.motion_prompt if scene else '')
        self._loading = False
        self.show_media(scene)

    def store_scene(self):
        if self._loading:
            return
        scene = self.current_scene()
        if scene is None:
            return
        scene.title = self.scene_title.text()
        scene.text = self.scene_text.toPlainText()
        scene.visual_prompt = self.visual_prompt.toPlainText()
        scene.motion_prompt = self.motion_prompt.toPlainText()
        item = self.scene_list.currentItem()
        if item is not None:
            item.setText(f'{self.state.index_of(scene.id) + 1}. {scene.title or "Adsız"}')

    def show_media(self, scene):
        image = scene.image_path if scene else ''
        pixmap = QPixmap(image) if image and Path(image).is_file() else QPixmap()
        if pixmap.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText(Path(image).name if image else 'Görsel yok')
        else:
            self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
        video = scene.video_path if scene else ''
        self.video_label.setText(video or 'Video yok')

    def add_empty_scene(self):
        scene = ss.Scene(title=f'Sahne {len(self.state.scenes) + 1}')
        self.state.scenes.append(scene)
        self.refresh_scene_list(scene.id)

    def delete_scene(self):
        if self.worker is not None:  # a running job may still write into this scene
            self.set_status('Önce süren işlemin bitmesini bekleyin.')
            return False
        index = self.state.index_of(self.current_id)
        if index < 0:
            return False
        title = self.state.scenes[index].title or 'Adsız'
        if not self.confirm(DELETE_SCENE_QUESTION.format(title=title)):
            return False
        if index >= 0:
            del self.state.scenes[index]
            self.current_id = ''
            self.refresh_scene_list()
        return True

    # ------------------------------------------------------------ worker plumbing

    def start(self, worker, on_done):
        if self.worker is not None:
            self.set_status('Önce süren işlemin bitmesini bekleyin.')
            return False
        self.worker = worker
        worker.status.connect(self.set_status)
        worker.progress.connect(self.on_progress)
        worker.completed.connect(lambda result: self.on_completed(worker, on_done, result))
        worker.failed.connect(lambda message: self.on_failed(worker, message))
        worker.cancelled.connect(lambda: self.on_cancelled(worker))
        self.set_busy(True)
        worker.start()
        return True

    def on_progress(self, seconds):
        if seconds and seconds % 5 == 0:
            text = self.status_label.text().split(' — ')[0]
            self.set_status(f'{text} — {seconds} sn')

    def _release(self, worker):
        if worker is not self.worker:
            return False
        self.worker = None
        self.set_busy(False)
        return not self._closing

    def on_completed(self, worker, on_done, result):
        if not self._release(worker):
            return
        try:
            on_done(result)
        except Exception as exc:
            self.set_status(f'Sonuç işlenemedi: {exc}')

    def on_failed(self, worker, message):
        if self._release(worker):
            self.set_status(f'Hata: {message}')

    def on_cancelled(self, worker):
        if self._release(worker):
            self.set_status('İşlem iptal edildi; sonucu kullanılmayacak.')

    def cancel_work(self):
        if self.worker is not None:
            self.worker.cancel()
            self.set_status('İptal ediliyor…')

    def need_key(self):
        key = self.key()
        if not key:
            self.set_status('Gemini API anahtarı yok. Ana penceredeki AI ayarlarından Gemini anahtarını girin.')
        return key

    def run_text(self, job, on_done):
        key = self.need_key()
        if not key:
            return False
        return self.start(TextWorker(job, key, self._transport), on_done)

    def show_usage(self, result):
        self.last_usage = ss.usage_line(result)
        self.usage_label.setText(self.last_usage)

    def text_model_choice(self):
        return self.text_model.currentText().strip() or None

    # ------------------------------------------------------------ text actions

    def has_bible_work(self):
        """True when the guide already holds characters or an outline (in the story or in the editor)."""
        if self.state.bible.characters or self.state.bible.outline:
            return True
        data = ss.extract_json(self.bible_editor.toPlainText())
        return isinstance(data, dict) and bool(data.get('characters') or data.get('outline'))

    def generate_bible(self):
        if self.has_bible_work() and not self.confirm(REPLACE_BIBLE_QUESTION):
            return
        self.read_idea_fields()
        bible = self.state.bible
        try:
            job = ss.bible_job(bible.premise, style=bible.style, pov=bible.pov, tense=bible.tense, genre=bible.genre,
                               model=self.text_model_choice(), quality=self.quality.currentData())
        except ValueError as exc:
            self.set_status(str(exc))
            return

        def done(result):
            self.show_usage(result)
            self.state.bible = ss.apply_bible(result.text, self.state.bible)
            self.refresh_bible_editor()
            self.set_status('Hikâye rehberi hazır. Gözden geçirip düzenleyebilirsiniz.')
        self.run_text(job, done)

    def generate_outline(self):
        if not self.apply_bible_editor():
            return
        job = ss.outline_job(self.state, model=self.text_model_choice(), quality=self.quality.currentData())

        def done(result):
            self.show_usage(result)
            self.state.bible.outline = ss.apply_outline(result.text)
            self.refresh_bible_editor()
            self.set_status('Olay örgüsü taslağı rehbere eklendi.')
        self.run_text(job, done)

    def _scene_done(self, job):
        def done(result):
            self.show_usage(result)
            scene = ss.apply_scene_text(self.state, job, result.text)
            self.refresh_scene_list(scene.id)
            message = 'Sahne hazır.'
            if result.truncated:
                message = 'Yanıt çıktı sınırında kesildi; metin eksik olabilir. "Devam et" ile tamamlayabilirsiniz.'
            if result.fell_back:
                message += f' Yedek model kullanıldı: {result.model}.'
            self.set_status(message)
            if self.auto_memory.isChecked():
                self.update_memory(scene.id)
        return done

    def write_scene(self):
        if not self.apply_bible_editor():  # keep the JSON error on screen; never write with the old guide
            return False
        job = ss.next_scene_job(self.state, instruction=self.instruction.text(), words=self.words.value(),
                                model=self.text_model_choice(), quality=self.quality.currentData())
        self.run_text(job, self._scene_done(job))

    def continue_scene(self):
        try:
            job = ss.continue_job(self.state, self.current_id, instruction=self.instruction.text(),
                                  words=self.words.value(), model=self.text_model_choice(),
                                  quality=self.quality.currentData())
        except ValueError as exc:
            self.set_status(str(exc))
            return
        self.run_text(job, self._scene_done(job))

    def rewrite_scene(self):
        try:
            job = ss.rewrite_job(self.state, self.current_id, self.rewrite_mode.currentData(),
                                 instruction=self.instruction.text(), model=self.text_model_choice(),
                                 quality=self.quality.currentData())
        except ValueError as exc:
            self.set_status(str(exc))
            return
        self.run_text(job, self._scene_done(job))

    def update_memory(self, scene_id):
        job = ss.memory_job(self.state, scene_id)

        def done(result):
            if ss.apply_memory(self.state, scene_id, result.text):
                self.set_status(self.status_label.text() + ' Özet ve süreklilik notları güncellendi.')
            else:
                self.set_status(self.status_label.text() + ' Özet güncellenemedi (geçersiz yanıt); eski notlar korundu.')
        self.run_text(job, done)

    def split_text(self):
        scene = self.current_scene()
        if scene is None or not scene.text.strip():
            self.set_status('Bölmek için metni bir sahneye yapıştırın ve o sahneyi seçin.')
            return
        try:
            job = ss.split_job(self.state, scene.text)
        except ValueError as exc:
            self.set_status(str(exc))
            return
        source, scene_id = scene.text, scene.id

        def done(result):
            parts = ss.apply_split(result.text, source)
            index = self.state.index_of(scene_id)
            if index < 0:
                return
            self.state.scenes[index:index + 1] = parts
            self.refresh_scene_list(parts[0].id)
            self.set_status(f'Metin {len(parts)} sahneye bölündü.')
        self.run_text(job, done)

    def extract_visual(self):
        try:
            job = ss.visual_job(self.state, self.current_id)
        except ValueError as exc:
            self.set_status(str(exc))
            return
        scene_id = self.current_id

        def done(result):
            self.show_usage(result)
            ss.apply_visual(self.state, scene_id, result.text)
            if scene_id == self.current_id:
                self.select_scene(self.state.index_of(scene_id))
            self.set_status('Görsel ve hareket istemleri hazır; üretmeden önce düzenleyebilirsiniz.')
        self.run_text(job, done)

    def check_models(self):
        key = self.need_key()
        if not key:
            return
        getter = self._file_getter

        def done(models):
            available = set(models)
            for combo, known in ((self.text_model, gemini_api.TEXT_MODELS), (self.image_model, gemini_api.IMAGE_MODELS),
                                 (self.video_model, gemini_api.VIDEO_MODELS)):
                current = combo.currentText().strip()
                usable = [m for m in known if m in available] or list(known)
                if current and current not in usable:  # a model id typed by hand is the user's choice: keep it
                    usable.append(current)
                combo.clear()
                combo.addItems(usable)
                combo.setCurrentText(current or usable[0])
            missing = [m for m in gemini_api.TEXT_MODELS + gemini_api.IMAGE_MODELS + gemini_api.VIDEO_MODELS
                       if m not in available]
            self.set_status('Model listesi güncellendi.' + (f' Bu anahtarla görünmeyen: {", ".join(missing)}' if missing else ''))
        self.start(CallWorker(lambda: gemini_api.list_models(key, getter=getter), 'Modeller denetleniyor…'), done)

    # ------------------------------------------------------------ image / video

    def choose_style_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Stil referansı seç', '', 'Görsel (*.png *.jpg *.jpeg *.webp)')
        if path:
            self.style_reference = path
            self.style_ref_label.setText(Path(path).name)

    def choose_character_references(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Karakter referansları seç', '', 'Görsel (*.png *.jpg *.jpeg *.webp)')
        if paths:
            self.character_references = paths[:gemini_api.MAX_CHARACTER_REFERENCES]
            self.char_ref_label.setText(', '.join(Path(p).name for p in self.character_references))

    def clear_references(self):
        self.style_reference, self.character_references = '', []
        self.style_ref_label.setText('Yok')
        self.char_ref_label.setText('Yok')

    def references(self):
        """[(path, role, label)]: character files are labelled by their file name (name them after the
        character, e.g. Elif.png), the style reference comes last."""
        refs = [(p, 'character', Path(p).stem) for p in self.character_references]
        if self.style_reference:
            refs.append((self.style_reference, 'style', ''))
        return refs

    def media_target(self, scene, kind):
        folder = self.output_folder()
        if folder is None:
            raise ValueError('Çıktı klasörü belirlenmemiş.')
        state = self.state
        return lambda extension: ss.media_path(folder, state, scene, kind, extension)

    def generate_image(self):
        scene = self.current_scene()
        if scene is None:
            self.set_status('Önce bir sahne seçin.')
            return
        self.store_scene()
        if not scene.visual_prompt.strip():
            scene.visual_prompt, scene.motion_prompt = ss.fallback_visual_prompt(self.state.bible, scene)
            self.select_scene(self.state.index_of(scene.id))
        key = self.need_key()
        if not key:
            return
        model, size = self.image_model.currentText().strip(), self.image_size.currentText()
        try:
            refs = self.references()
            gemini_api.validate_image_request(model, scene.visual_prompt, [gemini_api.ImageInput(b'x', 'image/png', r)
                                                                           for _, r, _ in refs],
                                              self.image_aspect.currentText(), size)
            target = self.media_target(scene, 'gorsel')
        except ValueError as exc:
            self.set_status(str(exc))
            return
        worker = ImageWorker(key, model, scene.visual_prompt, target, references=refs,
                             aspect_ratio=self.image_aspect.currentText(), image_size=size, transport=self._transport)
        scene_id = scene.id

        def done(result):
            target_scene = self.state.scene(scene_id)
            if target_scene is not None:
                target_scene.image_path = result['path']
            self.refresh_scene_list(scene_id)
            self.set_status(f'Görsel kaydedildi: {result["path"]}')
        if self.start(worker, done):
            self.set_status(f'{ss.image_cost_line(model, size)} — görsel üretiliyor…')

    def generate_video(self, from_image):
        scene = self.current_scene()
        if scene is None:
            self.set_status('Önce bir sahne seçin.')
            return
        self.store_scene()
        if from_image and not (scene.image_path and Path(scene.image_path).is_file()):
            self.set_status('Bu sahnenin görseli yok; önce görsel üretin ya da "Metinden video üret"i kullanın.')
            return
        if not scene.visual_prompt.strip() and not from_image:
            scene.visual_prompt, scene.motion_prompt = ss.fallback_visual_prompt(self.state.bible, scene)
        if not scene.motion_prompt.strip():
            scene.motion_prompt = ss.compose_motion_prompt({})
        self.select_scene(self.state.index_of(scene.id))
        key = self.need_key()
        if not key:
            return
        model, resolution, seconds = self.video_model.currentText().strip(), self.resolution.currentText(), self.duration.value()
        prompt = ss.video_prompt(scene, from_image)
        try:
            gemini_api.validate_video_request(prompt, (), self.video_aspect.currentText(), resolution, seconds, False)
            target = self.media_target(scene, 'video')
        except ValueError as exc:
            self.set_status(str(exc))
            return
        worker = VideoWorker(key, model, prompt, target, image_path=scene.image_path if from_image else '',
                             aspect_ratio=self.video_aspect.currentText(), resolution=resolution, duration=seconds,
                             transport=self._transport, getter=self._file_getter)
        scene_id = scene.id

        def done(result):
            target_scene = self.state.scene(scene_id)
            if target_scene is not None:
                target_scene.video_path = result['path']
            self.refresh_scene_list(scene_id)
            self.set_status(f'Video kaydedildi: {result["path"]}')
        if self.start(worker, done):
            self.set_status(f'{ss.video_cost_line(model, resolution, seconds)} — video üretiliyor; birkaç dakika sürebilir…')

    def add_to_project(self, kind):
        scene = self.current_scene()
        path = (scene.image_path if kind == 'image' else scene.video_path) if scene else ''
        if not path or not Path(path).is_file():
            self.set_status('Eklenecek dosya yok; önce üretin.')
            return False
        try:
            accepted = self._add_media(path)
        except Exception as exc:
            self.set_status(f'Projeye eklenemedi: {exc}')
            return False
        if accepted is False:
            self.set_status('Ana pencere dosyayı eklemedi.')
            return False
        self.set_status(f'Projeye eklendi: {Path(path).name}')
        return True

    # ------------------------------------------------------------ files

    def save_story(self, path=None):
        self.store_scene()
        self.read_idea_fields()
        if not path:
            folder = self.output_folder()
            suggested = str((folder / (ss.slug(self.state.bible.title) + '.hikaye.json')) if folder else '')
            path, _ = QFileDialog.getSaveFileName(self, 'Hikâyeyi kaydet', self.story_path or suggested,
                                                  'Hikâye (*.hikaye.json *.json)')
            if not path:
                return False
        try:
            ss.save_story(path, self.state)
        except OSError as exc:
            self.set_status(f'Kaydedilemedi: {exc}')
            return False
        self.story_path = str(path)
        self.mark_clean()
        self.set_status(f'Hikâye kaydedildi: {path}')
        return True

    def open_story(self, path=None):
        if self.worker is not None:
            self.set_status('Önce süren işlemin bitmesini bekleyin.')
            return False
        if not self.maybe_save():
            return False
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, 'Hikâye aç', self.story_path, 'Hikâye (*.hikaye.json *.json)')
            if not path:
                return False
        try:
            self.state = ss.load_story(path)
        except ValueError as exc:
            self.set_status(str(exc))
            return False
        self.story_path = str(path)
        self.current_id = ''
        self.refresh_bible_editor()
        self.refresh_scene_list()
        self.mark_clean()
        self.set_status(f'Hikâye açıldı: {Path(path).name}')
        return True

    # ------------------------------------------------------------ closing

    def shutdown(self):
        """Cancel a running worker and detach from it; it ends on its own (kept alive by story_workers)."""
        self._closing = True
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.cancel()
            for signal in (worker.status, worker.progress, worker.completed, worker.failed, worker.cancelled):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass

    def closeEvent(self, event):
        # QDialog.closeEvent calls reject(); confirm_close remembers the answer so it is asked once.
        if not self.confirm_close():
            event.ignore()
            return
        self.shutdown()
        super().closeEvent(event)

    def reject(self):
        if not self.confirm_close():
            return
        self.shutdown()
        super().reject()

    def showEvent(self, event):
        self._closing = False
        self._close_approved = False
        super().showEvent(event)
