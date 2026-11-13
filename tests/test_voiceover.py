"""Voiceover: choosing a voice, the Windows speech route, the fallback, and placing it on the timeline."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import tts_service
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
VOICES = [('id-zira', 'Microsoft Zira', 'en-US'), ('id-tolga', 'Microsoft Tolga', 'tr-TR')]


class PickTests(unittest.TestCase):
    def test_asked_voice_then_the_language_then_none(self):
        self.assertEqual(tts_service.pick_voice(VOICES, 'id-zira'), 'id-zira')
        self.assertEqual(tts_service.pick_voice(VOICES, None, 'tr'), 'id-tolga')
        self.assertEqual(tts_service.pick_voice(VOICES, 'gone', 'en'), 'id-zira')
        self.assertIsNone(tts_service.pick_voice(VOICES, None, 'de'))
        self.assertIsNone(tts_service.pick_voice([], 'id-zira'))


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class SynthesisTests(unittest.TestCase):
    def test_empty_text_is_refused(self):
        with self.assertRaises(ValueError):
            tts_service.synthesize('  ', 'voice.wav')

    def test_injected_runner_uses_the_powershell_route(self):
        seen = []

        def runner(command, **options):
            seen.append(command[0])
            return subprocess.CompletedProcess(command, 1, '', 'hata')
        with self.assertRaises(RuntimeError):
            tts_service.synthesize('Merhaba', 'voice.wav', runner)
        self.assertEqual(seen, ['powershell.exe'])

    def test_without_the_windows_speech_packages_powershell_is_the_fallback(self):
        seen = []

        def runner(command, **options):
            seen.append(command[0])
            return subprocess.CompletedProcess(command, 1, '', 'hata')
        with patch('akis.tts_service._winrt', return_value=None), \
             patch('akis.tts_service.subprocess.run', runner):
            with self.assertRaises(RuntimeError):
                tts_service.synthesize('Merhaba', 'voice.wav', runner)
        self.assertEqual(seen, ['powershell.exe'])

    def test_real_windows_voice_writes_a_wav(self):
        installed = tts_service.voices()
        if not installed:
            self.skipTest('no Windows speech voices or packages here')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'ses.wav'
            self.assertEqual(tts_service.synthesize('Merhaba, bu bir deneme.', target, language='tr'), str(target))
            with wave.open(str(target)) as sound:
                self.assertGreater(sound.getnframes() / sound.getframerate(), 0.5)


class TimelineTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        self.window.show_timeline(Timeline(fps_num=30, tracks=[Track('video', 'Video', [Clip('a.mp4', 0, 300)])]))

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def voice_tracks(self):
        return [(t.name, [(c.start, c.length) for c in t.clips]) for t in self.window.multitrack.tracks if t.kind == 'audio']

    def test_voiceover_lands_at_the_playhead_and_a_busy_track_gets_a_neighbour(self):
        w = self.window
        w.place_voiceover('v1.wav', 30, 2.0)
        w.place_voiceover('v2.wav', 90, 1.0)
        w.place_voiceover('v3.wav', 40, 1.0)                  # overlaps the first: goes on a second track
        self.assertEqual(self.voice_tracks(), [('Seslendirme', [(30, 60), (90, 30)]), ('Seslendirme 2', [(40, 30)])])

    def test_finished_voiceover_is_one_undo_step_and_joins_the_media_list(self):
        w = self.window
        w._voiceover_at = 15
        with patch('main.MediaService.duration', return_value=1.5):
            w.on_voiceover(str(self.root / 'ses.wav'))
        self.assertEqual(self.voice_tracks(), [('Seslendirme', [(15, 45)])])
        self.assertIn('Seslendirme zaman çizelgesine eklendi: ses.wav', w.status_label.text())
        self.assertTrue(w.undo())
        self.assertEqual(self.voice_tracks(), [])

    def test_without_the_timeline_option_it_only_saves(self):
        w = self.window
        w._voiceover_at = None
        w.on_voiceover('C:/x/ses.wav')
        self.assertEqual(self.voice_tracks(), [])
        self.assertEqual(w.status_label.text(), 'Ses kaydedildi: C:/x/ses.wav')

    def test_voice_list_starts_with_the_automatic_choice(self):
        self.assertIsNone(self.window.tts_voice.itemData(0))
        self.assertEqual(self.window.tts_voice.count(), 1 + len(tts_service.voices()))


if __name__ == '__main__':
    unittest.main()
