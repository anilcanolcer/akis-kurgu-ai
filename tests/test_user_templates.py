"""The user's own templates: capture, the file on disk, applying one, the dialog and the main window."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import user_templates
from akis.saved_templates_dialog import SavedTemplatesDialog
from akis.template_dialog import TemplateDialog
from akis.template_service import TEMPLATES
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


def project():
    return Timeline(tracks=[Track('video', 'Ana video', [Clip('a.mp4', 0, 90)]), Track('audio', 'Müzik'),
                            Track('text', 'Başlık', [Clip('', 0, 60, text='Haftanın özeti')])])


def sample(name='Haftalık vlog'):
    return user_templates.capture(name, project(), aspect='9:16 · Reels / Shorts', color=(5, 10, -4), speed=1.25,
                                  audio=('level', 'duck'))


class CaptureTests(unittest.TestCase):
    def test_takes_structure_and_settings_but_no_media(self):
        item = sample('  Haftalık   vlog ')
        self.assertEqual(item, {'name': 'Haftalık vlog', 'aspect': '9:16 · Reels / Shorts',
                                'tracks': [['video', 'Ana video'], ['audio', 'Müzik'], ['text', 'Başlık']],
                                'title': 'Haftanın özeti', 'color': [5, 10, -4], 'speed': 1.25, 'audio': ['duck', 'level']})
        self.assertNotIn('a.mp4', json.dumps(item))

    def test_needs_a_name(self):
        with self.assertRaises(ValueError):
            sample('   ')


class FileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / 'data'            # does not exist yet

    def test_saved_templates_come_back_and_same_name_replaces(self):
        self.assertEqual(user_templates.load(self.folder), [])
        user_templates.add(self.folder, sample('A'))
        user_templates.add(self.folder, sample('B'))
        changed = dict(sample('a'), speed=0.75)             # same name in another case
        items = user_templates.add(self.folder, changed)
        self.assertEqual([(item['name'], item['speed']) for item in items], [('B', 1.25), ('a', 0.75)])
        self.assertEqual(user_templates.load(self.folder), items)
        self.assertEqual([item['name'] for item in user_templates.remove(self.folder, 'B')], ['a'])
        self.assertFalse((self.folder / 'templates.json.tmp').exists())

    def test_damaged_or_hostile_file_is_empty_and_left_in_place(self):
        self.folder.mkdir()
        path = self.folder / user_templates.FILE_NAME
        for content in ('{not json', '{"a": 1}', '[1, "x", null]'):
            path.write_text(content, encoding='utf-8')
            self.assertEqual(user_templates.load(self.folder), [])
            self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_bad_values_are_dropped_or_clamped(self):
        self.folder.mkdir()
        entries = [dict(sample('İyi'), color=[900, -900, 3], audio=['level', 'bass'], tracks=[['video', 'V'], ['hologram', 'X']]),
                   dict(sample('Hız'), speed=9), dict(sample('Renk'), color=[1, 2]), {'name': 'Eksik'}]
        (self.folder / user_templates.FILE_NAME).write_text(json.dumps(entries), encoding='utf-8')
        items = user_templates.load(self.folder)
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]['color'], items[0]['audio'], items[0]['tracks']), ([50, -50, 3], ['level'], [['video', 'V']]))


class ApplyTests(unittest.TestCase):
    def test_adds_missing_tracks_and_the_title_without_touching_clips(self):
        timeline = Timeline(tracks=[Track('video', 'Ana video', [Clip('b.mp4', 0, 30)])])
        user_templates.apply(timeline, sample())
        self.assertEqual([(t.kind, t.name) for t in timeline.tracks], [('video', 'Ana video'), ('audio', 'Müzik'), ('text', 'Başlık')])
        self.assertEqual(timeline.tracks[0].clips[0].source, 'b.mp4')
        self.assertEqual([c.text for c in timeline.tracks[2].clips], ['Haftanın özeti'])
        user_templates.apply(timeline, sample())            # a second time: no duplicate tracks, title after the first
        self.assertEqual(len(timeline.tracks), 3)
        self.assertEqual([c.start for c in timeline.tracks[2].clips], [0, 90])

    def test_template_without_text_track_or_title_adds_no_title(self):
        item = dict(sample(), tracks=[['video', 'Ana video']], title='Başlık')
        timeline = Timeline()
        user_templates.apply(timeline, item)
        self.assertEqual([(t.kind, len(t.clips)) for t in timeline.tracks], [('video', 0)])

    def test_description_mentions_what_will_change(self):
        text = user_templates.describe(sample())
        for part in ('Ana video / Müzik / Başlık', '1.25×', '+5 / +10 / -4', 'müzik kısma, ses eşitleme', 'Haftanın özeti'):
            self.assertIn(part, text)


class DialogTests(unittest.TestCase):
    def test_empty_list_says_so_and_cannot_apply(self):
        dialog = SavedTemplatesDialog()
        self.assertIsNone(dialog.selection())
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertFalse(dialog.delete_button.isEnabled())
        self.assertTrue(dialog.save_button.isHidden())
        self.assertIn('Henüz kayıtlı şablonunuz yok', dialog.details.text())

    def test_saved_templates_are_listed_with_their_details(self):
        dialog = SavedTemplatesDialog(saved=[sample(), sample('İkinci')], save=lambda name: [], delete=lambda name: [])
        self.assertEqual([dialog.list.item(i).text() for i in range(dialog.list.count())], ['Haftalık vlog', 'İkinci'])
        self.assertEqual(dialog.selection()['name'], 'Haftalık vlog')
        self.assertIn('1.25×', dialog.details.text())
        self.assertTrue(dialog.apply_button.isEnabled())
        dialog.list.setCurrentRow(1)
        self.assertEqual(dialog.selection()['name'], 'İkinci')

    def test_save_and_delete_go_through_the_host_and_refresh_the_list(self):
        store = []

        def save(name):
            store.append(sample(name))
            return list(store)

        def delete(name):
            store[:] = [item for item in store if item['name'] != name]
            return list(store)
        dialog = SavedTemplatesDialog(saved=[], save=save, delete=delete)
        with patch('akis.saved_templates_dialog.QInputDialog.getText', return_value=('  Ürün  ', True)):
            dialog.save_current()
        self.assertEqual([item['name'] for item in store], ['Ürün'])
        self.assertEqual(dialog.selection()['name'], 'Ürün')              # the new one is selected
        with patch('akis.saved_templates_dialog.QInputDialog.getText', return_value=('', True)):
            dialog.save_current()                                          # no name: nothing happens
        self.assertEqual(len(store), 1)
        with patch('akis.saved_templates_dialog.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            dialog.delete_selected()
        self.assertEqual(len(store), 1)
        with patch('akis.saved_templates_dialog.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            dialog.delete_selected()
        self.assertEqual(store, [])
        self.assertIsNone(dialog.selection())

    def test_same_name_asks_before_overwriting(self):
        calls = []
        dialog = SavedTemplatesDialog(saved=[sample('Ürün')], save=lambda name: calls.append(name) or [sample(name)])
        with patch('akis.saved_templates_dialog.QInputDialog.getText', return_value=('ürün', True)), \
             patch('akis.saved_templates_dialog.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            dialog.save_current()
        self.assertEqual(calls, [])

    def test_english_ui_is_translated(self):
        dialog = SavedTemplatesDialog(language='en')
        self.assertEqual(dialog.windowTitle(), 'My templates')
        self.assertEqual(dialog.save_button.text(), 'Save this project as a template')
        self.assertEqual(dialog.details.text(), 'You have no saved templates yet.')

    def test_templates_dialog_offers_the_way_in(self):
        dialog = TemplateDialog()
        results = []
        dialog.done = results.append
        dialog.saved_button.click()
        self.assertEqual(results, [TemplateDialog.SAVED])
        self.assertNotIn(TemplateDialog.SAVED, (0, 1))                    # not mistaken for cancel or apply


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.app_support.app_data_dir', return_value=self.root / 'data').start()
        patch('akis.media_service.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_project_is_captured_saved_and_applied_again(self):
        w = self.window
        w.apply_preset(7, -3, 12)
        w.select_speed(1.5)
        w.select_aspect('1:1 · Kare')
        w.loudness.setChecked(True)
        item = w.capture_template('Benim düzenim')
        self.assertEqual((item['color'], item['speed'], item['aspect'], item['audio']), ([7, -3, 12], 1.5, '1:1 · Kare', ['level']))
        user_templates.add(self.root / 'data', item)

        w.apply_preset(0, 0, 0)
        w.select_speed(1.0)
        w.select_aspect('16:9 · YouTube')
        w.loudness.setChecked(False)

        def choose(dialog):
            self.assertEqual([entry['name'] for entry in dialog.saved], ['Benim düzenim'])
            return 1
        with patch('akis.template_dialog.TemplateDialog.exec', new=lambda dialog: TemplateDialog.SAVED), \
             patch('akis.saved_templates_dialog.SavedTemplatesDialog.exec', new=choose):
            w.show_templates()
        self.assertEqual((w.brightness.value(), w.contrast.value(), w.saturation.value()), (7, -3, 12))
        self.assertEqual(w.speed_value(), 1.5)
        self.assertEqual(w.aspect.currentData(), '1:1 · Kare')
        self.assertTrue(w.loudness.isChecked())
        self.assertEqual(w.render_adjustments()['audio'], ('level',))
        self.assertIn('Benim düzenim uygulandı', w.status_label.text())
        self.assertTrue(w.undo())                                     # colour, speed, aspect and tracks: one step
        self.assertEqual((w.brightness.value(), w.speed_value(), w.aspect.currentData()), (0, 1.0, '16:9 · YouTube'))

    def test_dismissing_my_templates_changes_nothing(self):
        w = self.window
        with patch('akis.template_dialog.TemplateDialog.exec', new=lambda dialog: TemplateDialog.SAVED), \
             patch('akis.saved_templates_dialog.SavedTemplatesDialog.exec', new=lambda dialog: 0):
            w.show_templates()
        self.assertFalse(w.undo())

    def test_built_in_templates_still_apply(self):
        w = self.window
        with patch('akis.template_dialog.TemplateDialog.exec', new=lambda dialog: 1):
            w.show_templates()
        self.assertIn(TEMPLATES[0].name, w.status_label.text())


if __name__ == '__main__':
    unittest.main()
