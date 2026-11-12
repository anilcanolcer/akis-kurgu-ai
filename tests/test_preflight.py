"""Checks before an export: missing files, holes in the picture, a tail without picture."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from akis import preflight
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
YES = lambda path: True


def timeline(*tracks):
    return Timeline(fps_num=30, tracks=list(tracks))


class CheckTests(unittest.TestCase):
    def test_a_plain_cut_has_nothing_to_report(self):
        cut = timeline(Track('video', 'Video', [Clip('a.mp4', 0, 90), Clip('b.mp4', 90, 60)]),
                       Track('text', 'Yazı', [Clip('', 30, 60, text='Merhaba')]))
        self.assertEqual(preflight.check(cut, exists=YES), [])
        self.assertEqual(preflight.check(timeline(), exists=YES), [])

    def test_missing_files_are_named_once_each(self):
        cut = timeline(Track('video', 'Video', [Clip('C:/v/a.mp4', 0, 30), Clip('C:/v/a.mp4', 30, 30), Clip('C:/v/b.mp4', 60, 30)]))
        found = preflight.check(cut, exists=lambda path: path.endswith('b.mp4'))
        self.assertEqual(len(found), 1)
        self.assertIn('1 kaynak dosya bulunamıyor (a.mp4)', found[0])

    def test_holes_in_the_picture_are_counted_and_located(self):
        cut = timeline(Track('video', 'Video', [Clip('a.mp4', 30, 60), Clip('a.mp4', 150, 30)]))
        found = preflight.check(cut, exists=YES)
        self.assertEqual(len(found), 1)
        self.assertIn('2 yerde görüntü yok (toplam 3,0 sn, 0:00,0, 0:03,0)', found[0])

    def test_a_second_video_track_or_an_overlay_covers_a_hole(self):
        cut = timeline(Track('video', 'Video', [Clip('a.mp4', 0, 60), Clip('a.mp4', 90, 30)]),
                       Track('overlay', 'Üst', [Clip('b.mp4', 50, 50)]))
        self.assertEqual(preflight.check(cut, exists=YES), [])
        cut.tracks[1].muted = True
        self.assertEqual(len(preflight.check(cut, exists=YES)), 1)

    def test_one_frame_holes_are_not_worth_a_warning(self):
        cut = timeline(Track('video', 'Video', [Clip('a.mp4', 0, 60), Clip('a.mp4', 62, 30)]))
        self.assertEqual(preflight.check(cut, exists=YES), [])

    def test_text_or_music_running_past_the_picture(self):
        cut = timeline(Track('video', 'Video', [Clip('a.mp4', 0, 60)]),
                       Track('audio', 'Müzik', [Clip('m.mp3', 0, 150)]))
        found = preflight.check(cut, exists=YES)
        self.assertEqual(len(found), 1)
        self.assertIn('3,0 sn daha yazı ya da ses sürüyor', found[0])

    def test_question_lists_every_finding(self):
        text = preflight.question(['Bir.', 'İki.'])
        self.assertIn('• Bir.\n• İki.', text)
        self.assertTrue(text.endswith('Yine de dışa aktarılsın mı?'))


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

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def export(self, answer=QMessageBox.StandardButton.No):
        w = self.window
        started = []
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(self.root / 'out.mp4'), '')) as chooser, \
             patch.object(w, 'export_canvas_size', return_value=(1080, 1920)), \
             patch('akis.export_progress.space_problem', return_value=''), \
             patch('main.QMessageBox.question', return_value=answer) as question, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.export_video()
        return started, question, chooser

    def test_clean_timeline_exports_without_a_question(self):
        started, question, _ = self.export()
        self.assertEqual(len(started), 1)
        question.assert_not_called()

    def test_finding_is_shown_before_the_file_dialog_and_no_stops_the_export(self):
        w = self.window
        track = next(t for t in w.multitrack.tracks if t.kind == 'video')
        track.clips[0].start = 60                                    # two seconds of nothing at the start
        started, question, chooser = self.export()
        self.assertEqual(started, [])
        chooser.assert_not_called()
        self.assertIn('görüntü yok', question.call_args.args[2])
        self.assertEqual(w.status_label.text(), 'Dışa aktarma başlatılmadı.')
        started, _, _ = self.export(QMessageBox.StandardButton.Yes)
        self.assertEqual(len(started), 1)


if __name__ == '__main__':
    unittest.main()
