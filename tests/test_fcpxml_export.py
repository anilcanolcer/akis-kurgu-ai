"""The FCPXML hand-off: times, the storyline with gaps, connected clips, and what is left out."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from akis import fcpxml_export
from akis.fcpxml_export import build, rational, volume_db
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


def media(duration=10.0, sound=True):
    fake = MagicMock()
    fake.duration.return_value = duration
    fake.has_audio.return_value = sound
    return fake


class TimeTests(unittest.TestCase):
    def test_whole_and_fractional_seconds(self):
        self.assertEqual(rational(60, 30, 1), '2s')
        self.assertEqual(rational(45, 30, 1), '3/2s')
        self.assertEqual(rational(1, 30000, 1001), '1001/30000s')
        self.assertEqual(rational(30, 30000, 1001), '1001/1000s')
        self.assertEqual(rational(0, 25, 1), '0s')

    def test_volume_in_decibels(self):
        self.assertEqual(volume_db(0.5), '-6.0dB')
        self.assertEqual(volume_db(0), '-96dB')


class BuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.a, self.b, self.music = (str(self.root / name) for name in ('a b.mp4', 'b.mp4', 'müzik.mp3'))

    def parse(self, timeline, canvas=(1080, 1920)):
        text, report = build(timeline, canvas, media())
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>'))
        return ET.fromstring(text.split('\n', 2)[2]), report

    def test_storyline_with_a_gap_and_the_sequence_format(self):
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', [Clip(self.a, 0, 60, source_in=30), Clip(self.b, 90, 30)])])
        root, report = self.parse(timeline)
        self.assertEqual(root.get('version'), '1.10')
        fmt = root.find('resources/format')
        self.assertEqual((fmt.get('frameDuration'), fmt.get('width'), fmt.get('height')), ('1/30s', '1080', '1920'))
        spine = list(root.find('library/event/project/sequence/spine'))
        self.assertEqual([item.tag for item in spine], ['asset-clip', 'gap', 'asset-clip'])
        first, gap, second = spine
        self.assertEqual((first.get('offset'), first.get('start'), first.get('duration')), ('0s', '1s', '2s'))
        self.assertEqual((gap.get('offset'), gap.get('duration')), ('2s', '1s'))
        self.assertEqual((second.get('offset'), second.get('duration')), ('3s', '1s'))
        self.assertEqual(root.find('library/event/project/sequence').get('duration'), '4s')
        self.assertEqual(report, {'clips': 2, 'texts': 0, 'transitions': 0, 'speeds': 0})

    def test_each_file_is_one_asset_pointing_at_the_original(self):
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'V', [Clip(self.a, 0, 30), Clip(self.a, 30, 30, source_in=90)])])
        root, _ = self.parse(timeline)
        assets = root.findall('resources/asset')
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].get('duration'), '10s')
        source = assets[0].find('media-rep').get('src')
        self.assertTrue(source.startswith('file:///'))
        self.assertIn('a%20b.mp4', source)
        self.assertEqual({clip.get('ref') for clip in root.iter('asset-clip')}, {assets[0].get('id')})

    def test_other_tracks_connect_in_their_parents_own_time(self):
        main = Track('video', 'V', [Clip(self.a, 0, 90, source_in=60)])        # shows source 2s..5s
        broll = Track('video', 'B', [Clip(self.b, 30, 30)])
        music = Track('audio', 'M', [Clip(self.music, 0, 120, volume=0.5)])
        root, report = self.parse(Timeline(fps_num=30, tracks=[main, broll, music]))
        first = root.find('library/event/project/sequence/spine/asset-clip')
        connected = {clip.get('lane'): clip for clip in first.findall('asset-clip')}
        self.assertEqual(set(connected), {'1', '-1'})
        self.assertEqual(connected['1'].get('offset'), '3s')      # local 2s + 1s into the parent
        self.assertEqual(connected['-1'].get('offset'), '2s')
        self.assertEqual(connected['-1'].get('audioRole'), 'music')
        self.assertEqual(connected['-1'].find('adjust-volume').get('amount'), '-6.0dB')
        gap = root.find('library/event/project/sequence/spine/gap')  # the music runs past the picture
        self.assertIsNotNone(gap)
        self.assertEqual(report['clips'], 3)

    def test_music_alone_hangs_off_a_gap(self):
        root, _ = self.parse(Timeline(fps_num=25, tracks=[Track('video', 'V'), Track('audio', 'M', [Clip(self.music, 25, 50)])]))
        gap = root.find('library/event/project/sequence/spine/gap')
        self.assertEqual(gap.find('asset-clip').get('offset'), '1s')

    def test_ntsc_rate_and_left_out_items_are_counted(self):
        video = Track('video', 'V', [Clip(self.a, 0, 30), Clip(self.a, 30, 30, style={'transition': 'fade'})])
        text = Track('text', 'Altyazı', [Clip('', 0, 30, text='Merhaba'), Clip('', 30, 30, text='Dünya')])
        root, report = self.parse(Timeline(fps_num=30000, fps_den=1001, tracks=[video, text]))
        self.assertEqual(root.find('resources/format').get('frameDuration'), '1001/30000s')
        self.assertEqual(report, {'clips': 2, 'texts': 2, 'transitions': 1, 'speeds': 0})
        self.assertEqual(fcpxml_export.describe(report), '2 klip yazıldı. 2 yazı ve altyazı klibi aktarılmadı. 1 geçiş aktarılmadı.')

    def test_muted_tracks_are_not_written(self):
        muted = Track('audio', 'M', [Clip(self.music, 0, 30)], muted=True)
        root, report = self.parse(Timeline(fps_num=30, tracks=[Track('video', 'V', [Clip(self.a, 0, 30)]), muted]))
        self.assertEqual(report['clips'], 1)
        self.assertEqual(len(root.findall('resources/asset')), 1)


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.MediaService.duration', return_value=2.0).start()
        patch('main.MediaService.has_audio', return_value=True).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_button_writes_the_file_and_reports_what_was_left_out(self):
        w = self.window
        target = self.root / 'kurgu'
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(target), '')), \
             patch.object(w, 'export_canvas_size', return_value=(1080, 1920)), \
             patch('main.QMessageBox.information') as shown:
            w.export_fcpxml()
        written = self.root / 'kurgu.fcpxml'
        self.assertTrue(written.is_file())
        ET.fromstring(written.read_text(encoding='utf-8').split('\n', 2)[2])
        self.assertIn('1 klip yazıldı.', shown.call_args.args[2])

    def test_cancelled_dialog_writes_nothing(self):
        with patch('main.QFileDialog.getSaveFileName', return_value=('', '')):
            self.window.export_fcpxml()
        self.assertEqual(list(self.root.glob('*.fcpxml')), [])


if __name__ == '__main__':
    unittest.main()
