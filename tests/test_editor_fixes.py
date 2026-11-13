"""Work before a main video, source length of the first clip, English UI gaps, shortcuts, persistence and
smaller editor fixes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

import main
from akis import i18n, inspiration_service, project_service, timeline_render
from akis.inspiration_dialog import InspirationDialog
from akis.timeline_model import Clip, Timeline, Track
from main import MainWindow

app = QApplication.instance() or QApplication([])
YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


class WindowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.recovery = self.root / 'recovery'
        patch('akis.app_support.recovery_dir', return_value=self.recovery).start()
        patch('akis.media_service.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = self.new_window()

    def new_window(self):
        with patch('akis.ai_providers.load_key', return_value=''):
            window = MainWindow()
        window.apply_language('tr')
        patch.object(window.preview, 'request').start()
        patch.object(window.multitrack_view, 'refresh_waveforms').start()
        self.addCleanup(self.close, window)
        return window

    @staticmethod
    def close(window):
        window._close_confirmed = True
        window.close()

    def file(self, name):
        path = self.root / name
        path.touch()
        return path

    def add_media(self, window, path, track=1):
        window.multitrack_view.selected_track = track
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(path), '')), \
             patch('main.timeline_service.validate_track_media'):
            window.add_timeline_media()

    def clips(self, window, kind):
        return [(c.source, c.start, c.length) for t in window.multitrack.tracks if t.kind == kind for c in t.clips]


class WorkBeforeVideoTests(WindowCase):
    def test_media_before_a_video_is_unsaved_autosaved_and_saved(self):
        w = self.window
        self.assertFalse(w.has_content())
        self.assertFalse(w.has_unsaved_changes())
        music = self.file('müzik.wav')
        self.add_media(w, music)
        self.assertEqual(self.clips(w, 'audio'), [(str(music), 0, 60)])
        self.assertTrue(w.has_content())
        self.assertTrue(w.has_unsaved_changes())
        self.assertTrue(w.autosave_project())
        recovered = json.loads(Path(w._autosave_file).read_text(encoding='utf-8'))
        self.assertEqual(recovered['timeline']['tracks'][1]['clips'][0]['source'], str(music))
        project = self.root / 'sessiz.akis.json'
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(project), '')), \
             patch('main.QMessageBox.information') as info:
            w.save_project()
        info.assert_not_called()
        self.assertTrue(project.exists())
        self.assertFalse(w.has_unsaved_changes())

    def test_close_asks_when_only_media_was_added(self):
        w = self.window
        self.add_media(w, self.file('müzik.wav'))
        with patch.object(w, 'isVisible', return_value=True), \
             patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Cancel) as ask:
            self.assertFalse(w.confirm_close())
        ask.assert_called_once()

    def test_loading_a_video_keeps_earlier_work(self):
        w = self.window
        music = self.file('müzik.wav')
        self.add_media(w, music)
        video = self.file('a.mp4')
        self.assertTrue(w.load_video(str(video)))
        self.assertEqual(self.clips(w, 'audio'), [(str(music), 0, 60)])
        self.assertEqual(self.clips(w, 'video'), [(str(video), 0, 60)])
        self.assertEqual(w.state.source, str(video))
        self.assertIn(str(music), w.media_bin.paths)
        self.assertTrue(w.has_unsaved_changes())  # the earlier work was never saved
        self.assertTrue(w.undo())  # adding the video is its own step
        self.assertEqual(self.clips(w, 'video'), [])
        self.assertEqual(self.clips(w, 'audio'), [(str(music), 0, 60)])

    def test_project_without_main_video_reopens(self):
        w = self.window
        music = self.file('müzik.wav')
        self.add_media(w, music)
        project = self.root / 'sessiz.akis.json'
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(project), '')):
            w.save_project()
        other = self.new_window()
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(project), '')), \
             patch('main.QMessageBox.critical') as critical, patch('main.QMessageBox.warning') as warning:
            other.open_project()
        critical.assert_not_called()
        warning.assert_not_called()
        self.assertEqual(self.clips(other, 'audio'), [(str(music), 0, 60)])
        self.assertEqual(other.state.source, '')
        self.assertEqual(other.project_path, str(project))
        self.assertEqual(other.project_title.text(), 'sessiz')
        self.assertFalse(other.has_unsaved_changes())

    def test_project_service_still_refuses_a_lost_main_video(self):
        timeline = Timeline(tracks=[Track('audio', 'A', [Clip(str(self.file('m.wav')), 0, 30)])])
        project = self.root / 'p.akis.json'
        project_service.save(project, project_service.make_document({'source': str(self.root / 'gone.mp4')},
                                                                    timeline, {}, ''))
        with self.assertRaises(FileNotFoundError):
            project_service.load_project(project)


class SourceLengthTests(WindowCase):
    def test_first_clip_cannot_be_trimmed_past_its_source(self):
        timeline = Timeline.from_legacy({'source': 'a.mp4', 'start': 0, 'end': 2.0, 'duration': 2.0})
        track = timeline.tracks[0]
        clip = track.clips[0]
        self.assertEqual(clip.source_length, 60)
        with self.assertRaises(ValueError):
            track.trim_end(clip.id, 90)
        track.trim_end(clip.id, 30)  # shortening is still fine
        track.trim_end(clip.id, 60)

    def test_loaded_video_clip_has_source_length(self):
        w = self.window
        w.load_video(str(self.file('a.mp4')))
        self.assertEqual(w.multitrack.tracks[0].clips[0].source_length, 60)

    def test_old_project_gets_source_length_on_open(self):
        video, music = self.file('a.mp4'), self.file('m.wav')
        timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(video), 0, 30, source_in=10)]),
                                    Track('audio', 'Audio', [Clip(str(music), 0, 45)]),
                                    Track('text', 'Text', [Clip('', 0, 30, text='yazı')])])
        project = self.root / 'eski.akis.json'
        project_service.save(project, project_service.make_document({'source': str(video)}, timeline, {}, ''))
        w = self.window
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(project), '')), \
             patch('main.QMessageBox.critical') as critical:
            w.open_project()
        critical.assert_not_called()
        lengths = [c.source_length for t in w.multitrack.tracks for c in t.clips]
        self.assertEqual(lengths, [60, 60, None])  # 2 s at 30 fps; text has no source
        self.assertFalse(w.has_unsaved_changes())


class EnglishUiTests(WindowCase):
    def nav(self, word):
        return next(b for b in self.window.findChildren(QPushButton) if b.property('nav') and word in b.text())

    def button(self, text):
        return next(b for b in self.window.findChildren(QPushButton) if b.text() == text)

    def test_sidebar_toolbar_and_tooltips_switch_language(self):
        w = self.window
        inspiration, toolbar = self.nav('İlham'), self.button('Böl')
        tts_hint = 'Çevrimdışı Windows sistem sesi kullanılır; dil ve ses işletim sisteminde yüklü seslere bağlıdır.'
        w.apply_language('en')
        self.assertEqual(inspiration.text(), '✦   Inspiration')
        self.assertEqual(toolbar.text(), 'Split')
        self.assertEqual(self.button('Save project').toolTip(), 'Saves the project (Ctrl+S)')
        self.assertEqual(w.cancel_button.toolTip(), 'Stops the running task.')
        self.assertEqual(w.play_button.toolTip(), 'Play / pause (Space)')
        labels = [label.text() for label in w.findChildren(type(w.project_title))]
        self.assertIn('Zoom', labels)
        self.assertIn('API transcription model', labels)
        self.assertNotIn(tts_hint, labels)
        w.apply_language('tr')
        self.assertEqual(inspiration.text(), '✦   İlham')
        self.assertEqual(toolbar.text(), 'Böl')
        self.assertEqual(self.button('Projeyi kaydet').toolTip(), 'Projeyi kaydeder (Ctrl+S)')
        self.assertEqual(w.play_button.toolTip(), 'Oynat / duraklat (Boşluk)')

    def test_inspiration_dialog_follows_the_language(self):
        dialog = InspirationDialog(language='en')
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.windowTitle(), 'Inspiration')
        self.assertEqual(dialog.prompt_button.text(), 'Write idea into edit request')
        self.assertEqual(dialog.category.itemText(0), 'All')
        self.assertIn('Shot list', dialog.details.toHtml())
        self.assertEqual(InspirationDialog().prompt_button.text(), 'Fikri kurgu isteğine yaz')
        seen = []
        fake = type('FakeDialog', (), {'__init__': lambda self, *a, **k: seen.append(k), 'exec': lambda self: 0})
        with patch('akis.window.assistant.InspirationDialog', fake):
            self.window.show_inspiration()
        self.assertEqual(seen, [{'language': 'tr'}])

    def test_disabled_controls_say_not_available(self):
        w = self.window
        # Noise reduction and loudness now work (akis.audio_polish); the fade control is still a placeholder.
        self.assertFalse(w.fade.isEnabled())
        self.assertIn('(henüz yok)', w.fade.text())
        self.assertIn('(henüz yok)', w.overlay.placeholderText())
        self.assertTrue(w.noise_reduction.isEnabled())
        self.assertNotIn('(henüz yok)', w.noise_reduction.text())
        w.apply_language('en')
        self.assertIn('(not available yet)', w.fade.text())
        self.assertEqual(w.noise_reduction.text(), 'Basic noise reduction')
        w.apply_language('tr')

    def test_en_ui_stays_one_to_one(self):
        values = list(i18n.EN_UI.values())
        self.assertEqual(len(values), len(set(values)))


class EditorBehaviourTests(WindowCase):
    def test_pausing_does_not_hide_progress_of_running_export(self):
        w = self.window
        w.load_video(str(self.file('a.mp4')))
        w.progress.show()
        w._workers.add(object())  # an export is running
        w._play_when_ready = True
        w.stop_proxy_playback(refresh=False)
        self.assertFalse(w.progress.isHidden())
        w._workers.clear()
        w._play_when_ready = True
        w.stop_proxy_playback(refresh=False)
        self.assertTrue(w.progress.isHidden())

    def test_split_messages_are_turkish(self):
        w = self.window
        w.load_video(str(self.file('a.mp4')))
        w.multitrack_view.selected = None
        w.split_clip()
        self.assertEqual(w.status_label.text(), 'Önce bölünecek klibi seçin.')
        clip = w.multitrack.tracks[0].clips[0]
        w.multitrack_view.selected = (0, clip.id)
        w.multitrack_view.playhead = 0  # on the clip's edge: cannot split
        w.split_clip()
        self.assertIn('oynatma imlecini', w.status_label.text())
        self.assertNotIn('Split must', w.status_label.text())
        self.assertEqual(w._undo_stack, [])

    def test_removing_the_last_clip_clears_the_preview(self):
        w = self.window
        w.load_video(str(self.file('a.mp4')))
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        w.video.set_image(image)
        clip = w.multitrack.tracks[0].clips[0]
        w.multitrack_view.selected = (0, clip.id)
        w.ripple_delete()
        self.assertIsNone(w.video.image)
        w.show_timeline_frame('late.png')  # a frame rendered before the delete arrives late
        self.assertIsNone(w.video.image)

    def test_delete_key_removes_clip_leaving_gap_and_is_undoable(self):
        w = self.window
        w.load_video(str(self.file('a.mp4')))
        track = w.multitrack.tracks[0]
        track.clips[0].length = 30
        track.add(Clip(w.state.source, 30, 30, source_in=30, source_length=60))
        w.multitrack_view.selected = (0, track.clips[0].id)
        w.shortcut_actions['Delete'].trigger()
        self.assertEqual([(c.start, c.length) for c in w.multitrack.tracks[0].clips], [(30, 30)])
        w.undo()
        self.assertEqual(len(w.multitrack.tracks[0].clips), 2)

    def test_missing_media_error_names_the_problem(self):
        timeline = Timeline(tracks=[Track('video', 'V', [Clip(str(self.root / 'yok.mp4'), 0, 10)])])
        renderer = timeline_render.TimelineRenderer(object(), size=(64, 64))
        with self.assertRaises(FileNotFoundError) as caught:
            renderer._render(timeline, str(self.root / 'out.png'), frame=0)
        self.assertIn('Medya bulunamadı:', str(caught.exception))


class ShortcutTests(WindowCase):
    def test_shortcuts_and_tooltips(self):
        w = self.window
        self.assertEqual(set(w.shortcut_actions), {'Ctrl+S', 'Ctrl+O', 'Ctrl+E', 'Space', 'Delete'})
        with patch.object(w, 'save_project') as save:
            w.shortcut_actions['Ctrl+S'].trigger()
        save.assert_called_once()
        for text, keys in (('Proje aç', 'Ctrl+O'), ('Projeyi kaydet', 'Ctrl+S'), ('Dışa aktar  ↗', 'Ctrl+E')):
            button = next(b for b in w.findChildren(QPushButton) if b.text() == text)
            self.assertIn(keys, button.toolTip())

    def test_single_key_shortcuts_leave_text_fields_alone(self):
        w = self.window
        w.load_video(str(self.file('a.mp4')))
        w.multitrack_view.selected = (0, w.multitrack.tracks[0].clips[0].id)
        with patch('main.QApplication.focusWidget', return_value=w.ai_prompt), \
             patch.object(w, 'toggle_play') as play:
            w.shortcut_actions['Space'].trigger()
            w.shortcut_actions['Delete'].trigger()
        play.assert_not_called()
        self.assertEqual(len(w.multitrack.tracks[0].clips), 1)
        with patch('main.QApplication.focusWidget', return_value=w.multitrack_view), \
             patch.object(w, 'toggle_play') as play:
            w.shortcut_actions['Space'].trigger()
        play.assert_called_once()


class PersistenceTests(WindowCase):
    def settings(self):
        return QSettings(str(self.root / 'ayarlar.ini'), QSettings.Format.IniFormat)

    def test_provider_model_and_splitter_round_trip(self):
        w = self.window
        w.provider.setCurrentText('Gemini')
        w.model.setCurrentText('ozel-model')
        w.splitter.setSizes([700, 400])
        settings = self.settings()
        w.save_ui_settings(settings)
        settings.sync()
        other = self.new_window()
        other.restore_ui_settings(self.settings())
        self.assertEqual(other.provider.currentText(), 'Gemini')
        self.assertEqual(other.model.currentText(), 'ozel-model')

    def test_bad_values_are_ignored(self):
        settings = self.settings()
        for key, value in (('ui/provider', 'Yok böyle'), ('ui/model', ''), ('ui/geometry', 'çöp'),
                           ('ui/splitter', ['a', 'b'])):
            settings.setValue(key, value)
        w = self.window
        provider, sizes = w.provider.currentText(), w.splitter.sizes()
        w.restore_ui_settings(settings)
        self.assertEqual(w.provider.currentText(), provider)
        self.assertEqual(w.splitter.sizes(), sizes)

    def test_offscreen_window_does_not_touch_real_settings(self):
        self.assertFalse(self.window._persist_ui)

    def test_unticking_secure_storage_deletes_the_key(self):
        w = self.window
        w.remember_key.setChecked(True)
        with patch('main.ai_providers.delete_key', create=True) as delete:
            w.remember_key.click()  # user unticks
        delete.assert_called_once_with(main.APP_NAME, w.provider.currentText())
        self.assertNotIn(w.provider.currentText(), w._saved_providers)
        with patch('main.ai_providers.delete_key', create=True) as delete:
            w.remember_key.setChecked(True)  # code (load_key) changing the box never deletes
            w.load_key()
        delete.assert_not_called()

    def test_works_without_delete_key(self):
        w = self.window
        w.remember_key.setChecked(True)
        saved = getattr(main.ai_providers, 'delete_key', None)
        if saved is not None:
            delattr(main.ai_providers, 'delete_key')
            self.addCleanup(setattr, main.ai_providers, 'delete_key', saved)
        w.remember_key.click()
        self.assertIn('silinemiyor', w.status_label.text())


class InspirationPromptTests(WindowCase):
    def choose(self, answer):
        idea = inspiration_service.IDEAS[0]
        # A stand-in dialog: building the real one with the window as parent crashes PySide6 6.10 under
        # Python 3.14 in tests (the same access violation test_inspiration_flow hits on unmodified code).
        fake = type('FakeDialog', (), {'__init__': lambda self, *a, **k: None, 'exec': lambda self: 1,
                                       'selection': lambda self: (idea, 'prompt')})
        with patch('akis.window.assistant.InspirationDialog', fake), \
             patch('main.QMessageBox.question', return_value=answer) as ask:
            self.window.show_inspiration()
        return idea, ask

    def test_existing_request_is_kept_unless_confirmed(self):
        w = self.window
        w.ai_prompt.setPlainText('benim isteğim')
        idea, ask = self.choose(NO)
        self.assertEqual(ask.call_args.args[2], main.IDEA_REPLACES_PROMPT_QUESTION)
        self.assertEqual(w.ai_prompt.toPlainText(), 'benim isteğim')
        idea, ask = self.choose(YES)
        self.assertEqual(w.ai_prompt.toPlainText(), idea.prompt)

    def test_empty_request_is_filled_without_asking(self):
        idea, ask = self.choose(NO)
        ask.assert_not_called()
        self.assertEqual(self.window.ai_prompt.toPlainText(), idea.prompt)


class CloseTests(WindowCase):
    def test_close_stops_story_workers(self):
        from akis import story_workers
        with patch.object(story_workers, 'stop_all', create=True) as stop_all:
            self.close(self.window)
        stop_all.assert_called_once()


if __name__ == '__main__':
    unittest.main()
