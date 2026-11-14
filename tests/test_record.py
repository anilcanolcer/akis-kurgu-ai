"""Recording: the ffmpeg screen recorder, the dialog's sources and states, and adding the result."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import screen_record
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


class FakeScreen:
    def __init__(self, x=0, y=0, width=1280, height=720, ratio=1.25, name='Ekran 1'):
        self._geometry = SimpleNamespace(x=lambda: x, y=lambda: y, width=lambda: width, height=lambda: height)
        self.ratio, self._name = ratio, name

    def geometry(self):
        return self._geometry

    def devicePixelRatio(self):
        return self.ratio

    def name(self):
        return self._name


class RecorderTests(unittest.TestCase):
    def test_screen_area_in_physical_pixels_and_even(self):
        self.assertEqual(screen_record.screen_area(FakeScreen(x=1280, width=1281, height=721)), (1600, 0, 1600, 900))

    def test_command_with_and_without_a_microphone(self):
        plain = screen_record.command('ffmpeg', (10, 20, 640, 360), 'out.mp4')
        self.assertIn('gdigrab', plain)
        self.assertEqual(plain[plain.index('-video_size') + 1], '640x360')
        self.assertEqual((plain[plain.index('-offset_x') + 1], plain[plain.index('-offset_y') + 1]), ('10', '20'))
        self.assertNotIn('dshow', plain)
        mic = screen_record.command('ffmpeg', (0, 0, 640, 360), 'out.mp4', 'Mikrofon (USB)')
        self.assertIn('audio=Mikrofon (USB)', mic)
        self.assertIn('1:a', mic)

    def test_microphone_names_from_ffmpeg(self):
        listing = ('[dshow @ 0] "HD Kamera" (video)\n[dshow @ 0]   Alternative name "@device_pnp_x"\n'
                   '[dshow @ 0] "Mikrofon (Realtek)" (audio)\n[dshow @ 0] "Stereo Mix" (audio)\n')
        fake = lambda *a, **k: SimpleNamespace(stderr=listing)
        self.assertEqual(screen_record.audio_devices('ffmpeg', run=fake), ['Mikrofon (Realtek)', 'Stereo Mix'])
        self.assertEqual(screen_record.audio_devices('ffmpeg', run=lambda *a, **k: (_ for _ in ()).throw(OSError())), [])

    def test_stop_finishes_the_file_and_reports_a_missing_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'k.mp4'
            sent = []

            class Process:
                stderr = SimpleNamespace(closed=False, read=lambda: b'device busy')

                def poll(self):
                    return None

                def communicate(self, input=None, timeout=None):
                    sent.append(input)
                    if write:
                        out.write_bytes(b'x' * 10)
                    return b'', b''
            write = True
            recorder = screen_record.ScreenRecorder('ffmpeg', popen=lambda *a, **k: Process())
            recorder.start((0, 0, 640, 360), out)
            self.assertTrue(recorder.recording)
            self.assertEqual(recorder.stop(), str(out))
            self.assertEqual(sent, [b'q'])                       # asked to finish, not killed
            out.unlink()
            write = False
            recorder.start((0, 0, 640, 360), out)
            with self.assertRaises(RuntimeError):
                recorder.stop()
            with self.assertRaises(RuntimeError):
                recorder.stop()                                   # nothing running any more

    @unittest.skipUnless(FFMPEG and os.environ.get('AKIS_REAL_SCREEN') == '1', 'gerçek ekran kaydı için AKIS_REAL_SCREEN=1')
    def test_a_real_short_screen_recording(self):
        import time
        from akis.media_service import MediaService
        with tempfile.TemporaryDirectory() as tmp:
            recorder = screen_record.ScreenRecorder(FFMPEG)
            out = Path(tmp) / 'ekran.mp4'
            recorder.start((0, 0, 320, 180), out)
            time.sleep(2)
            recorder.stop()
            self.assertAlmostEqual(MediaService(FFMPEG).duration(out), 2, delta=0.8)


class FakeDevices:
    @staticmethod
    def videoInputs():
        return []

    @staticmethod
    def audioInputs():
        return []

    @staticmethod
    def defaultAudioInput():
        return None


class DialogTests(unittest.TestCase):
    def test_sources_without_a_camera_or_microphone(self):
        from akis.record_dialog import CAMERA, MIC_ONLY, SCREEN, RecordDialog
        with tempfile.TemporaryDirectory() as tmp, \
             patch('akis.record_dialog.RecordDialog._screens', return_value=[FakeScreen(name='Ana ekran')]):
            d = RecordDialog(folder=tmp, devices=FakeDevices)
            kinds = [d.source.itemData(i)[0] for i in range(d.source.count())]
            self.assertEqual(kinds, [SCREEN, MIC_ONLY])
            self.assertEqual(d.source.itemText(0), 'Ekran: Ana ekran')
            self.assertTrue(d.start_button.isEnabled())                 # a screen needs no microphone
            self.assertIn('1600×900', d.placeholder.text())
            d.source.setCurrentIndex(1)
            self.assertFalse(d.start_button.isEnabled())                # sound only needs one
            self.assertIn('mikrofon görünmüyor', d.status.text())
            self.assertNotIn(CAMERA, kinds)
            d.close()

    def test_screen_recording_through_the_dialog(self):
        from akis.record_dialog import RecordDialog
        with tempfile.TemporaryDirectory() as tmp, \
             patch('akis.record_dialog.RecordDialog._screens', return_value=[FakeScreen()]):
            d = RecordDialog(folder=tmp, devices=FakeDevices)
            started = {}

            def start(area, output, microphone=None):
                started.update(area=area, output=output)
                Path(output).write_bytes(b'video')
            with patch.object(d.screen_recorder, 'start', side_effect=start), \
                 patch.object(type(d.screen_recorder), 'recording', new=property(lambda s: bool(started) and not started.get('done'))), \
                 patch.object(d.screen_recorder, 'stop', side_effect=lambda: (started.update(done=True), str(started['output']))[1]):
                d.start()
                self.assertFalse(d.start_button.isEnabled())
                self.assertTrue(d.stop_button.isEnabled())
                self.assertEqual(d.status.text(), 'Kaydediliyor…')
                d.stop()
            self.assertEqual(d.result(), 1)
            self.assertEqual((d.kind, Path(d.path).suffix), ('video', '.mp4'))
            self.assertTrue(Path(d.path).name.startswith('kayit-'))


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=4.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def fake_dialog(self, path, kind, accepted=True):
        return lambda *a, **k: SimpleNamespace(exec=lambda: int(accepted), path=str(path), kind=kind)

    def test_a_sound_recording_lands_at_the_playhead(self):
        w = self.window
        w.show_timeline(Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 100)])]))
        w.multitrack_view.playhead = 30
        sound = self.root / 'kayit-1.m4a'
        sound.write_bytes(b'x')
        with patch('akis.record_dialog.RecordDialog', side_effect=self.fake_dialog(sound, 'audio')):
            w.record_media()
        voice = next(t for t in w.multitrack.tracks if t.kind == 'audio')
        self.assertEqual((voice.clips[0].start, voice.clips[0].length, voice.clips[0].source), (30, 40, str(sound)))
        self.assertIn('Ses kaydı oynatma çizgisine eklendi', w.status_label.text())
        w.undo()
        self.assertFalse(any(t.kind == 'audio' and t.clips for t in w.multitrack.tracks))

    def test_a_video_recording_is_added_like_a_chosen_video(self):
        w = self.window
        video = self.root / 'kayit-2.mp4'
        video.write_bytes(b'x')
        with patch('akis.record_dialog.RecordDialog', side_effect=self.fake_dialog(video, 'video')), \
             patch.object(w, 'add_video') as added:
            w.record_media()
        added.assert_called_once_with(str(video))
        with patch('akis.record_dialog.RecordDialog', side_effect=self.fake_dialog(video, 'video', accepted=False)), \
             patch.object(w, 'add_video') as added:
            w.record_media()
        added.assert_not_called()

    def test_button_in_the_sidebar(self):
        from PySide6.QtWidgets import QPushButton
        w = self.window
        self.assertIn('⏺  Kayıt al', [b.text() for b in w.findChildren(QPushButton)])
        w.apply_language('en')
        self.assertIn('⏺  Record', [b.text() for b in w.findChildren(QPushButton)])


if __name__ == '__main__':
    unittest.main()
