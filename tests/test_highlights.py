"""Highlights: scoring stretches from the sound, picking the best, the reasons, the dialog and the button."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from akis import highlights, i18n, shorts_split
from akis.highlights_dialog import HighlightsDialog
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
W = highlights.WINDOW


def curve(seconds, lively=(), quiet=-60.0, talk=-25.0, base_speech=()):
    """A loudness curve: quiet, with speech in `base_speech` spans and lively spans full of rising peaks."""
    levels = [quiet] * int(seconds / W)
    for a, b in base_speech:
        for i in range(int(a / W), int(b / W)):
            levels[i] = talk
    for a, b in lively:
        for i in range(int(a / W), int(b / W)):
            levels[i] = talk
        t = a + 0.5
        while t < b:
            for i in range(int(t / W), int((t + 0.2) / W)):
                levels[i] = -8.0
            t += 3.0
    return levels


class ScoreTests(unittest.TestCase):
    def test_lively_stretches_score_highest_and_do_not_overlap(self):
        levels = curve(300, lively=[(40, 85), (200, 245)], base_speech=[(0, 300)])
        chosen = highlights.pick(highlights.score(levels, 45), 45, 2)
        self.assertEqual(len(chosen), 2)
        starts = [round(start) for start, _, _ in chosen]
        self.assertTrue(abs(starts[0] - 40) <= 4 and abs(starts[1] - 200) <= 4, starts)
        self.assertGreaterEqual(chosen[1][0], chosen[0][0] + 45)

    def test_details_and_reasons(self):
        levels = curve(120, lively=[(10, 55)], base_speech=[(0, 120)])
        start, value, details = highlights.pick(highlights.score(levels, 45), 45, 1)[0]
        self.assertGreater(details['rises'], 5)
        self.assertGreater(details['speech'], 0.9)
        text = highlights.reasons(details)
        self.assertIn('neredeyse kesintisiz konuşma', text)
        self.assertIn('sesin yükseldiği', text)
        english = highlights.reasons(details, lambda t: i18n.translate(t, 'en'))
        self.assertIn('moments where the voice rises', english)
        self.assertEqual(highlights.reasons({'speech': 0.1, 'rises': 0, 'energy': 0}), 'sakin bir bölüm')

    def test_too_short_or_empty(self):
        self.assertEqual(highlights.score([-30.0] * 100, 45), [])
        self.assertEqual(highlights.pick([], 45, 3), [])

    def test_ends_move_to_nearby_pauses(self):
        self.assertEqual(highlights.snap(40.0, 85.0, [38.5, 86.0, 120.0], 300), (38.5, 86.0))
        self.assertEqual(highlights.snap(40.0, 85.0, [30.0, 95.0], 300), (40.0, 85.0))           # too far away
        self.assertEqual(highlights.snap(-2.0, 400.0, [], 300), (0.0, 300))

    def test_timeline_curve_follows_the_edit(self):
        levels = [-10.0] * int(20 / W) + [-50.0] * int(20 / W)        # loud first 20 s of the source, then quiet
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 100, source_in=250),
                                                                     Clip('a.mp4', 100, 100, source_in=0)])])
        found = highlights.timeline_levels(timeline, lambda source: levels)
        self.assertEqual(len(found), int(20 / W))
        self.assertEqual(found[10], -50.0)                    # the first clip shows the quiet part
        self.assertEqual(found[int(15 / W)], -10.0)           # the second shows the loud part

    def test_find_returns_snapped_stretches_on_the_edit(self):
        levels = curve(180, lively=[(60, 105)], base_speech=[(0, 180)])
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 1800)])])
        found = highlights.find(timeline, lambda source: levels, length=45, count=1, pauses=[58.0])
        (start, end, value, details), = found
        self.assertEqual(start, 58.0)


class DialogTests(unittest.TestCase):
    def found(self):
        return [(10.0, 55.0, 3.0, {'speech': 0.9, 'rises': 4, 'energy': 0.3}),
                (100.0, 145.0, 2.0, {'speech': 0.7, 'rises': 0, 'energy': 0.0})]

    def test_ticked_rows_and_titles_come_back(self):
        dialog = HighlightsDialog(found=self.found(), titles=['Birinci', 'İkinci'])
        self.assertEqual(dialog.table.item(0, 0).text(), '0:10 – 0:55')
        self.assertIn('sesin yükseldiği 4 an', dialog.table.item(0, 2).text())
        dialog.table.item(1, 3).setText('Yeni başlık')
        self.assertEqual(dialog.selection(), ([(10.0, 55.0), (100.0, 145.0)], ['Birinci', 'Yeni başlık']))
        dialog.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dialog.selection(), ([(100.0, 145.0)], ['Yeni başlık']))
        dialog.table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(dialog.export_button.isEnabled())

    def test_english(self):
        dialog = HighlightsDialog(found=self.found(), language='en')
        self.assertEqual(dialog.windowTitle(), 'Highlights')
        self.assertIn('almost non-stop speech', dialog.table.item(0, 2).text())


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=180.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'vlog.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))

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

    def test_found_stretches_are_exported_as_unnumbered_shorts(self):
        w = self.window
        started = []
        levels = curve(180, lively=[(60, 105)], base_speech=[(0, 180)])
        with patch('akis.silence_cut.measure', return_value=levels), \
             patch('akis.highlights_dialog.HighlightsDialog.exec', new=lambda dialog: 1), \
             patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory', return_value=str(self.root)), \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.find_highlights()
            analysis = started.pop(0)
            analysis.start()
            self.assertTrue(analysis.wait(20000))
            app.processEvents()
        worker = started[0]
        self.assertIsInstance(worker, shorts_split.ShortsExportWorker)
        self.assertFalse(worker.numbered)
        self.assertTrue(any(abs(start - 60) <= 4 for start, end in worker.parts), worker.parts)

    def test_short_videos_are_not_searched(self):
        from akis.timeline_model import Clip as MainClip
        w = self.window
        w.show_timeline(Timeline(fps_num=30, tracks=[Track('video', 'V', [MainClip('a.mp4', 0, 900)])]))
        with patch('main.QMessageBox.information') as told:
            w.find_highlights()
        self.assertIn('en az bir dakikalık', told.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
