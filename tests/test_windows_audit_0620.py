"""Regressions from the 0.6.20 Windows audit (second round: the remaining features through the real UI, and
damaged project settings opened in the window).

1. A project whose settings part was damaged or hand-edited ("state", "publish" or "ai_prompt" of the wrong
   kind, a colour value of 10**30…) was refused with Python's words ("'list' object has no attribute 'get'",
   "QPlainTextEdit.setPlainText called with wrong argument types"), an empty reason, or an "unexpected
   error" box first; the timeline, the work itself, could not be opened at all. Now the unusable settings go
   back to their defaults, the project opens, and the person is told which settings those were.
2. An export at a project playback speed other than 1.00× (Düzenle › Oynatma hızı) put the picture two frames
   (67 ms) behind its sound at 1.25×–2×, and one frame ahead at 0.5×–0.75×, where the video was also one
   frame short. The sound was on time; the frames were chosen by the muxer's frame-rate conversion.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from akis import project_service  # noqa: E402
from akis.timeline_model import Clip, Timeline, Track  # noqa: E402

# Written out (not imported) so these tests also run, and fail, against the old code.
REPAIRED = 'Proje açıldı. Dosyadaki şu ayarlar okunamadı ve varsayılana döndürüldü: {names}.'


def document(**changes):
    timeline = Timeline(tracks=[Track('text', 'Yazı', [Clip('', 0, 60, text='Başlık ğüş')])])
    state = {'source': '', 'aspect': '1:1 · Kare', 'brightness': 12, 'contrast': -5, 'saturation': 20, 'speed': 1.5,
             'export_profile': 'YouTube · 1920×1080', 'audio_level': True}
    doc = project_service.make_document(state, timeline, {'title': 'Yayın', 'caption': 'Metin', 'hashtags': '#a'}, 'İstek')
    for key, value in changes.items():
        if key.startswith('state_'):
            doc['state'][key[len('state_'):]] = value
        else:
            doc[key] = value
    return doc


class SettingsRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def write(self, doc):
        path = self.folder / 'proje ğüş.akis.json'
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        return path

    def test_damaged_settings_parts_still_open_the_timeline(self):
        for damage in ({'state': []}, {'state': 'metin'}, {'publish': 5}, {'publish': None},
                       {'state_source': 7}, {'state_start': 'abc'}):
            with self.subTest(damage=damage):
                loaded, source, missing = project_service.load_project(self.write(document(**damage)))
                self.assertEqual(Timeline.from_dict(loaded['timeline']).tracks[0].clips[0].text, 'Başlık ğüş')
                self.assertIsInstance(loaded['state'], dict)
                self.assertIsInstance(loaded['publish'], dict)
                self.assertEqual(source, '')

    def test_wrong_kinds_go_back_to_defaults_and_colours_into_range(self):
        doc = document(state_saturation=10 ** 30, state_brightness=float('inf'), state_speed='abc', state_aspect=[1],
                       state_audio_level='evet', ai_prompt={'x': 1})
        loaded = project_service.load(self.write(doc))
        state = loaded['state']
        self.assertEqual(state['saturation'], 50)
        for name in ('brightness', 'speed', 'aspect', 'audio_level'):
            self.assertNotIn(name, state)
        self.assertNotIn('ai_prompt', loaded)
        self.assertEqual(state['contrast'], -5)            # good values stay as they were

    def test_older_speed_text_and_good_files_are_left_alone(self):
        loaded = project_service.load(self.write(document(state_speed='1.25×')))
        self.assertEqual(loaded['state']['speed'], '1.25×')
        self.assertEqual(loaded['state']['brightness'], 12)
        self.assertEqual(loaded['publish'], {'title': 'Yayın', 'caption': 'Metin', 'hashtags': '#a'})


class WindowOpensDamagedSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QApplication.instance() or QApplication([])

    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.window._close_confirmed = True

    def open(self, doc, language='tr'):
        self.window.apply_language(language)
        path = Path(self.tmp.name) / 'proje.akis.json'
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        hooked = []
        hook = sys.excepthook
        sys.excepthook = lambda *exc: hooked.append(exc)
        self.addCleanup(setattr, sys, 'excepthook', hook)
        with patch.object(QMessageBox, 'critical') as critical, patch.object(QMessageBox, 'information') as information:
            opened = self.window.open_project_file(str(path))
            QApplication.processEvents()
        sys.excepthook = hook
        return opened, critical, information, hooked

    def test_the_window_opens_it_says_which_settings_and_shows_no_python(self):
        opened, critical, information, hooked = self.open(
            document(state_saturation=10 ** 30, state_contrast=-1e308, publish=5, ai_prompt={'x': 1}))
        self.assertTrue(opened)
        self.assertEqual(hooked, [])
        critical.assert_not_called()
        told = information.call_args[0][2]
        self.assertEqual(told, REPAIRED.format(names='kontrast, doygunluk, yayın metni, AI isteği'))
        w = self.window
        self.assertEqual((w.state.saturation, w.saturation.value()), (50, 50))
        self.assertEqual((w.state.contrast, w.contrast.value()), (-50, -50))
        self.assertEqual(w.state.brightness, 12)
        self.assertEqual(w.publish_title.text(), '')
        self.assertEqual(w.multitrack.tracks[0].clips[0].text, 'Başlık ğüş')

    def test_the_english_window_names_the_settings_in_english(self):
        opened, critical, information, hooked = self.open(document(state='metin'), language='en')
        self.assertTrue(opened)
        self.assertEqual(information.call_args[0][2],
                         'The project is open. These settings in the file could not be read and are back to their '
                         'defaults: project settings.')

    def test_a_good_project_opens_without_a_notice(self):
        opened, critical, information, hooked = self.open(document())
        self.assertTrue(opened)
        information.assert_not_called()
        self.assertEqual((self.window.state.speed, self.window.state.saturation), (1.5, 20))


class EnglishScreenReaderNameTests(unittest.TestCase):
    """3. In the English interface, controls without visible text kept their Turkish screen-reader names
    ("Arayüz dili", "Görünüm", "Altyazı görünümü"); seen in the real UI through UI Automation."""

    @classmethod
    def setUpClass(cls):
        QApplication.instance() or QApplication([])

    def test_accessible_names_follow_the_language_and_come_back(self):
        from main import MainWindow
        window = MainWindow()
        self.addCleanup(window.close)
        window._close_confirmed = True
        from PySide6.QtWidgets import QTabBar
        # The editor's own names; Qt names its tab-bar scroll buttons itself, from its own catalogue.
        named = lambda: {w.accessibleName() for w in window.findChildren(QWidget)  # noqa: E731
                         if w.accessibleName() and not isinstance(w.parent(), QTabBar)}
        turkish = named()
        window.apply_language('en')
        english = named()
        left = sorted(n for n in english if set(n) & set('çğışöüÇĞİŞÖÜ') and n != window.version_button.accessibleName())
        self.assertEqual(left, [])
        self.assertTrue({'Interface language', 'Appearance', 'Caption style'} <= english)
        window.apply_language('tr')
        self.assertEqual(named(), turkish)


FFMPEG = os.environ.get('AKIS_FFMPEG') or shutil.which('ffmpeg')


@unittest.skipUnless(FFMPEG, 'FFmpeg')
class ProjectSpeedFrameTests(unittest.TestCase):
    """Every output frame at a project speed shows the source frame that belongs to its time."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.tmp.name) / 'numbered.mp4'
        # 60 frames, each as bright as its own number (20 + 3 × frame), with a tone for the sound track.
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=64x36:r=30:d=2',
                        '-f', 'lavfi', '-i', 'sine=f=440:d=2', '-vf', "geq=lum='20+3*N':cb=128:cr=128",
                        '-c:v', 'libx264', '-crf', '0', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest',
                        str(cls.source)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def shown(self, path):
        # The luma plane as it is (a conversion to full-range grey would shift every value).
        raw = subprocess.run([FFMPEG, '-v', 'error', '-i', str(path), '-vf', 'extractplanes=y,scale=16:9',
                              '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True, check=True).stdout
        size = 16 * 9
        return [round((sum(raw[i:i + size]) / size - 20) / 3) for i in range(0, len(raw), size)]

    def test_frames_follow_the_speed_exactly(self):
        from akis.media_service import MediaService
        from akis.timeline_render import TimelineRenderer
        from akis.i18n import SPEEDS
        for speed in [s for s in SPEEDS if s != 1.0]:       # every speed the editor offers
            with self.subTest(speed=speed):
                timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(self.source), 0, 60)])])
                output = Path(self.tmp.name) / f'speed-{speed}.mp4'
                TimelineRenderer(MediaService(FFMPEG), (64, 36), speed=speed).export(timeline, output)
                shown = self.shown(output)
                expected = [int(i * speed + 1e-9) for i in range(round(60 / speed))]
                self.assertEqual(len(shown), len(expected))
                wrong = [(i, got, want) for i, (got, want) in enumerate(zip(shown, expected)) if got != want]
                self.assertEqual(wrong[:5], [])


if __name__ == '__main__':
    unittest.main()
