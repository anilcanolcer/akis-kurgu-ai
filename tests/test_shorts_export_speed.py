"""Shorts limits and suggested titles use final playback time, while slices use timeline time."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis.shorts_dialog import ShortsDialog
from main import MainWindow

app = QApplication.instance() or QApplication([])


class ShortsSpeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.frame_rate', return_value=(10, 1)).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        self.video = self.root / 'source.mp4'
        self.video.touch()

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def choose(self, total, speed, limit, pauses=(), segments=()):
        window = self.window
        with patch('akis.media_service.MediaService.duration', return_value=total):
            self.assertTrue(window.load_video(str(self.video)))
        window.select_speed(speed)
        window.state.speed = speed
        window.caption_source = str(self.video)
        window.caption_segments = list(segments)
        dialogs, workers = [], []

        def create_dialog(parent, **parameters):
            dialog = ShortsDialog(parent, **parameters)
            dialog.limit.setValue(limit)
            dialogs.append(dialog)
            return dialog

        with patch('akis.window.exporting.ShortsDialog', side_effect=create_dialog), \
             patch.object(ShortsDialog, 'exec', return_value=1), \
             patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory', return_value=str(self.root)), \
             patch('akis.export_progress.space_problem', return_value=''), \
             patch.object(window, 'start_worker', side_effect=lambda: workers.append(window.worker)):
            window.choose_shorts(pauses, total)
        self.assertEqual(len(workers), 1)
        return dialogs[0], workers[0]

    def test_slow_motion_parts_respect_the_final_180_second_limit(self):
        dialog, worker = self.choose(360, 0.5, 180)
        self.assertEqual(dialog.total, 720)
        self.assertEqual(len(worker.parts), 4)
        self.assertEqual(worker.parts[0][0], 0)
        self.assertEqual(worker.parts[-1][1], 360)
        self.assertTrue(all(b - a <= 180 * 0.5 for a, b in worker.parts))
        self.assertTrue(all(first[1] == second[0] for first, second in zip(worker.parts, worker.parts[1:])))
        self.assertEqual(worker.adjustments['speed'], 0.5)

    def test_fast_playback_maps_pauses_titles_and_selected_slices_together(self):
        dialog, worker = self.choose(220, 2.0, 60, pauses=[106],
                                     segments=[{'start': 4, 'text': 'First.'}, {'start': 116, 'text': 'Second.'}])
        self.assertEqual((dialog.total, dialog.pauses, dialog.said),
                         (110, [53], [(2, 'First.'), (58, 'Second.')]))
        self.assertEqual(worker.parts, [(0, 106), (106, 220)])
        self.assertEqual(worker.titles, ['First', 'Second'])
        self.assertTrue(all((b - a) / worker.adjustments['speed'] <= 60 for a, b in worker.parts))


if __name__ == '__main__':
    unittest.main()
