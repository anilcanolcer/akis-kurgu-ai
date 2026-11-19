"""0.6.7: play at once while the smooth copy renders, retakes inside one long segment, status in English,
short export errors and no duplicate translation keys."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import retakes, timeline_render

app = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


def word(start, end, text):
    return {'start': start, 'end': end, 'text': text}


def spoken(*sentences, pause=1.8):
    """One Whisper segment holding every sentence, as the small models return unpunctuated speech."""
    words, at = [], 0.0
    for sentence in sentences:
        for item in sentence.split():
            words.append(word(at, at + 0.3, item))
            at += 0.35
        at += pause
    return [{'start': 0.0, 'end': words[-1]['end'], 'text': ' '.join(sentences), 'words': words}]


class RetakeSentenceTests(unittest.TestCase):
    def test_a_retake_inside_one_long_segment_is_found(self):
        segments = spoken('Merhaba bugün size kurgu yapmayı anlatacağım',
                          'ilk olarak videoyu programa ekliyoruz',
                          'ilk olarak videoyu programa ekliyoruz',
                          'son olarak videoyu dışa aktarıyoruz')
        self.assertEqual(len(retakes.sentences(segments)), 4)
        cuts = retakes.find(segments)
        self.assertEqual(len(cuts), 1)
        self.assertEqual(cuts[0][2], 'ilk olarak videoyu programa ekliyoruz')
        first, second = retakes.sentences(segments)[1:3]
        self.assertEqual((cuts[0][0], cuts[0][1]), (first['start'], second['start']))

    def test_sentence_punctuation_splits_without_a_pause(self):
        words = [word(0, .3, 'Bir.'), word(.35, .6, 'İki'), word(.65, .9, 'üç.')]
        parts = retakes.sentences([{'start': 0, 'end': .9, 'text': 'Bir. İki üç.', 'words': words}])
        self.assertEqual([p['text'] for p in parts], ['Bir.', 'İki üç.'])

    def test_segments_without_word_timings_are_kept(self):
        segments = [{'start': 0, 'end': 2, 'text': 'Aynı cümle burada geçiyor'},
                    {'start': 3, 'end': 5, 'text': 'Aynı cümle burada geçiyor'}]
        self.assertEqual(retakes.sentences(segments), segments)
        self.assertEqual(len(retakes.find(segments)), 1)


class ExportErrorTests(unittest.TestCase):
    def test_ffmpeg_stream_listing_is_left_out_and_the_cause_kept(self):
        log = ('encoder         : Lavf63.1.102\n  Duration: 00:00:08.00, start: 0.000000\n'
               '  Stream #1:0: Video: h264 (High)\n    Metadata:\n      handler_name    : VideoHandler\n'
               '[out#0/mp4 @ 0000] Error opening output C:/x.part.mp4: Permission denied\n'
               'Error opening output files: Permission denied')
        message = timeline_render.export_failure(log, 'C:/x.mp4')
        self.assertNotIn('Stream #1:0', message)
        self.assertNotIn('handler_name', message)
        self.assertIn('Permission denied', message)
        self.assertIn('Denetimli klasör erişimini', message)   # the write-permission hint still follows

    def test_short_messages_stay_whole(self):
        self.assertEqual(timeline_render.error_lines('Medya bulunamadı: a.mp4'), 'Medya bulunamadı: a.mp4')


class StatusLanguageTests(unittest.TestCase):
    def test_worker_progress_follows_the_english_interface(self):
        from main import MainWindow
        window = MainWindow()
        try:
            window.apply_language('en')
            window.set_status('Video çözümleniyor (1/2): ses, sahne ve kareler…')
            self.assertEqual(window.status_label.text(), 'Analysing video (1/2): sound, scenes and frames…')
            window.set_status('AI kurgusu uygulandı. Beğenmezseniz geri alabilir veya yeni bir istek yazabilirsiniz.')
            self.assertTrue(window.status_label.text().startswith('The AI edit was applied.'))
            window.set_status('kendi_dosyam.mp4')                   # anything unknown is shown as it is
            self.assertEqual(window.status_label.text(), 'kendi_dosyam.mp4')
            window.apply_language('tr')
            window.set_status('AI kurgu kararlarını veriyor…')
            self.assertEqual(window.status_label.text(), 'AI kurgu kararlarını veriyor…')
        finally:
            window._close_confirmed = True
            window.close()


class PlayWhileRenderingTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch('akis.app_support.app_data_dir', return_value=Path(self.tmp.name)).start()
        patch('akis.media_service.MediaService.duration', return_value=20.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.addCleanup(self.close)
        video = Path(self.tmp.name) / 'uzun.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))
        w = self.window
        patch.object(w.preview, 'request').start()
        patch.object(w, 'prepare_proxy').start()
        patch.object(w, 'sync_timeline_audio').start()
        patch.object(type(w.proxy), 'available', new=True, create=True).start()
        self.ready = patch.object(w.proxy, 'is_ready', return_value=False).start()
        self.play = patch.object(w.proxy, 'play').start()

    def close(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_play_starts_frame_by_frame_and_hands_over_where_it_got_to(self):
        w = self.window
        w.toggle_play()
        self.assertTrue(w.play_timer.isActive())        # moving at once, not waiting for the copy
        self.assertTrue(w._play_when_ready)
        w.timeline_frame = 123
        self.ready.return_value = True
        w.on_proxy_ready()
        self.assertFalse(w.play_timer.isActive())
        self.play.assert_called_once()
        self.assertEqual(self.play.call_args.args[0], 123)

    def test_pause_while_waiting_stops_both(self):
        w = self.window
        w.toggle_play()
        w.toggle_play()
        self.assertFalse(w.play_timer.isActive())
        self.assertFalse(w._play_when_ready)
        self.ready.return_value = True
        w.on_proxy_ready()                                # a copy finished after the pause must not start
        self.play.assert_not_called()

    def test_reaching_the_end_first_does_not_start_the_copy_later(self):
        w = self.window
        w.toggle_play()
        with patch.object(w.playback_clock, 'position', return_value=10 ** 6):
            w.advance_timeline()
        self.assertFalse(w.play_timer.isActive())
        self.assertFalse(w._play_when_ready)
        self.ready.return_value = True
        w.on_proxy_ready()
        self.play.assert_not_called()


class TranslationTableTests(unittest.TestCase):
    def test_no_turkish_key_is_written_twice_in_one_table(self):
        tree = ast.parse((ROOT / 'akis' / 'i18n.py').read_text(encoding='utf-8'))
        repeated = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                repeated += sorted({k for k in keys if keys.count(k) > 1})
        self.assertEqual(repeated, [])


if __name__ == '__main__':
    unittest.main()
