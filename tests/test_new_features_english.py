"""The features added after 0.5.3 speak English when the UI does: templates are translated and still fill in."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import clip_fit, export_progress, i18n, preflight, shortcuts, silence_cut
from akis.silence_dialog import SilenceDialog
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
EN = lambda text: i18n.translate(text, 'en')
Usage = namedtuple('Usage', 'total used free')


class TemplateTests(unittest.TestCase):
    def test_every_new_text_has_a_translation(self):
        texts = [silence_cut.NOTHING, silence_cut.SUMMARY, shortcuts.TITLE, shortcuts.NOTE]
        texts += [what for _, _, _, what, _ in shortcuts.SHORTCUTS] + [what for _, what in shortcuts.BUILT_IN]
        texts += [label for label, _, _ in clip_fit.CHOICES]
        for text in texts:
            self.assertNotEqual(EN(text), text, text)

    def test_silence_summary(self):
        before = [{'source': 0, 'start': 0, 'end': 100}]
        after, cuts = silence_cut.keep_segments(before, {0: [(10, 40)]}, margin=0)
        self.assertEqual(silence_cut.summary(before, after, cuts, EN), '1 silent parts will be cut · 1:40 → 1:10 (30.0 s shorter)')
        self.assertEqual(silence_cut.summary(before, before, [], EN), 'No silence to cut with these settings.')

    def test_export_status_and_space_warning(self):
        self.assertEqual(export_progress.text(7, None, EN), 'Exporting… 7%')
        self.assertEqual(export_progress.text(42, 70, EN), 'Exporting… 42% · about 1:10 left')
        self.assertEqual(export_progress.text(99, 2, EN), 'Exporting… 99% · almost done')
        warning = export_progress.space_problem('C:/x/out.mp4', 1000 * 1024 * 1024,
                                                lambda folder: Usage(0, 0, 300 * 1024 * 1024), EN)
        self.assertIn('about 300 MB free', warning)
        self.assertIn('up to 1.000 MB', warning)

    def test_pre_export_findings(self):
        cut = Timeline(fps_num=30, tracks=[Track('video', 'Video', [Clip('C:/v/gone.mp4', 30, 60)]),
                                           Track('audio', 'Müzik', [Clip('C:/v/gone.mp4', 0, 150)])])
        found = preflight.check(cut, exists=lambda path: False, say=EN)
        self.assertEqual(len(found), 3)
        self.assertIn('1 source files cannot be found (gone.mp4)', found[0])
        self.assertIn('no picture in 1 places (1,0 s in total', found[1])
        self.assertIn('runs on for 2,0 s after the picture ends', found[2])
        question = preflight.question(found, EN)
        self.assertTrue(question.startswith('Before you export:'))
        self.assertTrue(question.endswith('Export anyway?'))

    def test_silence_dialog(self):
        dialog = SilenceDialog(executable='ffmpeg', sources=[{'path': 'a.mp4', 'duration': 6.0}],
                               segments=[{'source': 0, 'start': 0, 'end': 6}], language='en',
                               measure=lambda executable, path: [])
        self.addCleanup(dialog.deleteLater)
        dialog.worker.wait(5000)
        app.processEvents()
        self.assertEqual(dialog.windowTitle(), 'Remove silences')
        self.assertEqual(dialog.apply_button.text(), 'Cut the silences')
        self.assertEqual(dialog.threshold_label.text(), 'Silence threshold: -35 dB')
        self.assertEqual(dialog.result.text(), 'No sound that can be analysed was found in the video.')


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))
        self.window.apply_language('en')

    def close_window(self):
        self.window.apply_language('tr')
        self.window._close_confirmed = True
        self.window.close()

    def test_new_controls_are_shown_in_english(self):
        w = self.window
        self.assertEqual(w.loudness.text(), 'Normalize loudness to -14 LUFS')
        self.assertEqual(w.music_duck.text(), 'Lower the music while someone speaks')
        self.assertEqual(w.speech_vocabulary.placeholderText(), 'Names and terms, comma-separated (e.g. Anılcan, Akış Kurgu)')
        self.assertEqual(w.speech_language.itemText(0), 'Türkçe')          # language names stay in their own language

    def test_status_messages_fill_in_after_translation(self):
        w = self.window
        w._export_estimator = export_progress.Estimator(now=lambda: 0.0)
        w.on_export_progress(1)
        self.assertEqual(w.status_label.text(), 'Exporting… 1%')
        w.set_clip_fit()
        self.assertEqual(w.status_label.text(), 'Select a video clip first.')
        index = next(i for i, t in enumerate(w.multitrack.tracks) if t.kind == 'video')
        clip = w.multitrack.tracks[index].clips[0]
        w.multitrack_view.selected, w.multitrack_view.selected_track = (index, clip.id), index
        with patch('main.QInputDialog.getItem', return_value=('Fill · keep the middle', True)) as dialog:
            w.set_clip_fit()
        self.assertEqual(dialog.call_args.args[1:4], ('Framing', 'How should the clip sit on the canvas?',
                                                      [EN(label) for label, _, _ in clip_fit.CHOICES]))
        self.assertEqual(clip.style, {'fit': 'fill', 'focus': 0.5})
        self.assertEqual(w.status_label.text(), 'Framing: Fill · keep the middle')


if __name__ == '__main__':
    unittest.main()
