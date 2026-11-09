import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from main import MainWindow

app = QApplication.instance() or QApplication([])

class MainWindowFlowTests(unittest.TestCase):
    def test_video_load_and_volume_use_timeline_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'demo.mp4'
            video.touch()
            window = MainWindow()
            with patch('main.MediaService.duration', return_value=2.0), patch.object(window, 'seek_timeline'):
                window.load_video(str(video))
            self.assertEqual(window.multitrack.tracks[0].clips[0].length, 60)
            window.preview_audio_output.setVolume(.3)
            self.assertAlmostEqual(window.preview_audio_output.volume(), .3, places=2)
            window.close()

if __name__ == '__main__': unittest.main()
