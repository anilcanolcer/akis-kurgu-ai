import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from akis.timeline_model import Clip, Track, Timeline
from akis.timeline_service import set_clip_volume, playback_volume

app = QApplication.instance() or QApplication([])

class VolumeTests(unittest.TestCase):
    def test_volume_survives_split_and_project_roundtrip(self):
        c=Clip('clip.mp4',0,20); timeline=Timeline(tracks=[Track('video','v',[c])])
        set_clip_volume(timeline,(0,c.id),.25)
        self.assertAlmostEqual(playback_volume(timeline,5,.8),.2)
        right=timeline.tracks[0].split(c.id,10)
        self.assertEqual(right.volume,.25)
        self.assertEqual(Timeline.from_dict(timeline.to_dict()).tracks[0].clips[1].volume,.25)
    def test_legacy_defaults(self):
        self.assertEqual(Clip('old',0,2).volume,1)

    def test_volume_change_stops_proxy_with_stale_mix_and_refreshes_current_frame(self):
        from main import MainWindow

        class PlayingProxy:
            playing = True

            def __init__(self):
                self.pause_count = 0

            def is_ready(self, signature):
                return False

            def pause(self):
                self.pause_count += 1
                self.playing = False

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as folder, \
             patch('akis.app_support.recovery_dir', return_value=Path(folder) / 'recovery'):
            window = MainWindow()
            clip = Clip('video.mp4', 0, 120)
            window.multitrack = Timeline(tracks=[Track('video', 'Video', [clip])])
            window.multitrack_view.set_model(window.multitrack)
            window.multitrack_view.selected = (0, clip.id)
            window.timeline_frame = 33
            proxy = PlayingProxy()
            window.proxy = proxy
            with patch('PySide6.QtWidgets.QInputDialog.getInt', return_value=(25, True)), \
                 patch.object(window, 'canvas_size', return_value=(160, 90)), \
                 patch.object(window.preview, 'request') as request:
                window.set_clip_volume()

            self.assertAlmostEqual(clip.volume, 0.25)
            self.assertEqual(proxy.pause_count, 1)
            request.assert_called_once()
            self.assertEqual(request.call_args.args[1], 33)
            window._close_confirmed = True
            window.close()

if __name__ == '__main__': unittest.main()
