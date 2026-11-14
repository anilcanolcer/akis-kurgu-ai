"""Filler words: which words count, where the cut goes, the question, the window's button."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import fillers, i18n
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


def w(text, start, end):
    return {'text': text, 'start': start, 'end': end}


# What Whisper wrote for a sample read with hesitations (timings from a real run).
SPOKEN = [w('Merhaba', 0.0, 0.52), w('arkadaşlar.', 0.52, 1.28), w('ıı,', 2.0, 2.2), w('bugün', 2.42, 2.6),
          w('size,', 2.6, 2.88), w('eee,', 3.34, 3.68), w('yeni', 3.86, 3.98), w('bir', 3.98, 4.12), w('şey', 4.12, 4.3),
          w('göstereceğim.', 4.3, 4.96), w('Şey,', 5.74, 5.92), w('önce', 6.06, 6.18), w('bilgisayarı', 6.18, 6.82),
          w('açıyoruz.', 6.82, 7.24), w('TMMM.', 8.04, 8.72), w('Sonra', 9.22, 9.64), w('İşte', 12.94, 13.16),
          w('şu', 13.16, 13.4), w('düğmeye', 13.4, 13.7)]


class FindTests(unittest.TestCase):
    def test_hesitations_and_pause_words_are_found_meaningful_words_kept(self):
        found = fillers.find(SPOKEN)
        self.assertEqual([text for _, _, text in found], ['ıı,', 'eee,', 'Şey,', 'TMMM.'])
        for start, end, _ in found:                       # never into a neighbouring word
            for word in SPOKEN:
                if word['text'] not in ('ıı,', 'eee,', 'Şey,', 'TMMM.'):
                    self.assertTrue(end <= word['start'] + 1e-9 or start >= word['end'] - 1e-9, (start, end, word))

    def test_spoken_fillers_need_a_pause_after_them(self):
        self.assertEqual(fillers.find([w('İşte', 1.0, 1.2), w('şu', 1.2, 1.4)]), [])
        self.assertEqual(fillers.find([w('yani', 1.0, 1.3), w('gel', 1.8, 2.0)])[0][2], 'yani')
        self.assertEqual(fillers.find([w('o', 0.5, 0.7), w('şey', 0.7, 1.0), w('güzel', 1.6, 2.0)]), [])
        self.assertEqual(fillers.find([w('işte', 1.0, 1.3)]), [])          # the last word: nothing after it

    def test_neighbouring_fillers_merge_and_tiny_ones_are_skipped(self):
        found = fillers.find([w('a', 0, 0.5), w('eee', 1.0, 1.4), w('ııı', 1.42, 1.8), w('b', 2.4, 2.8)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][2], 'eee ııı')
        self.assertEqual(fillers.find([w('a', 0, 0.5), w('ı', 0.52, 0.56), w('b', 0.58, 1.0)]), [])
        self.assertEqual(fillers.find([{'text': 'x'}, 'y', w('', 1, 2)]), [])

    def test_summary_in_both_languages(self):
        cuts = fillers.find(SPOKEN)
        text = fillers.summary(cuts)
        self.assertIn('4 dolgu sözcüğü bulundu', text)
        self.assertIn('ııı / eee ×3', text)
        self.assertIn('şey ×1', text)
        english = fillers.summary(cuts, lambda t: i18n.translate(t, 'en'))
        self.assertIn('4 filler words found', english)


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=20.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        self.video = self.root / 'konusma.mp4'
        self.video.touch()
        self.assertTrue(self.window.load_video(str(self.video)))

    def close_window(self):
        # A worker that has finished may not have told the window yet; a window that still
        # counts it refuses to close and keeps its recovery lock (seen on a slow CI runner).
        QApplication.processEvents()
        for _ in range(500):
            if not self.window._workers:
                break
            QApplication.processEvents()
            __import__("time").sleep(0.01)
        self.window._close_confirmed = True
        self.window.close()

    def run_fillers(self, words, answer=QMessageBox.StandardButton.Yes):
        w = self.window
        started = []
        with patch('akis.ai_service.local_transcribe', return_value=[{'start': 0, 'end': 20, 'text': 'x', 'words': words}]) as heard, \
             patch('PySide6.QtWidgets.QMessageBox.question', return_value=answer) as asked, \
             patch('PySide6.QtWidgets.QMessageBox.information') as told, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.remove_fillers()
            worker = started[0]
            worker.start()
            self.assertTrue(worker.wait(20000))
            app.processEvents()
        return heard, asked, told

    def test_fillers_are_cut_in_one_undo_step(self):
        w = self.window
        before = sum(c.length for c in w.multitrack.tracks[0].clips)
        heard, asked, _ = self.run_fillers(SPOKEN)
        self.assertIn(fillers.PROMPT, heard.call_args.kwargs['vocabulary'])
        self.assertTrue(heard.call_args.kwargs['timed'])
        self.assertIn('4 dolgu sözcüğü bulundu', asked.call_args.args[2])
        after = sum(c.length for c in w.multitrack.tracks[0].clips)
        fps = w.multitrack.fps_num / w.multitrack.fps_den
        self.assertAlmostEqual((before - after) / fps, sum(b - a for a, b, _ in fillers.find(SPOKEN)), delta=0.2)
        w.undo()
        self.assertEqual(sum(c.length for c in w.multitrack.tracks[0].clips), before)

    def test_declining_or_finding_nothing_changes_nothing(self):
        w = self.window
        before = [(c.start, c.length) for c in w.multitrack.tracks[0].clips]
        self.run_fillers(SPOKEN, QMessageBox.StandardButton.No)
        self.assertEqual([(c.start, c.length) for c in w.multitrack.tracks[0].clips], before)
        _, asked, told = self.run_fillers([w_ for w_ in SPOKEN if w_['text'] in ('Merhaba', 'arkadaşlar.')])
        asked.assert_not_called()
        self.assertIn('Dolgu sözcüğü bulunamadı', told.call_args.args[2])

    def test_a_larger_local_model_is_preferred_and_missing_ones_skipped(self):
        self.assertEqual(fillers.models_to_try('tiny'), ['small', 'base', 'tiny'])
        self.assertEqual(fillers.models_to_try('small'), ['small'])
        self.assertEqual(fillers.models_to_try('base'), ['small', 'base'])
        self.assertEqual(fillers.models_to_try('medium'), ['medium'])
        w = self.window
        w.local_model.setCurrentText('tiny')
        tried = []

        def listen(source, name, **kwargs):
            tried.append((name, kwargs['download']))
            if name != 'tiny':
                raise RuntimeError('model yok')
            return [{'start': 0, 'end': 20, 'text': 'x', 'words': SPOKEN}]
        started = []
        with patch('akis.ai_service.local_transcribe', side_effect=listen), \
                patch('PySide6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as asked, \
                patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.remove_fillers()
            started[0].start()
            self.assertTrue(started[0].wait(20000))
            app.processEvents()
        self.assertEqual([name for name, _ in tried], ['small', 'base', 'tiny'])
        self.assertTrue(all(not download for name, download in tried if name != 'tiny'))   # never fetched unasked
        self.assertIn('4 dolgu sözcüğü bulundu', asked.call_args.args[2])

    def test_button_is_in_the_edit_tab_and_translated(self):
        from PySide6.QtWidgets import QPushButton
        w = self.window
        w.apply_language('en')
        labels = [b.text() for b in w.findChildren(QPushButton)]
        self.assertIn('Cut filler words (um, uh, like)', labels)


if __name__ == '__main__':
    unittest.main()
