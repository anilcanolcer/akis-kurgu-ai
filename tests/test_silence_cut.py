"""“Sessizlikleri çıkar”: loudness curve, silent spans, the resulting cut, the dialog and a real render."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import array
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from akis import edit_plan, silence_cut
from akis.silence_cut import keep_segments, levels_from_pcm, silent_spans
from akis.silence_dialog import SilenceDialog
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')
RATE = silence_cut.SAMPLE_RATE


def pcm(*parts):
    """16-bit mono PCM from (seconds, amplitude 0..1) parts; a tone when loud, zeros when 0."""
    samples = array.array('h')
    for seconds, amplitude in parts:
        count = round(seconds * RATE)
        samples.extend(round(amplitude * 32767 * math.sin(2 * math.pi * 220 * i / RATE)) for i in range(count))
    return samples.tobytes()


def close(test, found, expected, places=1):
    test.assertEqual(len(found), len(expected), found)
    for (a, b), (c, d) in zip(found, expected):
        test.assertAlmostEqual(a, c, places=places)
        test.assertAlmostEqual(b, d, places=places)


class LevelTests(unittest.TestCase):
    def test_tone_is_loud_and_zeros_are_the_floor(self):
        levels = levels_from_pcm(pcm((0.5, 0.5), (0.5, 0)))
        self.assertEqual(len(levels), 50)
        self.assertTrue(all(-12 < level < -6 for level in levels[:24]), levels[:5])   # 0.5 sine ≈ -9 dBFS RMS
        self.assertTrue(all(level == silence_cut.FLOOR_DB for level in levels[26:]))

    def test_empty_and_odd_length_input(self):
        self.assertEqual(levels_from_pcm(b''), [])
        self.assertEqual(len(levels_from_pcm(b'\x00' * 81)), 1)

    def test_unreadable_file_measures_as_nothing(self):
        failed = lambda *a, **k: subprocess.CompletedProcess([], 1, b'', b'')
        self.assertEqual(silence_cut.measure('ffmpeg', 'x.mp4', failed), [])

        def missing(*a, **k):
            raise OSError('no ffmpeg')
        self.assertEqual(silence_cut.measure('ffmpeg', 'x.mp4', missing), [])


class SpanTests(unittest.TestCase):
    def setUp(self):
        self.levels = levels_from_pcm(pcm((1, 0.5), (1, 0), (1, 0.5), (0.3, 0), (1, 0.5), (0.7, 0)))

    def test_only_long_enough_silences_count(self):
        close(self, silent_spans(self.levels, -35, 0.5), [(1, 2), (4.3, 5)])
        close(self, silent_spans(self.levels, -35, 0.2), [(1, 2), (3, 3.3), (4.3, 5)])

    def test_threshold_decides_what_is_silent(self):
        quiet = levels_from_pcm(pcm((1, 0.5), (1, 0.01), (1, 0.5)))    # 0.01 sine ≈ -43 dBFS
        close(self, silent_spans(quiet, -35, 0.5), [(1, 2)])
        self.assertEqual(silent_spans(quiet, -50, 0.5), [])

    def test_no_audio_no_spans(self):
        self.assertEqual(silent_spans([], -35, 0.5), [])


class KeepTests(unittest.TestCase):
    def test_margin_stays_on_both_sides(self):
        segments, cuts = keep_segments([{'source': 0, 'start': 0, 'end': 10}], {0: [(2, 4)]}, margin=0.2)
        self.assertEqual(segments, [{'source': 0, 'start': 0, 'end': 2.2}, {'source': 0, 'start': 3.8, 'end': 10}])
        self.assertEqual(len(cuts), 1)
        self.assertEqual(cuts[0][0], 0)
        self.assertAlmostEqual(cuts[0][1], 2.2)
        self.assertAlmostEqual(cuts[0][2], 3.8)

    def test_silence_at_the_edges_is_removed_up_to_the_edge(self):
        segments, cuts = keep_segments([{'source': 0, 'start': 1, 'end': 9}], {0: [(0, 3), (8, 12)]}, margin=0.2)
        self.assertEqual(segments, [{'source': 0, 'start': 2.8, 'end': 8.2}])
        self.assertEqual(len(cuts), 2)

    def test_silence_shorter_than_two_margins_is_kept(self):
        segments, cuts = keep_segments([{'source': 0, 'start': 0, 'end': 10}], {0: [(2, 2.3)]}, margin=0.2)
        self.assertEqual(cuts, [])
        self.assertEqual(segments, [{'source': 0, 'start': 0, 'end': 10}])

    def test_only_the_segments_own_source_and_range_is_cut(self):
        before = [{'source': 0, 'start': 0, 'end': 5}, {'source': 1, 'start': 10, 'end': 20, 'transition': 'fade'}]
        segments, cuts = keep_segments(before, {0: [(12, 14)], 1: [(12, 14)]}, margin=0)
        self.assertEqual(segments, [{'source': 0, 'start': 0, 'end': 5},
                                    {'source': 1, 'start': 10, 'end': 12, 'transition': 'fade'},
                                    {'source': 1, 'start': 14, 'end': 20}])
        self.assertEqual([cut[0] for cut in cuts], [1])

    def test_sliver_between_two_silences_does_not_flicker(self):
        segments, cuts = keep_segments([{'source': 0, 'start': 0, 'end': 10}], {0: [(2, 4), (4.1, 6)]}, margin=0)
        self.assertEqual(segments, [{'source': 0, 'start': 0, 'end': 2}, {'source': 0, 'start': 6, 'end': 10}])
        self.assertEqual(len(cuts), 1)
        self.assertTrue(all(s['end'] - s['start'] >= silence_cut.MIN_KEEP for s in segments))

    def test_wholly_silent_segment_is_left_alone(self):
        before = [{'source': 0, 'start': 0, 'end': 5}]
        self.assertEqual(keep_segments(before, {0: [(0, 5)]}), (before, []))

    def test_input_is_not_modified(self):
        before = [{'source': 0, 'start': 0, 'end': 10}]
        keep_segments(before, {0: [(2, 4)]})
        self.assertEqual(before, [{'source': 0, 'start': 0, 'end': 10}])

    def test_summary_and_clock(self):
        before = [{'source': 0, 'start': 0, 'end': 100}]
        after, cuts = keep_segments(before, {0: [(10, 40)]}, margin=0)
        self.assertEqual(silence_cut.summary(before, after, cuts), '1 sessiz yer kesilecek · 1:40 → 1:10 (30.0 sn kısalır)')
        self.assertIn('bulunamadı', silence_cut.summary(before, before, []))
        self.assertEqual(silence_cut.clock(3725), '1:02:05')


class ApplyTests(unittest.TestCase):
    """The segments go through the same apply_plan the AI edit uses: other tracks follow the cut."""

    def test_timeline_is_recut_and_a_text_clip_follows_its_material(self):
        video = Track('video', 'Video', [Clip('a.mp4', 0, 300, source_length=300)])
        text = Track('text', 'Yazı', [Clip('', 240, 30, text='son')])
        timeline = Timeline(tracks=[video, text])
        sources = [{'path': 'a.mp4', 'duration': 10.0}]
        segments, cuts = keep_segments(edit_plan.current_segments(timeline, sources), {0: [(2, 4)]}, margin=0)
        result = edit_plan.apply_plan(timeline, sources, {'segments': segments})
        clips = sorted(result.tracks[0].clips, key=lambda c: c.start)
        self.assertEqual([(c.start, c.length, c.source_in) for c in clips], [(0, 60, 0), (60, 180, 120)])
        self.assertEqual(result.tracks[1].clips[0].start, 180)       # 2 s earlier, still over the same picture
        self.assertEqual(len(timeline.tracks[0].clips), 1)           # the original is untouched


class DialogTests(unittest.TestCase):
    def dialog(self, levels, segments=None):
        sources = [{'path': 'a.mp4', 'duration': 6.0}]
        dialog = SilenceDialog(executable='ffmpeg', sources=sources,
                               segments=segments or [{'source': 0, 'start': 0, 'end': 6}],
                               measure=lambda executable, path: levels)
        self.addCleanup(dialog.deleteLater)
        dialog.worker.wait(5000)
        app.processEvents()
        return dialog

    def test_result_follows_the_sliders_without_measuring_again(self):
        levels = levels_from_pcm(pcm((2, 0.5), (2, 0), (2, 0.5)))
        dialog = self.dialog(levels)
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertEqual(len(dialog.cuts), 1)
        self.assertIn('1 sessiz yer', dialog.result.text())
        first = dialog.segments[0]['end']
        dialog.margin.setValue(0)
        self.assertLess(dialog.segments[0]['end'], first)             # no margin cuts closer to the speech
        dialog.min_silence.setValue(20)
        dialog.min_silence.setValue(dialog.min_silence.maximum())
        dialog.threshold.setValue(-60)
        self.assertEqual(len(dialog.cuts), 1)                        # digital silence is below any threshold
        removed = [r for r in dialog.strip.ranges() if r[2]]
        self.assertEqual(len(removed), 1)
        self.assertAlmostEqual(removed[0][0], 2 / 6, places=1)
        self.assertAlmostEqual(removed[0][1], 4 / 6, places=1)

    def test_nothing_to_cut_keeps_apply_disabled(self):
        dialog = self.dialog(levels_from_pcm(pcm((6, 0.5))))
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertIn('bulunamadı', dialog.result.text())

    def test_source_without_audio_says_so(self):
        dialog = self.dialog([])
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertIn('ses bulunamadı', dialog.result.text())


class WindowTests(unittest.TestCase):
    """The button in the main window: one undo step, nothing changes when the dialog is dismissed."""

    def setUp(self):
        from unittest.mock import patch
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=root / 'recovery').start()
        patch('main.MediaService.duration', return_value=10.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        video = root / 'a.mp4'
        video.touch()
        self.assertTrue(self.window.load_video(str(video)))
        self.patch = patch

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def lengths(self):
        return [c.length for t in self.window.multitrack.tracks if t.kind == 'video' for c in t.clips]

    def answer(self, accepted, silences):
        """A stand-in dialog that reports the cut for the given silences without measuring anything."""
        def make(parent=None, *, executable, sources, segments, language='tr'):
            new, cuts = keep_segments(segments, silences, margin=0)
            return type('Dialog', (), {'exec': lambda self: int(accepted), 'segments': new, 'cuts': cuts})()
        return self.patch('main.SilenceDialog', side_effect=make)

    def test_accepting_cuts_in_one_undo_step(self):
        before = self.lengths()
        with self.answer(True, {0: [(2, 4)]}):
            self.window.remove_silences()
        self.assertEqual(len(self.lengths()), 2)
        self.assertEqual(sum(self.lengths()), sum(before) - round(2 * self.window.multitrack.fps_num / self.window.multitrack.fps_den))
        self.assertIn('1 sessiz yer kesildi', self.window.status_label.text())
        self.assertTrue(self.window.undo())
        self.assertEqual(self.lengths(), before)

    def test_dismissing_or_nothing_to_cut_changes_nothing(self):
        before = self.lengths()
        for accepted, silences in ((False, {0: [(2, 4)]}), (True, {})):
            with self.answer(accepted, silences):
                self.window.remove_silences()
            self.assertEqual(self.lengths(), before)
        self.assertFalse(self.window.undo())


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class RealAudioTests(unittest.TestCase):
    def test_measured_file_gives_the_silence_that_was_put_in(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'talk.wav'
            graph = ('sine=frequency=300:duration=2,volume=0.5[a];anullsrc=r=44100:cl=mono,atrim=duration=1.5[b];'
                     'sine=frequency=300:duration=2,volume=0.5[c];[a][b][c]concat=n=3:v=0:a=1')
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-filter_complex', graph, str(path)], check=True)
            levels = silence_cut.measure(FFMPEG, path)
        self.assertAlmostEqual(len(levels) * silence_cut.WINDOW, 5.5, places=0)
        close(self, silent_spans(levels, -35, 0.5), [(2, 3.5)])


if __name__ == '__main__':
    unittest.main()
