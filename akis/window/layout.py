"""Building the window: sidebar, workspace, editor and the inspector tabs."""
from __future__ import annotations

from akis.multitrack_widget import MultitrackWidget
from akis.preview_widget import PreviewView
from akis import tts_service
from akis import ai_providers, update_service
from akis import i18n
from akis import speech_settings
from akis.start_panel import StartPanel
from akis import theme
from akis import word_captions

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from akis import app_support
from akis.app_support import log


class LayoutMixin:
    """Building the window: sidebar, workspace, editor and the inspector tabs."""

    def build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(190)
        # On a short screen the sidebar scrolls instead of squeezing its parts until their text overlaps.
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setObjectName("sidebarInner")
        inner = QWidget()
        inner.setObjectName("sidebarInner")
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.sidebar_scroll = scroll
        v = QVBoxLayout(inner)
        v.setContentsMargins(18, 22, 14, 14)
        v.setSpacing(8)
        self.brand = brand = QLabel()
        brand.setTextFormat(Qt.TextFormat.RichText)
        brand.setObjectName("brand")
        brand.setProperty("i18n_skip", True)
        self.paint_brand()
        v.addWidget(brand)
        subtitle = QLabel("AI Video Studio")
        subtitle.setObjectName("muted")
        v.addWidget(subtitle)
        v.addSpacing(16)

        for index, (text, icon) in enumerate([
            ("Projeler", "▦"), ("İlham", "✦"), ("Şablonlar", "◈"), ("Hikâye Stüdyosu", "✎"), ("Dışa aktarımlar", "⇧")
        ]):
            # The whole label (icon included) is the EN_UI key, so apply_language translates it.
            button = QPushButton(f"{icon}   {text}")
            button.setProperty("nav", True)
            button.setProperty("active", index == 0)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if index == 0:
                button.clicked.connect(lambda: self.set_status(self.ui_text("Proje düzenleyicisi açık.")))
            elif index == 1:
                button.clicked.connect(self.show_inspiration)
            elif index == 2:
                button.clicked.connect(self.show_templates)
            elif index == 3:
                button.clicked.connect(self.show_story_studio)
            else:
                button.clicked.connect(lambda: self.set_status(self.ui_text("Dışa aktarmak için üstteki düğmeyi kullanın.")))
            v.addWidget(button)

        v.addSpacing(10)
        label = QLabel("PROJE MEDYASI")
        label.setObjectName("sectionLabel")
        v.addWidget(label)
        self.media_search = QLineEdit()
        self.media_search.setPlaceholderText("Medya ara")
        self.media_search.textChanged.connect(self.refresh_media_bin)
        v.addWidget(self.media_search)
        self.media_list = QListWidget()
        self.media_list.setObjectName("mediaList")
        self.media_list.setMinimumHeight(72)        # gives way first when the window is short
        self.media_list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        # Long file names are shortened in the middle (the full path is the tooltip) instead of a scroll bar.
        self.media_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.media_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        v.addWidget(self.media_list, 1)
        add = QPushButton("＋  Video ekle")
        add.setObjectName("secondary")
        add.clicked.connect(self.choose_video)
        v.addWidget(add)
        record = QPushButton("  Kayıt al")
        self.record_button = record
        record.setObjectName("secondary")
        record.setToolTip("Kameradan, ekrandan ya da mikrofondan kayıt alıp projeye ekler.")
        record.clicked.connect(self.record_media)
        v.addWidget(record)
        # Language and theme are two segmented switches. The combos behind them stay the source of truth
        # (settings, translation and scripts use them) but are not shown.
        self.language = QComboBox()
        self.language.addItem("Türkçe", "tr")
        self.language.addItem("English", "en")
        selected_language = self.startup_language()
        self.language.setCurrentIndex(0 if selected_language == "tr" else 1)
        self.language.currentIndexChanged.connect(self.change_language)
        self.language.hide()
        v.addWidget(self.language)
        self.theme_box = QComboBox()
        self.theme_box.setProperty("i18n_keyed", True)
        for name, label in theme.LABELS.items():
            self.theme_box.addItem(label, label)
        self.theme_box.setCurrentIndex(list(theme.LABELS).index(theme.current()))
        self.theme_box.setAccessibleName("Tema")
        self.theme_box.currentIndexChanged.connect(self.change_theme)
        self.theme_box.hide()
        v.addWidget(self.theme_box)
        v.addSpacing(4)
        self.language_switch = self.segmented(self.language, ["Türkçe", "English"], "Arayüz dili", translate=False)
        v.addWidget(self.language_switch)
        self.theme_switch = self.segmented(self.theme_box, ["Koyu", "Açık"], "Görünüm")
        v.addWidget(self.theme_switch)
        self.paint_switch_icons()
        v.addSpacing(6)

        local = QFrame()
        local.setObjectName("privacyCard")
        lv = QVBoxLayout(local)
        lv.setContentsMargins(10, 8, 10, 8)
        lv.setSpacing(3)
        title = QLabel("●  Yerel işleme")
        title.setObjectName("localTitle")
        # The standing promise is in the tooltip; the card itself shows what has actually left the computer.
        title.setToolTip("Dışa aktarma bilgisayarınızda yapılır. AI yalnızca siz başlatınca çalışır.")
        lv.addWidget(title)
        local.setToolTip(title.toolTip())
        # What actually left the computer since the app started (akis.privacy_log), kept current by a timer.
        self.privacy_label = QLabel()
        self.privacy_label.setWordWrap(True)
        self.privacy_label.setObjectName("mutedSmall")
        self.privacy_label.setProperty("i18n_skip", True)
        lv.addWidget(self.privacy_label)
        self.privacy_timer = QTimer(self)
        self.privacy_timer.setInterval(2000)
        self.privacy_timer.timeout.connect(self.refresh_privacy)
        self.privacy_timer.start()
        self.refresh_privacy()
        v.addWidget(local)
        # The running version, always in view; a click asks GitHub whether a newer one exists.
        self.version_button = QPushButton(f"v{update_service.VERSION}")
        self.version_button.setObjectName("versionTag")
        self.version_button.setProperty("i18n_skip", True)  # a version number, the same in every language
        self.version_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_button.clicked.connect(lambda: self.check_for_updates(manual=True))
        v.addWidget(self.version_button)
        return side

    def build_workspace(self) -> QWidget:
        shell = QWidget()
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(22, 16, 22, 16)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.project_title = QLabel("Yeni proje")
        self.project_title.setObjectName("projectTitle")
        self.project_subtitle = QLabel("Video ekleyerek başlayın")
        self.project_subtitle.setObjectName("muted")
        # User content once a video is loaded (file name and size); apply_language only rewrites the
        # placeholders while there is no video.
        for label in (self.project_title, self.project_subtitle):
            label.setProperty("i18n_skip", True)
        title_box.addWidget(self.project_title)
        title_box.addWidget(self.project_subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(300)
        self.status_label.setProperty("i18n_skip", True)  # messages can quote file names and errors
        header.addWidget(self.status_label)
        open_project = QPushButton("Proje aç")
        open_project.setObjectName("ghost")
        open_project.setToolTip("Kayıtlı bir projeyi açar (Ctrl+O)")
        open_project.clicked.connect(self.open_project)
        header.addWidget(open_project)
        save_project = QPushButton("Projeyi kaydet")
        save_project.setObjectName("secondary")
        save_project.setToolTip("Projeyi kaydeder (Ctrl+S)")
        save_project.clicked.connect(self.save_project)
        header.addWidget(save_project)
        self.save_as_button = QPushButton("Farklı kaydet")
        self.save_as_button.setObjectName("secondary")
        self.save_as_button.setToolTip("Projeyi başka bir konuma kaydeder (Ctrl+Shift+S)")
        self.save_as_button.clicked.connect(self.save_project_as)
        header.addWidget(self.save_as_button)
        export = QPushButton("Dışa aktar  ↗")
        export.setObjectName("primary")
        export.setToolTip("Videoyu MP4 olarak dışa aktarır (Ctrl+E)")
        export.clicked.connect(self.export_video)
        header.addWidget(export)
        outer.addLayout(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self.build_editor())
        split.addWidget(self.build_inspector())
        split.setSizes([900, 390])
        self.splitter = split
        outer.addWidget(split, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 1, Qt.AlignmentFlag.AlignVCenter)
        # Shown while a worker runs; enabled only when that worker can be stopped (it has cancel()).
        self.cancel_button = QPushButton("İptal")
        self.cancel_button.setObjectName("ghost")
        self.cancel_button.setToolTip("Devam eden işlemi durdurur.")
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel_work)
        progress_row.addWidget(self.cancel_button)
        outer.addLayout(progress_row)
        return shell

    def build_editor(self) -> QWidget:
        area = QFrame()
        area.setObjectName("editor")
        v = QVBoxLayout(area)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(12)

        self.video = PreviewView('Video ekleyin')
        self.video.setObjectName("video")
        self.video.setMinimumSize(320, 200)
        self.video.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.video.setToolTip('Ctrl + tekerlek: yakınlaştır · sürükle: kaydır · orta tuş: sıfırla · çift tık: yazı/işaret düzenle')
        self.video.double_clicked.connect(self.edit_at)
        # An empty project shows what to do first, over the empty preview (akis.start_panel).
        self.start_panel = StartPanel(add_video=self.choose_video, show_templates=self.show_templates)
        start_layout = QVBoxLayout(self.video)
        start_layout.addWidget(self.start_panel, 0, Qt.AlignmentFlag.AlignCenter)
        # Zooming in (or a larger window) needs a sharper still; wait until the gesture has settled.
        self.still_timer = QTimer(self)
        self.still_timer.setSingleShot(True)
        self.still_timer.setInterval(250)
        self.still_timer.timeout.connect(self.refresh_still)
        self.video.zoom_changed.connect(lambda _zoom: self.still_timer.start())
        self.video.resized.connect(self.still_timer.start)
        v.addWidget(self.video, 1)

        controls = QHBoxLayout()
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("roundButton")
        self.play_button.setFixedSize(40, 40)
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setToolTip("Oynat / duraklat (Boşluk)")  # the button is i18n_skip: apply_language sets it
        controls.addWidget(self.play_button)
        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setObjectName("mono")
        for dynamic in (self.play_button, self.time_label):
            dynamic.setProperty("i18n_skip", True)
        controls.addWidget(self.time_label)
        controls.addStretch()
        volume_label = QLabel("Ses")
        volume_label.setObjectName("muted")
        controls.addWidget(volume_label)
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(80)
        volume.setFixedWidth(100)
        self.master_volume = 0.8
        volume.valueChanged.connect(self.change_master_volume)
        controls.addWidget(volume)
        v.addLayout(controls)

        timeline_header = QHBoxLayout()
        timeline_header.addWidget(QLabel("Zaman çizelgesi"))
        timeline_header.addStretch()
        self.selection_label = QLabel("Seçim: —")
        self.selection_label.setObjectName("muted")
        self.selection_label.hide()
        timeline_header.addWidget(self.selection_label)
        v.addLayout(timeline_header)
        tool_container = QWidget()
        tools = QHBoxLayout(tool_container)
        tools.setContentsMargins(0, 0, 0, 0)
        for label, action in [('＋ İz', self.add_track), ('− İz', self.remove_track),
                              ('＋ Medya', self.add_timeline_media), ('＋ Müzik', self.add_timeline_music),
                              ('Böl', self.split_clip),
                              ('◁ Kırp', self.trim_left), ('Kırp ▷', self.trim_right), ('Aralığı sil', self.delete_range),
                              ('Ripple sil', self.ripple_delete), ('Klip sesi', self.set_clip_volume), ('Klip hızı', self.set_clip_speed), ('Kadraj', self.set_clip_fit), ('Metni düzenle', self.edit_text_clip)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            if label == '＋ Müzik':
                button.setToolTip('Ses dosyası seçip zaman çizelgesinin ses izine ekler.')
                self.music_button = button
            elif label == 'Klip sesi':
                button.setToolTip('Ses ya da video klibini seçin; düzeyi dışa aktarılan videoya da uygulanır.')
            elif label == 'Ripple sil':
                button.setToolTip('Seçili klibi siler ve boşluğu kapatır. Delete tuşu klibi boşluk bırakarak siler.')
            elif label == '◁ Kırp':
                button.setToolTip('Seçili klibin oynatma çizgisinden önceki kısmını atar (Q).')
            elif label == 'Kırp ▷':
                button.setToolTip('Seçili klibin oynatma çizgisinden sonraki kısmını atar (W).')
            elif label == 'Aralığı sil':
                button.setToolTip('Zaman çizelgesinde boş bir yerden sürükleyerek (ya da cetvelde Shift ile) bir aralık seçin; '
                                  'bu düğme o aralığı bütün izlerden çıkarır ve boşluğu kapatır (Delete).')
                button.setEnabled(False)
                self.range_button = button
            tools.addWidget(button)
        self.undo_button = QPushButton('↶ Geri al')
        self.undo_button.setToolTip('Son adımı geri al (Ctrl+Z)')
        self.undo_button.clicked.connect(self.undo)
        tools.addWidget(self.undo_button)
        self.redo_button = QPushButton('↷ Yinele')
        self.redo_button.setToolTip('Geri alınan adımı yinele (Ctrl+Y)')
        self.redo_button.clicked.connect(self.redo)
        tools.addWidget(self.redo_button)
        zoom = QSlider(Qt.Orientation.Horizontal)
        zoom.setRange(1, 100)
        zoom.setValue(20)
        zoom.setFixedWidth(90)
        zoom.valueChanged.connect(self.timeline_zoom)
        tools.addWidget(QLabel('Yakınlık'))
        tools.addWidget(zoom)
        tool_scroll = QScrollArea()
        tool_scroll.setWidgetResizable(True)
        tool_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tool_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tool_scroll.setMaximumHeight(65)
        tool_scroll.setWidget(tool_container)
        v.addWidget(tool_scroll)
        self.multitrack_view = MultitrackWidget(self.multitrack)
        self.multitrack_view.waveform_executable = app_support.ffmpeg_path
        self.multitrack_view.seek.connect(self.seek_timeline)
        self.multitrack_view.edit_started.connect(self.on_timeline_drag_started)
        self.multitrack_view.changed.connect(self.on_timeline_dragged)
        self.multitrack_view.range_changed.connect(self.on_range_changed)
        self.multitrack_view.clip_activated.connect(self.edit_clip)
        self.track_scroll = QScrollArea()
        self.track_scroll.setWidgetResizable(True)
        self.track_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.track_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.track_scroll.setMinimumHeight(218)
        self.track_scroll.setMaximumHeight(380)
        self.track_scroll.setWidget(self.multitrack_view)
        v.addWidget(self.track_scroll)
        self.horizontal_timeline = QScrollBar(Qt.Orientation.Horizontal)
        self.horizontal_timeline.setRange(0, 0)
        self.horizontal_timeline.valueChanged.connect(self.multitrack_view.set_offset)
        self.multitrack_view.viewport_resized.connect(self.update_timeline_scroll)
        v.addWidget(self.horizontal_timeline)
        return area

    def build_inspector(self) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("inspector")
        wrapper.setMinimumWidth(300)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_ai_tab(), "✦ AI Kurgu")
        self.tabs.addTab(self.build_edit_tab(), "Düzenle")
        self.tabs.addTab(self.build_publish_tab(), "Yayın")
        layout.addWidget(self.tabs)
        return wrapper

    def segmented(self, combo: QComboBox, labels, name: str, translate: bool = True) -> QFrame:
        """A row of exclusive buttons driving `combo` (one per item) and following it when code changes it."""
        frame = QFrame()
        frame.setObjectName("segment")
        frame.setAccessibleName(name)
        frame.setToolTip(name)
        row = QHBoxLayout(frame)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(3)
        group = QButtonGroup(frame)
        group.setExclusive(True)
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("segmentButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if not translate:
                button.setProperty("i18n_skip", True)   # language names are written in their own language
            group.addButton(button, index)
            row.addWidget(button, 1)
        group.button(max(0, combo.currentIndex())).setChecked(True)
        group.idClicked.connect(combo.setCurrentIndex)
        combo.currentIndexChanged.connect(lambda index: group.button(index) and group.button(index).setChecked(True))
        frame.group = group
        combo.setProperty("switch_group", group)
        return frame

    def paint_switch_icons(self) -> None:
        """Moon and sun on the theme switch, in the theme's own colours (painted again on a theme change)."""
        from akis import switch_icons
        self.record_button.setIcon(switch_icons.dot(theme.hex_('cut')))
        dark, light = self.theme_switch.group.buttons()
        dark.setIcon(switch_icons.moon(theme.hex_('accent_text' if dark.isChecked() else 'muted')))
        light.setIcon(switch_icons.sun(theme.hex_('accent_text' if light.isChecked() else 'muted')))

    def scroll_page(self, content: QWidget) -> QScrollArea:
        content.setObjectName("inspectorPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def build_ai_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(12)

        hero = QLabel("Ne istediğini yaz.\nAkış kurgulasın.")
        hero.setObjectName("aiHero")
        v.addWidget(hero)
        desc = QLabel("Videoyu keser, yeniden dizer; geçiş, ok ve daire, yazı, renk ve hız ekler. Beğenmezseniz tek tıkla geri alın.")
        desc.setWordWrap(True)
        desc.setObjectName("muted")
        v.addWidget(desc)

        v.addWidget(self.section("İSTEĞİNİZ"))
        self.ai_prompt = QPlainTextEdit()
        self.ai_prompt.setPlaceholderText("Örn. Sessizlikleri at, sahneler arasına geçiş koy, en komik ana ok ve daire ekle, başa dikkat çekici bir yazı yaz.")
        self.ai_prompt.setFixedHeight(112)
        v.addWidget(self.ai_prompt)

        prompt_edit = QPushButton("✦  Prompt ile kurgula")
        prompt_edit.setObjectName("primaryLarge")
        prompt_edit.setToolTip("Yazdığınız isteğe göre videoyu gerçekten keser, dizer ve ayarlar.")
        prompt_edit.clicked.connect(self.run_prompt_edit)
        v.addWidget(prompt_edit)
        silence_button = QPushButton("Sessizlikleri çıkar")
        silence_button.setObjectName("secondary")
        silence_button.setToolTip("Konuşma olmayan yerleri keser. Yapay zekâ, anahtar ve internet gerekmez.")
        silence_button.clicked.connect(self.remove_silences)
        v.addWidget(silence_button)
        retake_button = QPushButton("Tekrar çekimleri temizle")
        retake_button.setObjectName("secondary")
        retake_button.setToolTip("Aynı cümle birkaç kez söylendiyse yalnızca son denemeyi bırakır. "
                                 "Önce aşağıdan yerel konuşma metnini çıkarın; internet gerekmez.")
        retake_button.clicked.connect(self.remove_retakes)
        v.addWidget(retake_button)
        filler_button = QPushButton("Dolgu sözcüklerini kes (ııı, eee, şey)")
        filler_button.setObjectName("secondary")
        filler_button.setToolTip("Duraksamaları ve “şey, yani” gibi dolgu sözcüklerini bulup keser. "
                                 "Yerel konuşma tanımayla çalışır; internet gerekmez.")
        filler_button.clicked.connect(self.remove_fillers)
        v.addWidget(filler_button)
        speaker_button = QPushButton("Konuşmacıları ayır")
        speaker_button.setObjectName("secondary")
        speaker_button.setToolTip("Kimin ne zaman konuştuğunu bulur: değişimleri işaretler ya da yalnızca bir "
                                  "konuşmacıyı bırakır. Bilgisayarınızda çalışır; ilk kullanımda küçük bir ses modeli indirilir.")
        speaker_button.clicked.connect(self.separate_speakers)
        v.addWidget(speaker_button)
        sample_button = QPushButton("Örnek videonun stilini al…")
        sample_button.setObjectName("secondary")
        sample_button.setToolTip("Beğendiğiniz bir videonun oranını, kadrajını, ses düzeyini ve rengini okur; "
                                 "şablon olarak kaydedip bu projeye uygular. İnternet gerekmez.")
        sample_button.clicked.connect(self.style_from_sample)
        v.addWidget(sample_button)
        beat_button = QPushButton("Kesimleri müziğin ritmine oturt")
        beat_button.setObjectName("secondary")
        beat_button.setToolTip("Ses izindeki müziğin vuruşlarını bulur ve video kesimlerini en yakın vuruşa kaydırır. "
                               "Müziğe dokunmaz; internet gerekmez.")
        beat_button.clicked.connect(self.snap_cuts_to_beat)
        v.addWidget(beat_button)
        punch_button = QPushButton('Ses düzeyi artışlarında yakınlaştır')
        punch_button.setObjectName("secondary")
        punch_button.setToolTip('Kaynak sesindeki belirgin ses düzeyi artışlarında görüntü kısa süre yakınlaşır; '
                                'müzik vuruşları da bunu tetikleyebilir. Yeniden basınca kaldırmayı sorar; internet gerekmez.')
        punch_button.clicked.connect(self.punch_in_on_emphasis)
        v.addWidget(punch_button)
        # Undoes the last step of the shared edit history; right after an AI edit that is the AI edit.
        self.undo_edit_button = QPushButton("↶  Son adımı geri al")
        self.undo_edit_button.setObjectName("secondary")
        self.undo_edit_button.setToolTip("AI kurgusu dahil son düzenlemeyi geri alır (Ctrl+Z).")
        self.undo_edit_button.setEnabled(False)
        self.undo_edit_button.clicked.connect(self.undo)
        v.addWidget(self.undo_edit_button)
        self.ai_result = QPlainTextEdit()
        self.ai_result.setReadOnly(True)
        self.ai_result.setPlaceholderText("Yapılan kurgunun özeti burada görünecek.")
        self.ai_result.setMinimumHeight(150)
        v.addWidget(self.ai_result)
        self.use_speech = QCheckBox("Konuşmayı da çözümle (yerel Whisper, daha yavaş)")
        self.use_speech.setToolTip("Model önbellekte yoksa bu adım atlanır; kurgu kare, sessizlik ve sahne bilgisiyle yapılır.")
        v.addWidget(self.use_speech)
        self.review_plan = QCheckBox("Uygulamadan önce AI planını göster")
        self.review_plan.setToolTip("AI'ın önerdiği her değişiklik ayrı bir kutuda gösterilir; istemediklerinizin işaretini kaldırırsınız.")
        self.review_plan.setChecked(self.settings.value("ai/review_plan", True) not in (False, 'false', '0', 0))
        self.review_plan.toggled.connect(lambda on: self.settings.setValue("ai/review_plan", bool(on)))
        v.addWidget(self.review_plan)
        v.addWidget(self.section("AI SAĞLAYICI"))
        self.provider = QComboBox()
        self.provider.addItems(ai_providers.PROVIDERS)
        v.addWidget(self.provider)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-…")
        v.addWidget(self.api_key)
        key_row = QHBoxLayout()
        self.remember_key = QCheckBox("Windows'ta güvenli sakla")
        self.remember_key.clicked.connect(self.on_remember_key_clicked)  # user clicks only, not load_key
        key_row.addWidget(self.remember_key)
        key_row.addStretch()
        reveal = QToolButton()
        reveal.setText("Göster")
        reveal.clicked.connect(self.toggle_key)
        key_row.addWidget(reveal)
        v.addLayout(key_row)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(ai_providers.PROVIDERS["OpenAI"])
        v.addWidget(self.model)
        save_key = QPushButton("Anahtarı güvenli kaydet")
        save_key.clicked.connect(lambda: self.save_key(self.api_key.text().strip()))
        v.addWidget(save_key)


        v.addWidget(self.section("ÖNERİ MODU (KESMEDEN)"))
        options = QFormLayout()
        # Item data is the value sent to the model, whatever the item shows.
        self.ai_platform = self.keyed_combo(['Reels', 'TikTok', 'YouTube Shorts', 'General'])
        self.ai_tempo = self.keyed_combo(['Slow', 'Medium', 'Fast', 'Dynamic'])
        self.ai_style = self.keyed_combo(['Cinematic', 'Energetic', 'Minimal', 'Educational', 'Storytelling'])
        self.ai_focus = self.keyed_combo(['Hook first', 'Highlights', 'Full story', 'Product', 'Tutorial'])
        for label, widget in [('Platform', self.ai_platform), ('Tempo', self.ai_tempo), ('Stil', self.ai_style), ('Odak', self.ai_focus)]:
            options.addRow(label, widget)
        v.addLayout(options)

        analyze = QPushButton("Öneri al")
        analyze.setObjectName("secondary")
        analyze.clicked.connect(self.run_ai)
        v.addWidget(analyze)
        self.ai_suggestions = []
        self.ai_choice = QComboBox()
        self.ai_choice.currentIndexChanged.connect(self.show_ai_suggestion)
        v.addWidget(self.ai_choice)
        apply_plan = QPushButton('Seçili öneriyi işaretlere uygula')
        apply_plan.clicked.connect(self.apply_ai_suggestion)
        v.addWidget(apply_plan)
        v.addWidget(self.section("KONUŞMA METNİ VE SESLENDİRME"))
        v.addWidget(QLabel('Konuşma dili'))
        self.speech_language = QComboBox()
        for code, name, _ in speech_settings.LANGUAGES:
            self.speech_language.addItem(name, code)
        self.speech_language.setProperty("i18n_skip", True)  # language names are shown in their own language
        self.speech_language.setToolTip('Altyazı ve konuşma metni bu dilde çözümlenir.')
        v.addWidget(self.speech_language)
        self.speech_vocabulary = QLineEdit()
        self.speech_vocabulary.setPlaceholderText('Özel adlar ve terimler, virgülle (örn. Anılcan, Akış Kurgu)')
        self.speech_vocabulary.setToolTip('Yanlış yazılan isimleri ve terimleri buraya ekleyin; tanıma bunları bekler.')
        v.addWidget(self.speech_vocabulary)
        self.load_speech_settings()
        self.speech_language.activated.connect(lambda _index: self.save_speech_settings())
        self.speech_vocabulary.editingFinished.connect(self.save_speech_settings)
        self.caption_backend = QComboBox()
        self.caption_backend.setProperty("i18n_keyed", True)  # item 1 is the local engine; the others are provider names
        for name in ('OpenAI', 'Yerel Whisper', 'xAI', 'Gemini'):
            self.caption_backend.addItem(name, name)
        v.addWidget(self.caption_backend)
        v.addWidget(QLabel('API transkripsiyon modeli'))
        self.transcript_model = QComboBox(); self.transcript_model.setEditable(True)
        self.transcript_model.addItems(ai_providers.TRANSCRIPTION_MODELS['OpenAI'])
        v.addWidget(self.transcript_model)
        self.caption_backend.currentTextChanged.connect(self.change_transcript_provider)
        self.local_model = QComboBox(); self.local_model.addItems(['tiny', 'base', 'small'])
        v.addWidget(self.local_model)
        self.download_model = QCheckBox('Modeli indir (internet)')
        v.addWidget(self.download_model)
        note = QLabel('Yerel model ilk kullanımda indirilmeli; indirme kapalıyken yalnızca önbellek kullanılır.')
        note.setWordWrap(True); v.addWidget(note)
        transcript = QPushButton("Konuşmayı Türkçe metne çevir")
        transcript.setObjectName("secondary")
        transcript.clicked.connect(self.run_transcript)
        v.addWidget(transcript)
        self.caption_segments = []
        self.caption_source = ''
        # How captions look: sentence by sentence, or a few words at a time with the spoken word lit.
        self.caption_look = QComboBox()
        self.caption_look.setProperty("i18n_keyed", True)
        for key in word_captions.CHOICES:
            self.caption_look.addItem(word_captions.CHOICE_NAMES[key], word_captions.CHOICE_NAMES[key])
        saved_look = self.settings.value("captions/look", "vurgu")
        self.caption_look.setCurrentIndex(word_captions.CHOICES.index(saved_look)
                                          if saved_look in word_captions.CHOICES else 1)
        self.caption_look.setAccessibleName("Altyazı görünümü")
        self.caption_look.currentIndexChanged.connect(
            lambda index: self.settings.setValue("captions/look", word_captions.CHOICES[max(0, index)]))
        v.addWidget(self.caption_look)
        self.apply_captions_button = QPushButton('Yerel altyazıyı zaman çizelgesine ekle')
        self.apply_captions_button.setEnabled(False)
        self.apply_captions_button.clicked.connect(self.apply_local_captions)
        v.addWidget(self.apply_captions_button)

        self.tts_input = QPlainTextEdit()
        self.tts_input.setPlaceholderText('Seslendirme metni')
        self.tts_input.setFixedHeight(75)
        v.addWidget(self.tts_input)
        self.tts_voice = QComboBox()
        self.tts_voice.setProperty("i18n_skip", True)  # voice names are the system's own
        self.tts_voice.addItem(self.ui_text('Konuşma diline uygun ses'), None)
        for voice_id, name, language in tts_service.voices():
            self.tts_voice.addItem(f'{name} ({language})', voice_id)
        self.tts_voice.setToolTip('Seslendirmeyi okuyacak Windows sesi. Yeni ses dili Windows Ayarları › Zaman ve dil › Konuşma bölümünden eklenir.')
        v.addWidget(self.tts_voice)
        self.tts_to_timeline = QCheckBox('Oynatma çizgisinden zaman çizelgesine ekle')
        self.tts_to_timeline.setChecked(True)
        v.addWidget(self.tts_to_timeline)
        tts_button = QPushButton('Windows sesiyle WAV oluştur')
        tts_button.clicked.connect(self.create_voiceover)
        v.addWidget(tts_button)
        tts_hint = QLabel('Çevrimdışı Windows sistem sesi kullanılır; dil ve ses işletim sisteminde yüklü seslere bağlıdır.')
        tts_hint.setWordWrap(True)
        v.addWidget(tts_hint)

        v.addStretch()
        return self.scroll_page(content)

    def load_speech_settings(self) -> None:
        speech_settings.set_current(str(self.settings.value("speech/language", speech_settings.DEFAULT_LANGUAGE)),
                                    str(self.settings.value("speech/vocabulary", "") or ""))
        chosen = speech_settings.language() or speech_settings.AUTO
        self.speech_language.setCurrentIndex(max(0, self.speech_language.findData(chosen)))
        self.speech_vocabulary.setText(speech_settings.vocabulary())

    def save_speech_settings(self) -> None:
        """The user changed the speech language or the term list: use it from now on and remember it."""
        speech_settings.set_current(self.speech_language.currentData(), self.speech_vocabulary.text())
        self.speech_vocabulary.setText(speech_settings.vocabulary())
        self.settings.setValue("speech/language", speech_settings.language() or speech_settings.AUTO)
        self.settings.setValue("speech/vocabulary", speech_settings.vocabulary())

    def section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def keyed_combo(keys) -> QComboBox:
        """A combo whose items carry a stable key as item data; the shown text may be translated."""
        combo = QComboBox()
        for key in keys:
            combo.addItem(key, key)
        combo.setProperty("i18n_keyed", True)
        return combo

    @staticmethod
    def select_choice(combo: QComboBox, key) -> bool:
        """Select the item whose key is `key`; returns False (selection unchanged) when there is none."""
        index = combo.findData(key)
        if index < 0:
            return False
        combo.setCurrentIndex(index)
        return True

    def select_aspect(self, value) -> str:
        """Select an aspect from a key, an older file's display text (Turkish or English) or a bare ratio."""
        key = i18n.choice_key(i18n.ASPECTS, value)
        if key is None:
            log.warning("Bilinmeyen tuval oranı %r; varsayılan kullanılıyor", value)
            key = i18n.DEFAULT_ASPECT
        self.select_choice(self.aspect, key)
        return key

    def select_export_profile(self, value) -> str:
        key = i18n.choice_key(i18n.EXPORT_PROFILES, value)
        if key is None:
            log.warning("Bilinmeyen dışa aktarma profili %r; varsayılan kullanılıyor", value)
            key = i18n.DEFAULT_EXPORT_PROFILE
        self.select_choice(self.export_profile, key)
        return key

    def select_speed(self, value) -> float:
        """Select the offered speed nearest to `value` (1.25, '1.25×'). Raises ValueError for a non-number."""
        speed = i18n.speed_key(value)
        self.select_choice(self.speed, speed)
        return speed

    def speed_value(self) -> float:
        return float(self.speed.currentData())

    def build_edit_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(14)
        v.addWidget(self.section("TUVAL ORANI"))
        self.aspect = self.keyed_combo(i18n.ASPECTS)
        self.aspect.currentIndexChanged.connect(lambda _index: self.change_aspect(self.aspect.currentData()))
        v.addWidget(self.aspect)

        v.addWidget(self.section("OYNATMA HIZI"))
        self.speed = QComboBox()
        for value in i18n.SPEEDS:
            self.speed.addItem(f"{value:.2f}×", value)
        self.select_speed(1.0)
        self.speed.currentIndexChanged.connect(lambda _index: self.change_speed(self.speed.currentData()))
        v.addWidget(self.speed)
        # A whole-video fade and look effects are not in the shared timeline renderer: the controls exist
        # (older code and projects refer to them) but are not shown, so nothing on screen does nothing.
        self.fade = QCheckBox("Yumuşak giriş ve çıkış geçişi")
        self.fade.setEnabled(False)
        self.fade.hide()
        self.effect = self.keyed_combo(i18n.EFFECTS)
        self.effect.setEnabled(False)
        self.effect.hide()

        v.addWidget(self.section("RENK VE IŞIK"))
        self.brightness = self.add_slider(v, "Parlaklık", -50, 50, lambda x: self.change_color("brightness", x))
        self.contrast = self.add_slider(v, "Kontrast", -50, 50, lambda x: self.change_color("contrast", x))
        self.saturation = self.add_slider(v, "Doygunluk", -50, 50, lambda x: self.change_color("saturation", x))

        vivid = QPushButton("Canlı görünüm uygula")
        vivid.setObjectName("secondary")
        vivid.clicked.connect(lambda: self.apply_preset(5, 10, 18))
        v.addWidget(vivid)
        natural = QPushButton("Doğal görünüme dön")
        natural.setObjectName("ghost")
        natural.clicked.connect(lambda: self.apply_preset(0, 0, 0))
        v.addWidget(natural)

        v.addWidget(self.section("BAŞLIK KATMANI"))
        self.overlay = QLineEdit()
        self.overlay.setPlaceholderText("Videonun başında görünecek kısa başlık")
        self.overlay.setToolTip("Enter'a basınca uygulanır; yazıyı silip Enter'a basınca başlık kalkar.")
        self.overlay.editingFinished.connect(self.set_title_layer)
        v.addWidget(self.overlay)
        hint = QLabel("Başlık, videonun başına 3 saniyelik bir yazı klibi olarak eklenir; zaman çizelgesinde taşıyıp uzatabilirsiniz.")
        hint.setWordWrap(True)
        hint.setObjectName("mutedSmall")
        v.addWidget(hint)
        v.addStretch()
        return self.scroll_page(content)

    def add_slider(self, layout: QVBoxLayout, name: str, low: int, high: int, callback) -> QSlider:
        row = QHBoxLayout()
        label = QLabel(name)
        value = QLabel("0")
        value.setObjectName("mono")
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value)
        layout.addLayout(row)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.valueChanged.connect(lambda x: (value.setText(f"{x:+d}"), callback(x)))
        slider.value_label = value  # kept current by hand when a value is restored with signals blocked
        layout.addWidget(slider)
        return slider

    def build_publish_tab(self) -> QWidget:
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(16, 18, 16, 18)
        v.setSpacing(12)
        v.addWidget(self.section("YAYIN PAKETİ"))
        v.addWidget(QLabel("Dışa aktarma profili"))
        self.export_profile = self.keyed_combo(i18n.EXPORT_PROFILES)
        self.export_profile.currentIndexChanged.connect(
            lambda _index: self.change_export_profile(self.export_profile.currentData()))
        v.addWidget(self.export_profile)
        profile_hint = QLabel('Profil oranı seçer; 4K seçenekleri seçili oranı iki kat çözünürlükte dışa aktarır.')
        profile_hint.setWordWrap(True)
        v.addWidget(profile_hint)
        three = QPushButton("Üç biçimde dışa aktar")
        three.setObjectName("secondary")
        three.setToolTip("Aynı kurguyu tek seferde dikey (9:16), kare (1:1) ve yatay (16:9) üç ayrı dosya olarak kaydeder.")
        three.clicked.connect(self.export_three_formats)
        v.addWidget(three)
        shorts = QPushButton("Shorts'a böl…")
        shorts.setObjectName("secondary")
        shorts.setToolTip("Videonun tamamını art arda dikey kısa videolara böler ve hepsini dışa aktarır.")
        shorts.clicked.connect(self.export_shorts)
        v.addWidget(shorts)
        best = QPushButton("Öne çıkan anları bul…")
        best.setObjectName("secondary")
        best.setToolTip("Videonun en canlı bölümlerini gerekçesiyle listeler; seçtiklerinizi dikey kısa video olarak kaydeder.")
        best.clicked.connect(self.find_highlights)
        v.addWidget(best)
        handoff = QPushButton("Kurgu dosyası olarak aktar (DaVinci Resolve)")
        handoff.setObjectName("secondary")
        handoff.setToolTip("Kesimleri FCPXML dosyası olarak kaydeder; DaVinci Resolve ve Final Cut Pro aynı kurguyu "
                           "özgün videolarla açar. Video oluşturulmaz.")
        handoff.clicked.connect(self.export_fcpxml)
        v.addWidget(handoff)
        batch = QPushButton("Toplu dışa aktar…")
        batch.setObjectName("secondary")
        batch.setToolTip("Birden çok videoyu aynı biçimde işleyip her birini ayrı dosya olarak kaydeder.")
        batch.clicked.connect(self.export_batch)
        v.addWidget(batch)
        v.addWidget(self.section("SES İYİLEŞTİRME"))
        self.loudness = QCheckBox("Ses yüksekliğini -14 LUFS'a normalleştir")
        self.loudness.setToolTip("Kısık çekilmiş videoyu yayın düzeyine çıkarır; önizlemede ve dışa aktarmada uygulanır.")
        self.noise_reduction = QCheckBox("Temel gürültü azaltma")
        self.noise_reduction.setToolTip("Videonun kendi sesindeki uğultu ve hışırtıyı hafifletir; müziğe dokunmaz. Sonucu dinleyerek karar verin.")
        self.music_duck = QCheckBox("Konuşurken müziği kıs")
        self.music_duck.setToolTip("Videoda biri konuşurken ses izlerindeki müzik alçalır, susunca geri yükselir.")
        for box, name in self.audio_boxes():
            box.toggled.connect(lambda checked, name=name: self.change_audio(name, checked))
            v.addWidget(box)
        v.addWidget(QLabel("AI Başlık"))
        self.publish_title = QLineEdit()
        self.publish_title.setPlaceholderText("Başlık önerisi")
        v.addWidget(self.publish_title)
        v.addWidget(QLabel("Açıklama"))
        self.publish_caption = QPlainTextEdit()
        self.publish_caption.setPlaceholderText("Video açıklaması")
        self.publish_caption.setMinimumHeight(140)
        v.addWidget(self.publish_caption)
        v.addWidget(QLabel("Etiketler"))
        self.publish_tags = QPlainTextEdit()
        self.publish_tags.setPlaceholderText("#reels #video")
        self.publish_tags.setMaximumHeight(100)
        v.addWidget(self.publish_tags)
        copy = QPushButton("Yayın metnini panoya kopyala")
        copy.setObjectName("secondary")
        copy.clicked.connect(self.copy_publish_text)
        v.addWidget(copy)
        note = QLabel("Instagram'a doğrudan yükleme bu sürümde yoktur. Videoyu filigransız dışa aktarabilir ve yayın paketini kopyalayabilirsiniz.")
        note.setWordWrap(True)
        note.setObjectName("mutedSmall")
        v.addWidget(note)
        v.addStretch()
        return self.scroll_page(content)
