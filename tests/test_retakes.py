"""Retakes: which repeats are found, what is cut, and the button that cuts them."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import i18n, retakes
from akis.retakes import find

app = QApplication.instance() or QApplication([])


def said(*lines):
    """Timed segments from (start, end, text) triples."""
    return [{'start': start, 'end': end, 'text': text} for start, end, text in lines]


class FindTests(unittest.TestCase):
    def test_sentence_said_again_keeps_the_last_try(self):
        cuts = find(said((0, 3, 'Bugün size yeni bir özellik göstereceğim.'),
                         (3.5, 6, 'Bugün size yeni bir özellik göstereceğim.'),
                         (6.5, 9, 'İlk olarak menüyü açıyoruz.')))
        self.assertEqual(cuts, [(0, 3.5, 'Bugün size yeni bir özellik göstereceğim.', 'Bugün size yeni bir özellik göstereceğim.')])

    def test_slightly_different_wording_still_counts(self):
        cuts = find(said((0, 3, 'Bugün sizlere yeni bir özellik göstereceğim'),
                         (4, 7, 'Bugün size yeni bir özelliği göstereceğim')))
        self.assertEqual(len(cuts), 1)

    def test_false_start_is_cut(self):
        cuts = find(said((0, 1.5, 'Bugün size şunu'), (2, 6, 'Bugün size şunu anlatmak istiyorum, çok önemli.')))
        self.assertEqual(cuts, [(0, 2, 'Bugün size şunu', 'Bugün size şunu anlatmak istiyorum, çok önemli.')])

    def test_three_tries_leave_only_the_third(self):
        cuts = find(said((0, 2, 'Merhaba arkadaşlar hoş geldiniz'), (2.5, 4, 'Merhaba arkadaşlar hoş geldiniz'),
                         (5, 7, 'Merhaba arkadaşlar, hoş geldiniz!')))
        self.assertEqual([(start, end) for start, end, _, _ in cuts], [(0, 5)])

    def test_a_stumble_between_two_tries_goes_with_the_first(self):
        cuts = find(said((0, 3, 'Şimdi ayarlar menüsüne geçiyoruz'), (3.2, 4, 'ııı pardon'),
                         (4.5, 7, 'Şimdi ayarlar menüsüne geçiyoruz')))
        self.assertEqual([(start, end) for start, end, _, _ in cuts], [(0, 4.5)])

    def test_different_sentences_and_short_words_are_left_alone(self):
        self.assertEqual(find(said((0, 2, 'Evet tamam'), (2, 3, 'Evet tamam'), (3, 6, 'Videonun ilk bölümü bitti.'),
                                   (6, 9, 'Şimdi ikinci bölüme geçelim.'))), [])

    def test_repeats_far_apart_are_not_retakes(self):
        self.assertEqual(find(said((0, 3, 'Abone olmayı unutmayın lütfen'), (60, 63, 'Abone olmayı unutmayın lütfen'))), [])
        far = said((0, 2, 'Bunu birazdan anlatacağım'), (2, 3, 'bir'), (3, 4, 'iki'), (4, 5, 'üç'), (5, 6, 'dört'),
                   (6, 8, 'Bunu birazdan anlatacağım'))
        self.assertEqual(find(far), [])

    def test_unsorted_or_empty_input(self):
        self.assertEqual(find([]), [])
        cuts = find(said((4, 7, 'Bugün size yeni bir özellik'), (0, 3, 'Bugün size yeni bir özellik'), (8, 9, '  ')))
        self.assertEqual([(start, end) for start, end, _, _ in cuts], [(0, 4)])

    def test_question_lists_what_goes_and_what_stays_in_both_languages(self):
        cuts = [(0, 1, 'eski deneme', 'son deneme')] * 8
        text = retakes.summary(cuts)
        self.assertIn('8 tekrar çekim bulundu', text)
        self.assertIn('✕ eski deneme\n✓ son deneme', text)
        self.assertIn('… ve 2 tane daha.', text)
        english = retakes.summary(cuts, lambda t: i18n.translate(t, 'en'))
        self.assertIn('8 retakes found', english)
        self.assertIn('Cut them?', english)


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=10.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        self.video = self.root / 'a.mp4'
        self.video.touch()
        self.assertTrue(self.window.load_video(str(self.video)))

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def length(self):
        return sum(c.length for t in self.window.multitrack.tracks if t.kind == 'video' for c in t.clips)

    def test_without_a_transcript_it_says_what_to_do_first(self):
        with patch('main.QMessageBox.information') as told:
            self.window.remove_retakes()
        self.assertIn('yerel konuşma metnini', told.call_args.args[2])

    def test_cut_after_confirming_is_one_undo_step(self):
        w = self.window
        w.caption_source = str(self.video)
        w.caption_segments = said((0, 3, 'Bugün size yeni bir özellik göstereceğim'),
                                  (3, 6, 'Bugün size yeni bir özellik göstereceğim'), (6, 9, 'Başlayalım o zaman.'))
        before = self.length()
        fps = w.multitrack.fps_num / w.multitrack.fps_den
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes) as asked:
            w.remove_retakes()
        self.assertIn('✕ Bugün size', asked.call_args.args[2])
        self.assertEqual(self.length(), before - round(3 * fps))
        self.assertIn('1 tekrar çekim kesildi', w.status_label.text())
        self.assertTrue(w.undo())
        self.assertEqual(self.length(), before)
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            w.remove_retakes()
        self.assertEqual(self.length(), before)
        self.assertFalse(w.undo())

    def test_nothing_found_says_so(self):
        w = self.window
        w.caption_source = str(self.video)
        w.caption_segments = said((0, 3, 'Tek bir cümle var burada.'))
        with patch('main.QMessageBox.information') as told:
            w.remove_retakes()
        self.assertEqual(told.call_args.args[2], 'Tekrar çekim bulunamadı.')


if __name__ == '__main__':
    unittest.main()
