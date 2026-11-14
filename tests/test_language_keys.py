"""Whole-string language switching, stable combo keys in project files, and prompt-edit settings/colour."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import i18n, project_service
from akis.timeline_model import Clip, Timeline, Track
from main import EditState, MainWindow

app = QApplication.instance() or QApplication([])


class I18nTests(unittest.TestCase):
    def test_choice_key_maps_keys_turkish_english_and_bare_ratios(self):
        self.assertEqual(i18n.choice_key(i18n.ASPECTS, '1:1 · Kare'), '1:1 · Kare')
        self.assertEqual(i18n.choice_key(i18n.ASPECTS, '1:1 · Square'), '1:1 · Kare')
        self.assertEqual(i18n.choice_key(i18n.ASPECTS, 'Source ratio'), 'Kaynak oranı')
        self.assertEqual(i18n.choice_key(i18n.ASPECTS, '16:9'), '16:9 · YouTube')
        self.assertEqual(i18n.choice_key(i18n.EXPORT_PROFILES, '4K Vertical · 2160×3840'), '4K Dikey · 2160×3840')
        self.assertIsNone(i18n.choice_key(i18n.ASPECTS, '21:9 · Sinema'))
        self.assertEqual(i18n.speed_key('1.25×'), 1.25)
        self.assertEqual(i18n.speed_key(1.1), 1.0)
        with self.assertRaises(ValueError):
            i18n.speed_key('hızlı')

    def test_translation_is_whole_string_only(self):
        self.assertEqual(i18n.translate('Ses', 'en'), 'Audio')
        self.assertEqual(i18n.translate('Ses kaydı 1', 'en'), 'Ses kaydı 1')
        self.assertEqual(i18n.source_of('Audio'), 'Ses')
        self.assertEqual(i18n.source_of('Audio kaydı'), 'Audio kaydı')


class WindowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = self.new_window()

    def new_window(self):
        window = MainWindow()
        window.apply_language('tr')  # independent of the language saved on this machine
        patch.object(window.preview, 'request').start()
        self.addCleanup(self.close, window)
        return window

    @staticmethod
    def close(window):
        window._close_confirmed = True
        window.close()

    def video(self, name='a.mp4'):
        path = self.root / name
        path.touch()
        return path

    def save_as(self, window, path):
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(path), '')):
            window.save_project()

    def open(self, window, path):
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(path), '')), \
             patch('main.QMessageBox.critical') as critical, patch('main.QMessageBox.warning'):
            window.open_project()
        critical.assert_not_called()


class LanguageTests(WindowCase):
    def test_switching_language_leaves_user_content_intact(self):
        w = self.window
        w.load_video(str(self.video('Ses kaydı 1.mp4')))
        w.publish_title.setText('Ses ve müzik')
        subtitle = w.project_subtitle.text()
        w.apply_language('en')
        self.assertEqual(w.project_title.text(), 'Ses kaydı 1')
        self.assertEqual(w.tts_input.placeholderText(), 'Seslendirme metni / Voiceover text')
        texts = [label.text() for label in w.findChildren(type(w.project_title))]
        self.assertIn('Audio', texts)  # the volume label: exactly "Ses"
        self.assertNotIn('Audio kaydı 1', texts)
        self.assertEqual(w.media_list.item(0).text(), '▣  Ses kaydı 1.mp4')
        self.assertEqual(w.aspect.currentText(), '9:16 · Reels / Shorts')
        w.apply_language('tr')
        self.assertEqual(w.project_title.text(), 'Ses kaydı 1')
        self.assertEqual(w.project_subtitle.text(), subtitle)
        self.assertEqual(w.publish_title.text(), 'Ses ve müzik')
        self.assertIn('Ses', [label.text() for label in w.findChildren(type(w.project_title))])
        self.assertEqual(w.tabs.tabText(0), '✦ AI Kurgu')

    def test_placeholder_header_follows_language_until_a_video_is_loaded(self):
        w = self.window
        w.apply_language('en')
        self.assertEqual(w.project_title.text(), 'New project')
        w.apply_language('tr')
        self.assertEqual(w.project_title.text(), 'Yeni proje')

    def test_text_set_by_code_after_a_switch_is_translated_whole(self):
        w = self.window
        w.apply_language('en')
        w.fade.setText('Ses')  # code replaces a translated text: it becomes the new source
        w.apply_language('tr')
        self.assertEqual(w.fade.text(), 'Ses')
        w.apply_language('en')
        self.assertEqual(w.fade.text(), 'Audio')

    def test_project_saved_in_english_reopens_in_turkish(self):
        w = self.window
        w.load_video(str(self.video()))
        w.apply_language('en')
        w.select_export_profile('4K UHD · 3840×2160')  # also moves the aspect to 16:9
        w.aspect.setCurrentIndex(w.aspect.findData('1:1 · Kare'))
        w.speed.setCurrentIndex(w.speed.findData(1.5))
        self.assertEqual(w.aspect.currentText(), '1:1 · Square')
        project = self.root / 'english.akis.json'
        self.save_as(w, project)
        state = json.loads(project.read_text(encoding='utf-8'))['state']
        self.assertEqual((state['aspect'], state['export_profile'], state['speed']), ('1:1 · Kare', '4K UHD · 3840×2160', 1.5))

        other = self.new_window()
        self.open(other, project)
        self.assertEqual(other.aspect.currentData(), '1:1 · Kare')
        self.assertEqual(other.aspect.currentText(), '1:1 · Kare')
        self.assertEqual(other.speed.currentText(), '1.50×')
        self.assertEqual(other.export_profile.currentData(), '4K UHD · 3840×2160')
        self.assertEqual(other.export_canvas_size(), (2160, 2160))
        self.assertFalse(other.has_unsaved_changes())

    def test_old_project_with_display_text_and_dropped_fields_still_loads(self):
        video = self.video('old.mp4')
        project = self.root / 'old.akis.json'
        state = asdict(EditState(source=str(video), speed=1.25))
        # Written by an older version while the UI was English, with fields this version dropped.
        state.update(aspect='1:1 · Square', export_profile='4K Vertical · 2160×3840', effect='Sinematik',
                     fade=True, overlay_text='Başlık', noise_reduction=True, loudness_normalization=False)
        timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(video), 0, 60)])])
        project_service.save(project, project_service.make_document(state, timeline, {}, ''))
        w = self.window
        self.open(w, project)
        self.assertEqual(w.aspect.currentData(), '1:1 · Kare')
        self.assertEqual(w.state.aspect, '1:1 · Kare')
        self.assertEqual(w.export_profile.currentData(), '4K Dikey · 2160×3840')
        self.assertEqual(w.state.export_profile, '4K Dikey · 2160×3840')
        self.assertEqual(w.state.speed, 1.25)
        self.assertEqual(w.speed.currentText(), '1.25×')
        saved = w.project_document()['state']
        self.assertNotIn('effect', saved)
        self.assertEqual(saved['aspect'], '1:1 · Kare')

    def test_old_turkish_display_text_and_unknown_aspect(self):
        video = self.video('tr.mp4')
        project = self.root / 'tr.akis.json'
        state = asdict(EditState(source=str(video), aspect='4:5 · Instagram gönderisi', export_profile='YouTube · 1920×1080'))
        project_service.save(project, project_service.make_document(state, Timeline.from_legacy(state), {}, ''))
        self.open(self.window, project)
        self.assertEqual(self.window.aspect.currentData(), '4:5 · Instagram gönderisi')
        self.assertEqual(self.window.export_profile.currentData(), 'YouTube · 1920×1080')
        state['aspect'] = '21:9 · Sinema'  # nothing to map to: the default, not the previous project's value
        project_service.save(project, project_service.make_document(state, Timeline.from_legacy(state), {}, ''))
        self.window.aspect.setCurrentIndex(1)
        self.open(self.window, project)
        self.assertEqual(self.window.aspect.currentData(), i18n.DEFAULT_ASPECT)
        self.assertEqual(self.window.state.aspect, i18n.DEFAULT_ASPECT)

    def test_canvas_and_snapshot_use_keys_in_english(self):
        w = self.window
        w.load_video(str(self.video()))
        w.apply_language('en')
        w.aspect.setCurrentIndex(w.aspect.findData('Kaynak oranı'))
        self.assertEqual(w.aspect.currentText(), 'Source ratio')
        self.assertEqual(w.state.aspect, 'Kaynak oranı')
        with patch('akis.media_service.MediaService.dimensions', return_value=(640, 360)):
            self.assertEqual(w.canvas_size(), (640, 360))
        snapshot = w.open_snapshot()
        w.aspect.setCurrentIndex(0)
        w.apply_language('tr')
        w.restore_open_snapshot(snapshot)
        self.assertEqual(w.aspect.currentData(), 'Kaynak oranı')


class PromptEditTests(WindowCase):
    def apply(self, plan):
        w = self.window
        result = Timeline(tracks=[Track('video', 'Video', [Clip(w.state.source, 0, 30)])])
        with patch('akis.edit_plan.apply_plan', return_value=result), patch('akis.edit_plan.describe', return_value='özet'), \
             patch('main.QMessageBox.critical') as critical:
            w.on_prompt_edit(plan, [(w.state.source, 2.0)])
        critical.assert_not_called()

    def test_partial_colour_plan_keeps_other_sliders_and_undo_restores_all(self):
        w = self.window
        w.load_video(str(self.video()))
        w.apply_preset(3, 4, 5)
        self.apply({'color': {'brightness': 12}, 'aspect': '16:9', 'speed': 1.25})
        self.assertEqual((w.brightness.value(), w.contrast.value(), w.saturation.value()), (12, 4, 5))
        self.assertEqual((w.state.brightness, w.state.contrast, w.state.saturation), (12, 4, 5))
        self.assertEqual(w.aspect.currentData(), '16:9 · YouTube')
        self.assertEqual(w.state.speed, 1.25)
        self.assertTrue(w.undo())
        self.assertEqual((w.brightness.value(), w.contrast.value(), w.saturation.value()), (3, 4, 5))
        self.assertEqual(w.aspect.currentData(), i18n.DEFAULT_ASPECT)
        self.assertEqual(w.state.speed, 1.0)

    def test_prompt_worker_receives_current_settings(self):
        w = self.window
        w.load_video(str(self.video()))
        w.apply_language('en')
        w.apply_preset(-2, 7, 9)
        w.aspect.setCurrentIndex(w.aspect.findData('1:1 · Kare'))
        w.speed.setCurrentIndex(w.speed.findData(0.75))
        w.ai_prompt.setPlainText('sessizlikleri at')
        with patch.object(w, 'api_credentials', return_value=('k', 'm')), \
             patch.object(w, 'edit_sources', return_value=[(w.state.source, 2.0)]), \
             patch.object(w, 'start_worker'), patch('akis.window.assistant.PromptEditWorker') as worker:
            w.run_prompt_edit()
        settings = worker.call_args.kwargs['settings']
        self.assertEqual(settings, {'color': (-2, 7, 9), 'speed': '0.75×', 'aspect': '1:1 · Kare'})
        from akis import edit_plan
        line = edit_plan._settings_line(settings, None)
        self.assertIn('aspect 1:1', line)
        self.assertIn('speed 0.75', line)


if __name__ == '__main__':
    unittest.main()


class QtOwnTextsTests(unittest.TestCase):
    """Qt's standard buttons (Yes/No, Cancel, Save/Discard) follow the UI language, not stay English."""

    def tearDown(self):
        i18n.use_qt_language('en')

    def texts(self):
        from PySide6.QtWidgets import QDialogButtonBox
        B = QDialogButtonBox.StandardButton
        box = QDialogButtonBox(B.Yes | B.No | B.Cancel | B.Save)
        return {box.button(b).text().replace('&', '') for b in (B.Yes, B.No, B.Cancel, B.Save)}

    def test_turkish_ui_shows_turkish_standard_buttons_and_english_switches_back(self):
        self.assertTrue(i18n.use_qt_language('tr'))
        self.assertEqual(self.texts(), {'Evet', 'Hayır', 'İptal', 'Kaydet'})
        self.assertFalse(i18n.use_qt_language('en'))
        self.assertEqual(self.texts(), {'Yes', 'No', 'Cancel', 'Save'})

    def test_the_window_installs_it_with_its_language(self):
        w = MainWindow()
        try:
            w.apply_language('tr')
            self.assertIn('Evet', self.texts())
            w.apply_language('en')
            self.assertIn('Yes', self.texts())
        finally:
            w.close()
            w.deleteLater()
