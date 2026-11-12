"""Analysis results are kept per file while the app runs, and a changed file is analysed afresh."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from akis import analysis_cache, speech_settings
from akis.ai_workers import PromptEditWorker
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


class CacheTests(unittest.TestCase):
    def setUp(self):
        analysis_cache.clear()
        self.addCleanup(analysis_cache.clear)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.file = Path(tmp.name) / 'a.mp4'
        self.file.write_bytes(b'one')

    def test_computed_once_per_file_and_name(self):
        calls = []
        work = lambda: calls.append(1) or [1, 2]
        self.assertEqual(analysis_cache.remember(self.file, 'silences', work), [1, 2])
        self.assertEqual(analysis_cache.remember(str(self.file), 'silences', work), [1, 2])
        analysis_cache.remember(self.file, 'scenes', work)
        self.assertEqual(len(calls), 2)

    def test_changed_file_is_analysed_again_and_its_old_results_are_dropped(self):
        analysis_cache.remember(self.file, 'frame', lambda: b'x' * 1000)
        self.assertEqual(analysis_cache.held_bytes(), 1000)
        self.file.write_bytes(b'two, longer')
        calls = []
        analysis_cache.remember(self.file, 'frame', lambda: calls.append(1) or b'y' * 10)
        self.assertEqual(calls, [1])
        self.assertEqual(analysis_cache.held_bytes(), 10)

    def test_failed_results_and_unreadable_files_are_not_kept(self):
        calls = []
        failed = lambda: calls.append(1)
        for _ in range(2):
            analysis_cache.remember(self.file, 'transcript', failed, keep=lambda value: value is not None)
            analysis_cache.remember(self.file.with_name('missing.mp4'), 'silences', lambda: calls.append(1) or [])
        self.assertEqual(len(calls), 4)

    def test_memory_is_bounded_by_dropping_the_oldest_files(self):
        other = self.file.with_name('b.mp4')
        other.write_bytes(b'b')
        with patch.object(analysis_cache, 'MAX_BYTES', 1500):
            analysis_cache.remember(self.file, 'frame', lambda: b'x' * 1000)
            analysis_cache.remember(other, 'frame', lambda: b'y' * 1000)
        self.assertEqual(analysis_cache.held_bytes(), 1000)
        calls = []
        analysis_cache.remember(other, 'frame', lambda: calls.append(1) or b'')
        self.assertEqual(calls, [])                      # the newer file is still there


class WorkerTests(unittest.TestCase):
    """A second request on the same video does not analyse it again."""

    def setUp(self):
        analysis_cache.clear()
        self.addCleanup(analysis_cache.clear)
        speech_settings.set_current(speech_settings.DEFAULT_LANGUAGE, '')
        self.addCleanup(speech_settings.set_current, speech_settings.DEFAULT_LANGUAGE, '')
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.video = self.root / 'talk.mp4'
        self.video.write_bytes(b'video')
        self.timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(self.video), 0, 90)])])

    def analyse(self, whisper=None):
        worker = PromptEditWorker('k', 'm', 'OpenAI', 'kes', self.timeline, [(str(self.video), 3.0)], 'ffmpeg',
                                  whisper_model=whisper)
        media = MagicMock()
        media.cancelled = False
        media.has_audio.return_value = True
        media.silences.return_value = [(1.0, 2.0)]
        media.scene_changes.return_value = [1.5]
        media.dimensions.return_value = (1920, 1080)

        def extract(path, at, target):
            Path(target).write_bytes(b'jpeg')
            return subprocess.CompletedProcess([], 0)
        media.extract_frame.side_effect = extract
        worker.media = media
        with tempfile.TemporaryDirectory() as temp:
            frames = worker.analyse(temp)
        return worker, media, frames

    def test_second_analysis_reuses_everything(self):
        first_worker, first, frames = self.analyse()
        self.assertTrue(frames)
        self.assertEqual(first.silences.call_count, 1)
        second_worker, second, again = self.analyse()
        self.assertEqual((second.silences.call_count, second.scene_changes.call_count, second.extract_frame.call_count), (0, 0, 0))
        self.assertEqual(again, frames)
        self.assertEqual(second_worker.sources[0]['silences'], [(1.0, 2.0)])
        self.assertEqual(second_worker.sources[0]['scenes'], [1.5])

    def test_edited_video_file_is_analysed_again(self):
        self.analyse()
        self.video.write_bytes(b'a different video')
        _, media, _ = self.analyse()
        self.assertEqual(media.silences.call_count, 1)
        self.assertGreater(media.extract_frame.call_count, 0)

    def test_transcript_is_reused_until_model_or_speech_settings_change(self):
        words = [{'start': 0, 'end': 1, 'text': 'merhaba'}]
        with patch('akis.ai_workers.local_transcribe', return_value=words) as recognise:
            self.analyse('tiny')
            worker, _, _ = self.analyse('tiny')
            self.assertEqual(recognise.call_count, 1)
            self.assertEqual(worker.sources[0]['transcript'], words)
            self.analyse('small')
            self.assertEqual(recognise.call_count, 2)
            speech_settings.set_current(language='en')
            self.analyse('small')
            self.assertEqual(recognise.call_count, 3)

    def test_failed_recognition_is_tried_again_next_time(self):
        with patch('akis.ai_workers.local_transcribe', side_effect=RuntimeError('model yok')) as recognise:
            worker, _, _ = self.analyse('tiny')
            self.assertEqual(worker.sources[0]['transcript'], [])
            self.analyse('tiny')
        self.assertEqual(recognise.call_count, 2)


if __name__ == '__main__':
    unittest.main()
