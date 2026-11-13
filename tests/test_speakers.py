"""Separating speakers by voice pitch: utterances, grouping, safety for one voice, markers, the window."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox

from akis import speakers
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
RATE = speakers.RATE


def voice(pitch, seconds, seed=0):
    """A buzzy, voice-like tone (harmonics of `pitch`) with a little wobble and noise."""
    t = np.arange(int(seconds * RATE)) / RATE
    rng = np.random.default_rng(seed)
    f = pitch * (1 + 0.03 * np.sin(2 * np.pi * 3 * t))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    tone = sum(np.sin(k * phase) / k for k in range(1, 12))
    return (0.2 * tone + 0.01 * rng.standard_normal(len(t))).astype(np.float32)


def talk(turns, pause=1.0):
    """Samples and timed words for [(pitch, seconds)] said one after the other with pauses between."""
    pieces, words, at = [], [], 0.0
    for index, (pitch, seconds) in enumerate(turns):
        pieces.append(voice(pitch, seconds, index))
        for k in range(int(seconds / 0.4)):
            words.append({'text': f'söz{index}_{k}', 'start': at + k * 0.4, 'end': at + k * 0.4 + 0.35})
        at += seconds
        pieces.append(np.zeros(int(pause * RATE), dtype=np.float32))
        at += pause
    return np.concatenate(pieces), words


class PitchEmbedder:
    """Stands in for the model in window tests: a print that points by the voice's pitch."""
    def print_of(self, samples):
        vector = speakers.voice_print(samples)
        if vector is None:
            return None
        angle = np.radians((speakers._pitch_semitones(vector) - 80) * 9)     # an octave apart: far apart
        return np.array([np.cos(angle), np.sin(angle)])


class ModelGroupTests(unittest.TestCase):
    def unit(self, angle):
        return np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))])

    def test_similar_prints_group_and_different_ones_do_not(self):
        prints = [self.unit(a) for a in (0, 5, 85, 3, 88, 90, 2)]       # cos(85°) ≈ 0.09: different people
        self.assertEqual(speakers.cluster_model(prints, [1] * 7), [0, 0, 1, 0, 1, 1, 0])
        same = [self.unit(a) for a in (0, 40, 20, 55, 10)]               # one voice varying (cos ≥ 0.57)
        self.assertEqual(set(speakers.cluster_model(same, [1] * 5)), {0})

    def test_a_brief_group_joins_the_most_alike(self):
        prints = [self.unit(a) for a in (0, 2, 4, 80)]
        self.assertEqual(speakers.cluster_model(prints, [10, 10, 10, 0.5]), [0, 0, 0, 0])
        self.assertEqual(speakers.cluster_model([], []), [])


class GroupTests(unittest.TestCase):
    def test_words_join_into_utterances_at_pauses(self):
        words = [{'text': 'a', 'start': 0, 'end': 0.3}, {'text': 'b', 'start': 0.4, 'end': 0.7},
                 {'text': 'c', 'start': 1.5, 'end': 1.8}, {'bad': 1}]
        self.assertEqual(speakers.utterances(words), [(0.0, 0.7, 'a b'), (1.5, 1.8, 'c')])

    def test_two_clearly_different_voices_alternate(self):
        samples, words = talk([(120, 3), (240, 3), (125, 2.5), (230, 3), (118, 3)])
        found = speakers.find(samples, words)
        self.assertEqual([s for _, _, s, _ in found], [0, 1, 0, 1, 0])
        totals = speakers.summary(found)
        self.assertEqual(sorted(totals), [0, 1])
        self.assertAlmostEqual(totals[1][0], 6, delta=0.5)

    def test_one_voice_rising_and_falling_stays_one_speaker(self):
        samples, words = talk([(110, 3), (135, 3), (120, 2), (145, 3), (115, 3)])
        self.assertEqual({s for _, _, s, _ in speakers.find(samples, words)}, {0})

    def test_a_brief_other_voice_is_not_a_speaker(self):
        samples, words = talk([(120, 6), (240, 0.9), (122, 6), (118, 6)])
        self.assertEqual({s for _, _, s, _ in speakers.find(samples, words)}, {0})

    def test_nothing_to_judge(self):
        self.assertEqual(speakers.find(np.zeros(RATE, dtype=np.float32), []), [])
        self.assertEqual(speakers.cluster([], []), [])

    def test_markers_follow_the_edit(self):
        found = [(0.0, 2.0, 0, 'a'), (3.0, 5.0, 1, 'b'), (6.0, 8.0, 1, 'c'), (9.0, 10.0, 0, 'd')]
        clips = [Clip('a.mp4', 0, 50, source_in=0), Clip('a.mp4', 50, 100, source_in=60, style={'speed': 2.0})]
        marks = speakers.markers(found, clips, 10)
        self.assertEqual(marks, [{'frame': 0, 'label': 'Konuşmacı 1'}, {'frame': 30, 'label': 'Konuşmacı 2'},
                                 {'frame': 65, 'label': 'Konuşmacı 1'}])


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.app_support.app_data_dir', return_value=self.root / 'data').start()   # never the real model folder
        patch('akis.media_service.MediaService.duration', return_value=24.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = self.root / 'roportaj.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))
        self.samples, self.words = talk([(120, 3), (240, 3), (125, 3), (235, 3), (118, 3)])

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def model(self, folder):
        return Path(folder) / 'model.onnx'

    def run_speakers(self, choice):
        w = self.window
        started, shown = [], []

        def pick(box):
            shown.append(box.text())
            return next((b for b in box.buttons() if b.text() == choice), None)
        with patch('akis.ai_service.local_transcribe', return_value=[{'start': 0, 'end': 20, 'text': 'x', 'words': self.words}]), \
             patch('akis.speakers.decode', return_value=self.samples), \
             patch('akis.speaker_model.download', side_effect=lambda folder: self.model(folder)), \
             patch('akis.speaker_model.available', return_value=True), \
             patch('akis.speaker_model.Embedder', side_effect=lambda path: PitchEmbedder()), \
             patch.object(QMessageBox, 'exec', lambda box: 0), patch.object(QMessageBox, 'clickedButton', pick), \
             patch('PySide6.QtWidgets.QMessageBox.information') as told, \
             patch.object(w, 'start_worker', side_effect=lambda: started.append(w.worker)):
            w.separate_speakers()
            started[0].start()
            self.assertTrue(started[0].wait(20000))
            app.processEvents()
        return shown, told

    def test_changes_are_marked(self):
        shown, _ = self.run_speakers('Değişimleri işaretle')
        self.assertIn('2 konuşmacı bulundu', shown[0])
        labels = [m['label'] for m in self.window.multitrack.markers]
        self.assertEqual(labels, ['Konuşmacı 1', 'Konuşmacı 2', 'Konuşmacı 1', 'Konuşmacı 2', 'Konuşmacı 1'])
        self.window.undo()
        self.assertEqual(self.window.multitrack.markers, [])

    def test_keeping_one_speaker_cuts_the_other(self):
        before = sum(c.length for c in self.window.multitrack.tracks[0].clips)
        self.run_speakers('Yalnız Konuşmacı 1')
        after = sum(c.length for c in self.window.multitrack.tracks[0].clips)
        fps = self.window.multitrack.fps_num / self.window.multitrack.fps_den
        self.assertAlmostEqual((before - after) / fps, 6.0, delta=0.6)        # speaker 2 spoke 2 × 3 s

    def test_one_voice_is_reported(self):
        self.samples, self.words = talk([(120, 3), (130, 3), (118, 3)])
        _, told = self.run_speakers('Değişimleri işaretle')
        self.assertEqual(told.call_args.args[2], 'Tek konuşmacı bulundu.')

    def test_without_the_model_pitch_still_separates(self):
        self.model = lambda folder: (_ for _ in ()).throw(OSError('çevrimdışı'))
        shown, _ = self.run_speakers('Değişimleri işaretle')
        self.assertIn('2 konuşmacı bulundu', shown[0])
        self.samples, self.words = talk([(120, 3), (130, 3), (118, 3)])
        _, told = self.run_speakers('Değişimleri işaretle')
        self.assertIn('perdeden ayrıldı', told.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
