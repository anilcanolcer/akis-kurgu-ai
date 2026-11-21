"""Regressions from the 0.6.19 Windows audit (real-UI flows on the editor and the packaged exe).

1. Exporting over a video another program holds open (a player showing the last export) failed with
   "[WinError 5] Erişim engellendi" on the hidden `.part-…` file, plus advice about antivirus and folder
   permissions. Now a short hold is waited out and a longer one is named for what it is.
2. Opening a project saved by a newer version said "Unsupported project version" in English, and a cut-off
   or empty file showed Python's parser text ("Expecting value: line 1 column 47 (char 46)").
"""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from akis import i18n, messages, project_service  # noqa: E402
from akis.timeline_model import Clip, Timeline, Track  # noqa: E402
from akis.timeline_render import TimelineRenderer, export_failure  # noqa: E402

# The texts are written out here (not imported) so these tests also run, and fail, against the old code.
OUTPUT_IN_USE = ('Hedef dosya başka bir programda açık (örneğin bir video oynatıcıda). '
                 'O programı kapatıp yeniden deneyin.')
NOT_A_PROJECT = 'Bu dosya bir Akış Kurgu projesi değil.'
NEWER_PROJECT = 'Bu proje programın daha yeni bir sürümüyle kaydedilmiş. Açmak için programı güncelleyin.'
DAMAGED_PROJECT = 'Proje dosyası bozuk ya da yarım kalmış (satır {line}, sütun {column}).'


class FakeMedia:
    executable = 'ffmpeg'


def finished_render(self, timeline, partial, on_progress=None):
    Path(partial).write_bytes(b'new export')


@unittest.skipUnless(os.name == 'nt', 'Windows file locking')
class OutputHeldOpenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.output = self.folder / 'son video ğüş.mp4'
        self.output.write_bytes(b'previous export')
        self.timeline = Timeline()
        self.timeline.tracks = [Track('video', 'V1', [Clip(str(self.folder / 'kaynak.mp4'), 0, 30)])]
        self.renderer = TimelineRenderer(FakeMedia(), (64, 36))

    def test_a_held_output_is_named_and_the_old_file_and_no_part_file_remain(self):
        with open(self.output, 'rb'), patch.object(TimelineRenderer, '_render', finished_render):
            with self.assertRaises(PermissionError) as caught:
                self.renderer.export(self.timeline, self.output)
        self.assertEqual(str(caught.exception), OUTPUT_IN_USE)
        self.assertEqual(self.output.read_bytes(), b'previous export')
        self.assertEqual([p.name for p in self.folder.iterdir() if '.part' in p.name], [])
        shown = export_failure(caught.exception, self.output)
        self.assertIn(OUTPUT_IN_USE, shown)
        self.assertNotIn('.part', shown)
        self.assertNotIn('antivirüs', shown)          # the permission advice does not fit a file that is in use
        english = export_failure(caught.exception, self.output, say=lambda text: i18n.translate(text, 'en'))
        self.assertIn('open in another program', english)

    def test_a_short_hold_is_waited_out(self):
        handle = open(self.output, 'rb')
        threading.Timer(0.25, handle.close).start()
        with patch.object(TimelineRenderer, '_render', finished_render):
            self.renderer.export(self.timeline, self.output)
        self.assertEqual(self.output.read_bytes(), b'new export')

    def test_a_fast_export_reports_the_same(self):
        from akis import fast_export

        def copy(arguments, **kw):
            Path(arguments[-1]).write_bytes(b'new export')
            return type('Done', (), {'returncode': 0, 'stderr': ''})()
        media = type('Media', (), {'run': staticmethod(copy)})()
        source = self.folder / 'kaynak.mp4'
        source.write_bytes(b'x')
        with open(self.output, 'rb'), self.assertRaises(PermissionError) as caught:
            fast_export.export([(str(source), 0.0, 1.0)], str(self.output), media)
        self.assertEqual(str(caught.exception), OUTPUT_IN_USE)
        self.assertEqual(self.output.read_bytes(), b'previous export')


class ProjectOpenMessageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def load(self, body):
        path = self.folder / 'proje.akis.json'
        path.write_bytes(body if isinstance(body, bytes) else body.encode('utf-8'))
        with self.assertRaises(ValueError) as caught:
            project_service.load(path)
        return str(caught.exception)

    def test_a_newer_project_says_to_update_in_turkish_and_english(self):
        text = self.load(json.dumps({'format': 'akis-kurgu-project', 'version': project_service.CURRENT_VERSION + 1}))
        self.assertEqual(text, NEWER_PROJECT)
        self.assertIn('newer version', messages.message(text, 'en'))

    def test_cut_off_and_empty_files_are_called_damaged_with_the_place(self):
        for body, line, column in (('{"format": "akis-kurgu-project", "timeline": [', 1, 47), ('', 1, 1),
                                   ('{\n  "format": "akis-kurgu-project",\n  "version": 2,\n', 4, 1)):
            with self.subTest(body=body[:20]):
                text = self.load(body)
                self.assertEqual(text, DAMAGED_PROJECT.format(line=line, column=column))
                self.assertEqual(messages.message(text, 'en'),
                                 f'The project file is damaged or incomplete (line {line}, column {column}).')

    def test_a_damaged_timeline_is_named_without_model_or_python_words(self):
        good = project_service.make_document({}, Timeline(tracks=[Track('video', 'V1', [Clip('a.mp4', 0, 30)])]), {}, '')
        for damage in ({'kind': 'film'}, {'clips': [None]}, {'clips': [dict(good['timeline']['tracks'][0]['clips'][0], length=0)]}):
            with self.subTest(damage=damage):
                doc = json.loads(json.dumps(good))
                doc['timeline']['tracks'][0].update(damage)
                text = self.load(json.dumps(doc))
                self.assertEqual(text, 'Proje dosyasındaki kurgu okunamadı; dosya bozulmuş ya da elle değiştirilmiş olabilir.')
                self.assertIn('could not be read', messages.message(text, 'en'))

    def test_other_files_are_not_projects(self):
        for body in ('[]', '"metin"', json.dumps({'format': 'akis-story'}), b'\xff\xfe\x00binary',
                     json.dumps({'format': 'akis-kurgu-project', 'version': True})):
            with self.subTest(body=str(body)[:20]):
                self.assertEqual(self.load(body), NOT_A_PROJECT)

    def test_the_window_shows_the_readable_message_and_keeps_the_open_project(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication([])
        from main import MainWindow
        window = MainWindow()
        self.addCleanup(window.close)
        path = self.folder / 'yeni.akis.json'
        path.write_text(json.dumps({'format': 'akis-kurgu-project', 'version': 99}), encoding='utf-8')
        with patch.object(QMessageBox, 'critical') as critical:
            self.assertFalse(window.open_project_file(str(path)))
        shown = critical.call_args[0][2]
        self.assertIn(NEWER_PROJECT, shown)
        self.assertNotIn('Unsupported', shown)


if __name__ == '__main__':
    unittest.main()
