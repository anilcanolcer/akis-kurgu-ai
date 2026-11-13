"""Cuts on the beat: finding the beat, moving the cuts, and the button (the music stays where it is)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import beat_sync
from akis.beat_sync import beats, snap_segments
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


def pulses(period, phase=0.0, seconds=20.0, hop=beat_sync.HOP):
    """An onset curve with a sharp rise every `period` seconds."""
    curve = [0.0] * int(seconds / hop)
    t = phase
    while t < seconds:
        if int(round(t / hop)) < len(curve):
            curve[int(round(t / hop))] = 1000.0
        t += period
    return curve


class BeatTests(unittest.TestCase):
    def test_tempo_and_phase(self):
        found = beats(pulses(0.5, 0.12))
        self.assertAlmostEqual(found[0], 0.12, places=2)
        self.assertTrue(all(abs(b - a - 0.5) < 0.011 for a, b in zip(found, found[1:])))

    def test_double_time_is_not_mistaken_for_half_time(self):
        found = beats(pulses(0.4))                       # 150 BPM
        self.assertAlmostEqual(found[1] - found[0], 0.4, places=2)

    def test_no_steady_beat(self):
        self.assertEqual(beats([0.0] * 2000), [])
        self.assertEqual(beats([5.0] * 100), [])         # too short to tell

    def test_unreadable_music_has_no_onsets(self):
        failed = lambda *a, **k: subprocess.CompletedProcess([], 1, b'', b'')
        self.assertEqual(beat_sync.read_onsets('ffmpeg', 'x.mp3', runner=failed), [])


class SnapTests(unittest.TestCase):
    def test_each_cut_moves_to_the_nearest_close_beat(self):
        segments = [{'source': 0, 'start': 0, 'end': 1.8}, {'source': 1, 'start': 5, 'end': 7.1}, {'source': 0, 'start': 3, 'end': 4}]
        new, moved = snap_segments(segments, [0, 2, 4, 6], {0: 10, 1: 10})
        self.assertEqual(moved, 2)
        self.assertEqual(new[0]['end'], 2.0)            # cut at 1.8 s -> beat at 2 s
        self.assertAlmostEqual(new[1]['end'], 7.0)       # next cut at 2 + 2.1 = 4.1 s -> beat at 4 s
        self.assertEqual(new[2], segments[2])            # the last clip's end is not a cut

    def test_far_beats_and_source_limits_are_respected(self):
        segments = [{'source': 0, 'start': 0, 'end': 2.9}, {'source': 0, 'start': 5, 'end': 6}]
        self.assertEqual(snap_segments(segments, [0, 4], {0: 10})[1], 0)            # 1.1 s away: too far
        new, moved = snap_segments([{'source': 0, 'start': 8, 'end': 9.8}, {'source': 0, 'start': 0, 'end': 1}],
                                   [2.2], {0: 10})
        self.assertEqual((moved, new[0]['end']), (1, 10))                          # only 0.2 s of source left
        new, _ = snap_segments([{'source': 0, 'start': 0, 'end': 0.5}, {'source': 0, 'start': 5, 'end': 6}], [0.1], {0: 10})
        self.assertAlmostEqual(new[0]['end'] - new[0]['start'], beat_sync.MIN_LENGTH)

    def test_input_is_not_changed(self):
        segments = [{'source': 0, 'start': 0, 'end': 1.8}, {'source': 0, 'start': 3, 'end': 4}]
        snap_segments(segments, [2.0], {0: 10})
        self.assertEqual(segments[0]['end'], 1.8)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealMusicTests(unittest.TestCase):
    def test_kick_drum_at_120_bpm(self):
        with tempfile.TemporaryDirectory() as folder:
            music = Path(folder) / 'kick.wav'
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            "aevalsrc='0.8*sin(2*PI*55*t)*exp(-30*mod(t-0.12,0.5))*gte(t,0.12)+0.05*sin(2*PI*2000*t)':s=44100:d=12",
                            str(music)], check=True)
            found = beats(beat_sync.read_onsets(FFMPEG, music))
            later = beats(beat_sync.read_onsets(FFMPEG, music, start=1.0, duration=8))
        self.assertGreater(len(found), 20)
        self.assertTrue(all(abs(((b - 0.12 + 0.25) % 0.5) - 0.25) < 0.02 for b in found))
        self.assertTrue(all(abs(((b + 1.0 - 0.12 + 0.25) % 0.5) - 0.25) < 0.02 for b in later))   # read from 1 s in


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.MediaService.duration', return_value=10.0).start()
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

    def test_without_music_it_says_so(self):
        with patch('main.QMessageBox.information') as told:
            self.window.snap_cuts_to_beat()
        self.assertIn('müzik ekleyin', told.call_args.args[2])

    def test_cuts_move_to_the_beat_and_the_music_stays(self):
        w = self.window
        video = str(self.video)
        music = Clip(str(self.root / 'm.mp3'), 0, 300)
        w.show_timeline(Timeline(fps_num=30, tracks=[
            Track('video', 'Video', [Clip(video, 0, 54, source_in=0), Clip(video, 54, 60, source_in=150)]),
            Track('audio', 'Müzik', [music]), Track('text', 'Yazı', [Clip('', 60, 30, text='Merhaba')])]))
        with patch('main.beat_sync.read_onsets', return_value=pulses(0.5, 0.0, 10.0)):
            w.snap_cuts_to_beat()
            self.assertTrue(w.worker.wait(10000))          # the beat is read off the window's thread
            app.processEvents()
        main, sound = w.multitrack.tracks[0].clips, w.multitrack.tracks[1].clips
        self.assertEqual(main[0].length, 60)            # the cut at 1.8 s moved to the beat at 2 s
        self.assertEqual(main[1].start, 60)
        self.assertEqual([(c.start, c.length, c.source_in) for c in sound], [(0, 300, 0)])
        self.assertIn('1 kesim müziğin vuruşuna oturtuldu', w.status_label.text())
        self.assertTrue(w.undo())
        self.assertEqual(w.multitrack.tracks[0].clips[0].length, 54)


if __name__ == '__main__':
    unittest.main()
