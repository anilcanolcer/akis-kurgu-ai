"""English error messages, finding moved media, portable photos and undo keeping the selection."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import ast
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from akis import app_support, i18n, messages, project_service

app = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]
TURKISH = re.compile('[çğıöşüÇĞİÖŞÜ]')


def _template(node):
    """The text of a string, f-string or + concatenation with every filled-in value as {}."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace('{', '{{').replace('}', '}}')
    if isinstance(node, ast.JoinedStr):
        return ''.join(v.value.replace('{', '{{').replace('}', '}}') if isinstance(v, ast.Constant) else '{}'
                       for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return (_template(node.left) or '{}') + (_template(node.right) or '{}')
    return None


def raised_turkish_messages():
    """{template: where} for every Turkish text the application passes to an exception."""
    found = {}
    for path in sorted((ROOT / 'akis').rglob('*.py')) + [ROOT / 'main.py']:
        if path.name in ('i18n.py', 'inspiration_en.py', 'messages.py'):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and node.args:
                name = getattr(node.func, 'attr', None) or getattr(node.func, 'id', '')
                if name.endswith('Error') or name.endswith('Cancelled'):
                    text = _template(node.args[0])
                    if text and TURKISH.search(text):
                        found.setdefault(text, f'{path.name}:{node.lineno}')
    return found


class MessageTranslationTests(unittest.TestCase):
    def test_every_raised_turkish_message_has_an_english_text(self):
        untranslated = []
        for template, where in raised_turkish_messages().items():
            sample = template.format(*[f'X{i}' for i in range(template.count('{}'))])
            english = messages.message(sample, 'en')
            if english == sample or TURKISH.search(english.replace('Akış', '')):
                untranslated.append(f'{where}: {sample}')
        self.assertEqual(untranslated, [])

    def test_update_constants_are_translated(self):
        from akis import update_service
        for text in [update_service.VERIFY_FAILED, update_service.UAC_DECLINED,
                     *update_service.INSTALLER_EXIT_CODES.values()]:
            self.assertFalse(TURKISH.search(messages.message(text, 'en')), text)

    def test_templates_keep_their_values_and_turkish_is_unchanged(self):
        text = 'OpenAI 90 saniyede yanıt vermedi. Başka bir model deneyin veya tekrar deneyin.'
        self.assertEqual(messages.message(text, 'en'),
                         'OpenAI did not respond within 90 seconds. Try another model or try again.')
        self.assertEqual(messages.message(text, 'tr'), text)
        self.assertEqual(messages.message('Medya bulunamadı: C:/a/b.mp4', 'en'), 'Media not found: C:/a/b.mp4')
        self.assertEqual(messages.message('ffmpeg: unknown encoder', 'en'), 'ffmpeg: unknown encoder')
        self.assertEqual(messages.message('', 'en'), '')

    def test_window_shows_errors_in_the_ui_language(self):
        from main import MainWindow
        window = MainWindow()
        try:
            window.apply_language('en')
            error = ValueError('Dosyada desteklenen görüntü veya ses akışı bulunamadı.')
            self.assertEqual(window.ui_text('Medya eklenemedi: {error}', error=error),
                             'The media could not be added: The file has no supported picture or sound stream.')
            with patch('PySide6.QtWidgets.QMessageBox.critical') as critical:
                window.on_worker_error('Ses okunamadı.')
            self.assertEqual(critical.call_args[0][2], 'Could not read the audio.')
            # User content filled into other fields is never translated.
            self.assertEqual(window.ui_text('“{name}” zaten var. Üzerine yazılsın mı?', name='Ses'),
                             '“Ses” already exists. Replace it?')
            window.apply_language('tr')
            self.assertEqual(window.ui_text('Medya eklenemedi: {error}', error=error),
                             'Medya eklenemedi: Dosyada desteklenen görüntü veya ses akışı bulunamadı.')
        finally:
            window._close_confirmed = True
            window.close()


def _photo(path):
    image = QImage(64, 48, QImage.Format.Format_RGB32)
    image.fill(0x3366AA)
    assert image.save(str(path))
    return path


class ProjectMediaTests(unittest.TestCase):
    def setUp(self):
        try:
            app_support.ffmpeg_path()
        except RuntimeError:
            self.skipTest('FFmpeg not available')
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def window(self, data):
        from main import MainWindow
        stack = patch('akis.app_support.app_data_dir', return_value=self.tmp / data)
        stack.start()
        self.addCleanup(stack.stop)
        window = MainWindow()

        def close():
            window._close_confirmed = True
            window.close()
        self.addCleanup(close)
        return window, stack

    def make_project(self):
        folder = self.tmp / 'Proje'
        folder.mkdir()
        photo = _photo(folder / 'kapak.png')
        window, stack = self.window('pc1')
        self.assertTrue(window._import_media_path(str(photo)))
        window.write_project(str(folder / 'p.akis.json'))
        stack.stop()
        return folder, window

    def test_photo_keeps_its_name_and_moves_with_the_project(self):
        folder, window = self.make_project()
        clip = next(c for t in window.multitrack.tracks for c in t.clips)
        self.assertEqual(Path(clip.style['still_image']).name, 'kapak.png')
        self.assertEqual([Path(p).name for p in window.media_bin.search('')], ['kapak.png'])
        from akis.timeline_service import clip_display_name
        self.assertEqual(clip_display_name(clip), 'kapak.png')
        saved = json.loads((folder / 'p.akis.json').read_text(encoding='utf-8'))
        self.assertIn('kapak.png', saved['relative_media'].values())

        moved = self.tmp / 'Baska' / 'Proje'
        shutil.copytree(folder, moved)
        shutil.rmtree(folder)
        shutil.rmtree(self.tmp / 'pc1')  # the converted copy stayed on the first computer
        other, _ = self.window('pc2')  # another computer: its app data has no converted copy
        with patch('PySide6.QtWidgets.QMessageBox.warning') as warning:
            self.assertTrue(other.open_project_file(str(moved / 'p.akis.json')))
        warning.assert_not_called()
        rebuilt = next(c for t in other.multitrack.tracks for c in t.clips)
        self.assertTrue(Path(rebuilt.source).is_file())
        # samefile: CI's temp folder has a short (RUNNER~1) and a long name for the same place.
        self.assertTrue(os.path.samefile(rebuilt.style['still_image'], moved / 'kapak.png'))
        self.assertTrue(other.has_unsaved_changes())

    def test_moved_media_is_located_and_others_follow_from_its_folder(self):
        folder = self.tmp / 'Kaynak'
        folder.mkdir()
        project = self.tmp / 'p.akis.json'
        first, second = folder / 'a.wav', folder / 'b.wav'
        ffmpeg = app_support.ffmpeg_path()
        import subprocess
        for path in (first, second):
            subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=d=1', str(path)], check=True)
        window, stack = self.window('pc1')
        for path in (first, second):
            self.assertTrue(window._import_media_path(str(path), forced_kind='audio'))
        window.write_project(str(project))
        stack.stop()
        moved = self.tmp / 'Yeni'
        shutil.move(str(folder), str(moved))

        self.assertEqual([Path(p).name for p in project_service.missing_media(project)], ['a.wav', 'b.wav'])
        other, _ = self.window('pc2')
        other.show()
        with patch('PySide6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
             patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(moved / 'a.wav'), '')) as chooser, \
             patch('PySide6.QtWidgets.QMessageBox.warning') as warning:
            self.assertTrue(other.open_project_file(str(project)))
        self.assertEqual(chooser.call_count, 1)  # b.wav was found beside a.wav
        warning.assert_not_called()
        sources = sorted(Path(c.source).resolve() for t in other.multitrack.tracks for c in t.clips if c.source)
        self.assertEqual(sources, [(moved / 'a.wav').resolve(), (moved / 'b.wav').resolve()])
        self.assertTrue(other.has_unsaved_changes())

    def test_declining_to_locate_opens_with_the_missing_list(self):
        folder, _ = self.make_project()
        (folder / 'kapak.png').unlink()
        shutil.rmtree(self.tmp / 'pc1')
        other, _ = self.window('pc2')
        other.show()
        with patch('PySide6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.No), \
             patch('PySide6.QtWidgets.QMessageBox.warning') as warning:
            self.assertTrue(other.open_project_file(str(folder / 'p.akis.json')))
        self.assertIn('kapak', warning.call_args[0][2])


class UndoSelectionTests(unittest.TestCase):
    def test_undo_and_redo_keep_the_selected_clip(self):
        from main import MainWindow
        from akis.timeline_model import Clip
        window = MainWindow()
        try:
            track = next(i for i, t in enumerate(window.multitrack.tracks) if t.kind == 'text')
            with window.history_step():
                window.multitrack.tracks[track].clips.append(Clip('', 0, 30, text='Merhaba'))
            clip = window.multitrack.tracks[track].clips[0]
            window.multitrack_view.selected = (track, clip.id)
            with window.history_step():
                window.multitrack.tracks[track].clips[0].text = 'Selam'
            window.undo()
            self.assertEqual(window.multitrack_view.selected, (track, clip.id))
            window.redo()
            self.assertEqual(window.multitrack_view.selected, (track, clip.id))
        finally:
            window._close_confirmed = True
            window.close()


class TouchingClipHandleTests(unittest.TestCase):
    def test_right_handle_next_to_a_touching_clip_trims_the_left_clip(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from akis.multitrack_widget import MultitrackWidget
        from akis.timeline_model import Clip, Timeline, Track
        timeline = Timeline.from_legacy({})
        timeline.tracks = [Track('video', 'Video')]
        left, right = Clip('a.mp4', 0, 240, source_length=240), Clip('b.mp4', 240, 150, source_length=150)
        timeline.tracks[0].clips = [left, right]
        view = MultitrackWidget(timeline)
        view.resize(1400, 200)
        view.zoom = 4.0
        view.show()
        try:
            y = 30 + 21
            x = round(view.x_for(240)) - 2   # inside the left clip as drawn, on its right handle
            QTest.mousePress(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y))
            self.assertEqual((view.selected, view.drag_mode), ((0, left.id), 'trim'))
            QTest.mouseMove(view, QPoint(x - 160, y))
            QTest.mouseRelease(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x - 160, y))
            self.assertEqual(left.length, 200)
            self.assertEqual((right.start, right.length), (240, 150))
        finally:
            view.close()


if __name__ == '__main__':
    unittest.main()
