"""Regression cases from the Windows workflow audit against 0.6.20."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from akis import beat_sync, speakers, story_service, tts_service
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


class FileAndTimingTests(unittest.TestCase):
    def test_short_clip_on_beat_is_never_extended_past_its_source(self):
        parts = [{'source': 0, 'start': 0, 'end': 0.1}, {'source': 1, 'start': 0, 'end': 2}]
        result, moved = beat_sync.snap_segments(parts, [0.1], {0: 0.1, 1: 2})
        self.assertEqual((result, moved), (parts, 0))

    def test_beat_analysis_selects_an_audible_clip(self):
        muted = Clip('silent.wav', 0, 50, volume=0)
        music = Clip('music.wav', 50, 50)
        timeline = Timeline(tracks=[Track('audio', 'A', [muted, music])])
        self.assertIs(beat_sync.music_clip(timeline), music)

    def test_repeated_and_trimmed_speech_is_marked_in_playback_order(self):
        utterances = [(0, 2, 0, 'A'), (2, 4, 1, 'B')]
        clips = [Clip('interview.mp4', 0, 10, source_in=25),
                 Clip('interview.mp4', 10, 40), Clip('interview.mp4', 50, 40)]
        self.assertEqual([(m['frame'], m['label']) for m in speakers.markers(utterances, clips, 10)],
                         [(0, 'Konuşmacı 2'), (10, 'Konuşmacı 1'), (30, 'Konuşmacı 2'),
                          (50, 'Konuşmacı 1'), (70, 'Konuşmacı 2')])

    def test_moving_story_and_media_together_reopens_scene_files(self):
        from akis.story_service import Scene, StoryState
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / 'Önce'
            before.mkdir()
            image, video = before / 'görsel.png', before / 'film.mp4'
            image.write_bytes(b'picture')
            video.write_bytes(b'video')
            story = before / 'sahne.hikaye.json'
            story_service.save_story(story, StoryState(scenes=[Scene(image_path=str(image), video_path=str(video))]))
            after = before.rename(Path(tmp) / 'Taşındı')
            scene = story_service.load_story(after / story.name).scenes[0]
            self.assertEqual(Path(scene.image_path).read_bytes(), b'picture')
            self.assertEqual(Path(scene.video_path).read_bytes(), b'video')

    @unittest.skipUnless(sys.platform == 'win32', 'Windows speech')
    def test_failed_voiceover_preserves_previous_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'eski.wav'
            target.write_bytes(b'previous')
            def fail(command, **options):
                request = json.loads(base64.b64decode(options['input']).decode())
                Path(request['path']).write_bytes(b'partial')
                return subprocess.CompletedProcess(command, 1, '', 'device unavailable')
            with self.assertRaises(RuntimeError):
                tts_service.synthesize('test', target, fail)
            self.assertEqual(target.read_bytes(), b'previous')
            self.assertEqual(list(target.parent.iterdir()), [target])


class EditorTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery'))
        self.window = MainWindow()
        self.window.apply_language('tr')
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_applying_transcript_with_no_matching_clip_preserves_existing_captions(self):
        from akis import edit_plan
        w = self.window
        existing = Track('text', edit_plan.CAPTION_TRACK, [Clip('', 0, 30, text='Keep these captions')])
        w.multitrack = Timeline(tracks=[Track('video','V',[Clip('new.mp4', 0, 30)]), existing])
        w.caption_source = 'other.mp4'
        w.caption_segments = [{'start':0, 'end':1, 'text':'Başka'}]
        w.apply_local_captions()
        self.assertIn(existing, w.multitrack.tracks)

    def test_analysis_finishing_after_an_edit_does_not_apply_the_old_result(self):
        import threading
        import time
        from PySide6.QtTest import QTest
        w = self.window
        release = threading.Event()
        completed = []
        w.run_analysis('Analiz', lambda: release.wait(10), completed.append)
        w.multitrack.tracks.append(Track('audio', 'Son düzenleme'))
        release.set()
        deadline = time.monotonic() + 10
        while (w._workers or not w.progress.isHidden()) and time.monotonic() < deadline:
            QTest.qWait(25)
        self.assertTrue(w.progress.isHidden())
        self.assertEqual(completed, [])

    def test_hundredth_overlapping_voiceover_gets_its_own_track(self):
        w = self.window
        w.multitrack = Timeline(tracks=[Track('audio', 'Seslendirme' if i == 1 else f'Seslendirme {i}',
                                              [Clip('v.wav', 0, 10)]) for i in range(1, 100)])
        w.place_voiceover('new.wav', 0, 1)
        self.assertEqual(w.multitrack.tracks[-1].name, 'Seslendirme 100')

    def test_voiceover_cannot_overwrite_project_audio(self):
        w = self.window
        original = self.root / 'music.wav'
        original.write_bytes(b'original')
        w.media_bin.add(str(original))
        w.tts_input.setPlainText('Merhaba')
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(original), '')), \
             patch('PySide6.QtWidgets.QMessageBox.warning') as warning, patch.object(w, 'start_worker') as start:
            w.create_voiceover()
        start.assert_not_called()
        warning.assert_called_once()
        self.assertEqual(original.read_bytes(), b'original')
