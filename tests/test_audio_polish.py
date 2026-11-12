"""Sound clean-up switches: the mix graph, real renders measured with ffmpeg, the window and the project file."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import audio_polish
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import LIMITER, TimelineRenderer

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


class GraphTests(unittest.TestCase):
    def test_no_option_is_the_plain_mix(self):
        self.assertEqual(audio_polish.mix(['[a1]'], [], (), LIMITER),
                         ['[a1]amix=inputs=1:duration=longest:normalize=0[aout]'])
        self.assertEqual(audio_polish.mix(['[a1]'], ['[a2]'], (), LIMITER, ',atempo=1.500000'),
                         [f'[a1][a2]amix=inputs=2:duration=longest:normalize=0,{LIMITER},atempo=1.500000[aout]'])
        self.assertEqual(audio_polish.mix([], [], ('level',), LIMITER), [])
        self.assertEqual(audio_polish.voice_filter(()), '')

    def test_level_comes_before_the_limiter_and_restores_the_sample_rate(self):
        line, = audio_polish.mix(['[a1]'], ['[a2]'], ('level',), LIMITER)
        self.assertIn(f'normalize=0,{audio_polish.LEVEL},{LIMITER}[aout]', line)
        self.assertTrue(audio_polish.LEVEL.endswith('aresample=48000'))

    def test_duck_needs_both_speech_and_music(self):
        for voices, music in ((['[a1]'], []), ([], ['[a2]'])):
            self.assertEqual(len(audio_polish.mix(voices, music, ('duck',), LIMITER)), 1)
        lines = audio_polish.mix(['[a1]', '[a3]'], ['[a2]'], ('duck',), LIMITER)
        graph = ';'.join(lines)
        self.assertIn('[a1][a3]amix=inputs=2:duration=longest:normalize=0[voice]', graph)
        self.assertIn('[a2]anull[music]', graph)
        self.assertIn('[voicekey]apad[voicepad]', graph)        # the compressor stops when its key ends
        self.assertIn(f'[music][voicepad]{audio_polish.DUCK}[ducked]', graph)
        self.assertTrue(lines[-1].endswith(f'{LIMITER}[aout]'))

    def test_options_are_checked_and_ordered(self):
        self.assertEqual(audio_polish.clean(['level', 'duck', 'level']), ('duck', 'level'))
        self.assertEqual(audio_polish.clean(None), ())
        with self.assertRaises(ValueError):
            audio_polish.clean(['loud'])
        with self.assertRaises(ValueError):
            TimelineRenderer(MediaService('ffmpeg'), (160, 90), audio=('bass',))


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealRenderTests(unittest.TestCase):
    """Renders short clips and measures the result, so the filters are proven to run and to do their job."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.media = MediaService(FFMPEG)
        run = lambda *args: subprocess.run([FFMPEG, '-v', 'error', '-y', *args], check=True)
        # A quiet talking video (tone for 2 s, then 2 s of silence), a hissy one, and steady music.
        run('-f', 'lavfi', '-i', 'color=c=gray:s=160x90:r=10:d=4', '-f', 'lavfi', '-i',
            "aevalsrc='0.05*sin(2*PI*300*t)*lt(t,2)':s=48000:d=4", '-shortest', str(cls.root / 'talk.mp4'))
        run('-f', 'lavfi', '-i', 'color=c=gray:s=160x90:r=10:d=3', '-f', 'lavfi', '-i',
            'anoisesrc=color=white:amplitude=0.02:sample_rate=48000:duration=3', '-shortest', str(cls.root / 'hiss.mp4'))
        run('-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=48000:duration=4', '-af', 'volume=0.5',
            str(cls.root / 'music.wav'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render(self, name, audio=(), music=False, source='talk.mp4', frames=40):
        tracks = [Track('video', 'Video', [Clip(str(self.root / source), 0, frames)])]
        if music:
            tracks.append(Track('audio', 'Müzik', [Clip(str(self.root / 'music.wav'), 0, frames)]))
        output = self.root / name
        TimelineRenderer(self.media, (160, 90), audio=audio).export(Timeline(fps_num=10, tracks=tracks), output)
        return output

    def mean_db(self, path, start=None, duration=None, band=None):
        args = [FFMPEG, '-hide_banner', '-nostats']
        if start is not None:
            args += ['-ss', str(start), '-t', str(duration)]
        chain = (f'bandpass=f={band}:width_type=h:w=200,' if band else '') + 'volumedetect'
        report = subprocess.run([*args, '-i', str(path), '-af', chain, '-f', 'null', '-'],
                                capture_output=True, text=True).stderr
        return float(re.search(r'mean_volume: (-?[\d.]+) dB', report).group(1))

    def sample_rate(self, path):
        report = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path)], capture_output=True, text=True).stderr
        return int(re.search(r'Audio:.*?(\d+) Hz', report).group(1))

    def test_level_makes_quiet_footage_louder(self):
        plain, levelled = self.render('plain.mp4'), self.render('level.mp4', ('level',))
        self.assertGreater(self.mean_db(levelled, 0.3, 1.5), self.mean_db(plain, 0.3, 1.5) + 6)
        self.assertEqual(self.sample_rate(levelled), 48000)

    def test_denoise_lowers_the_hiss(self):
        plain = self.render('hiss_plain.mp4', source='hiss.mp4', frames=30)
        cleaned = self.render('hiss_clean.mp4', ('denoise',), source='hiss.mp4', frames=30)
        self.assertLess(self.mean_db(cleaned, 1, 1.8), self.mean_db(plain, 1, 1.8) - 3)

    def test_music_dips_under_speech_and_returns(self):
        ducked = self.render('duck.mp4', ('duck',), music=True)
        plain = self.render('noduck.mp4', (), music=True)
        music = lambda path, start: self.mean_db(path, start, 0.8, band=1000)
        self.assertLess(music(ducked, 0.8), music(plain, 0.8) - 3)       # someone is speaking
        self.assertAlmostEqual(music(ducked, 3.1), music(plain, 3.1), delta=1.5)   # they stopped
        self.assertLess(music(ducked, 0.8), music(ducked, 3.1) - 3)

    def test_everything_together_still_renders_the_full_length(self):
        output = self.render('all.mp4', audio_polish.OPTIONS, music=True)
        self.assertAlmostEqual(self.media.duration(output), 4.0, delta=0.2)


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

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_switches_are_usable_and_off_by_default(self):
        w = self.window
        for box, name in w.audio_boxes():
            self.assertTrue(box.isEnabled())
            self.assertFalse(box.isChecked())
            self.assertNotIn('henüz yok', box.text())
        self.assertNotIn('audio', w.render_adjustments())

    def test_switches_reach_the_renderer_settings(self):
        w = self.window
        w.loudness.setChecked(True)
        w.music_duck.setChecked(True)
        self.assertEqual(w.render_adjustments()['audio'], ('duck', 'level'))
        TimelineRenderer(MediaService('ffmpeg'), (160, 90), **w.render_adjustments())   # accepted as given
        w.loudness.setChecked(False)
        w.music_duck.setChecked(False)
        self.assertNotIn('audio', w.render_adjustments())

    def test_project_file_keeps_the_switches(self):
        w = self.window
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(w.load_video(str(video)))
        w.noise_reduction.setChecked(True)
        document = w.project_document()
        w.noise_reduction.setChecked(False)
        w.apply_project_state(document)
        self.assertTrue(w.noise_reduction.isChecked())
        self.assertEqual(w.render_adjustments()['audio'], ('denoise',))

    def test_old_project_keys_do_not_switch_anything_on(self):
        w = self.window
        video = self.root / 'a.mp4'
        video.touch()
        self.assertTrue(w.load_video(str(video)))
        document = w.project_document()
        document['state'].update(noise_reduction=True, loudness_normalization=True, audio_duck='yes')
        w.apply_project_state(document)
        self.assertNotIn('audio', w.render_adjustments())
        self.assertFalse(w.music_duck.isChecked())


if __name__ == '__main__':
    unittest.main()
