"""Fixes from the 20 November 2026 audit: long project names, the versions folder, trimmed word captions,
relinking same-named takes, previews of a replaced source and frame timing of sped-up clips."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path

from akis import project_service
from akis.timeline_model import Clip, Timeline, Track


def document():
    return project_service.make_document({}, Timeline.from_legacy({}), {}, '')


class LongNameSaveTests(unittest.TestCase):
    def test_a_project_name_windows_accepts_can_be_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ('p' * (245 - len('.akis.json')) + '.akis.json')
            self.assertEqual(len(target.name), 245)
            try:
                target.write_text('eski', encoding='utf-8')     # Windows itself accepts the name
            except OSError:
                self.skipTest('this system does not accept the long path')
            project_service.save(target, document())
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['format'], 'akis-kurgu-project')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), [target.name])  # no temporary file left


class VersionsFolderTests(unittest.TestCase):
    def test_pruning_deletes_only_the_apps_own_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'p.akis.json'
            folder = project_service.versions_folder(project)
            folder.mkdir()
            note = folder / '000-notes.json'
            note.write_text('{"not": "a version"}', encoding='utf-8')
            for second in range(25):
                (folder / f'20261120-0915{second:02d}-000000.json').write_text('{}', encoding='utf-8')
            removed = project_service.prune_versions(project, keep=20)
            self.assertEqual(len(removed), 5)
            self.assertTrue(note.is_file())
            kept = sorted(p.name for p in folder.glob('2026*.json'))
            self.assertEqual(kept[0], '20261120-091505-000000.json')   # the oldest five went

    def test_saving_twenty_versions_keeps_a_note_in_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'p.akis.json'
            project_service.save_with_snapshot(project, document(), snapshot=True)
            note = project_service.versions_folder(project) / '000-notes.json'
            note.write_text('{}', encoding='utf-8')
            for _ in range(21):
                project_service.save_with_snapshot(project, document(), snapshot=True)
            self.assertTrue(note.is_file())


import shutil
from PIL import Image, ImageChops

FFMPEG = shutil.which('ffmpeg')
FONT = Path(r'C:\Windows\Fonts\arial.ttf')


def differing_pixels(a, b, limit=24):
    """Pixels where any colour channel differs by more than `limit`."""
    red, green, blue = ImageChops.difference(Image.open(a).convert('RGB'), Image.open(b).convert('RGB')).split()
    largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return largest.point(lambda value: 255 if value > limit else 0).histogram()[255]


class TrimmedWordCaptionTests(unittest.TestCase):
    WORDS = [[0, 10, 'bir'], [10, 20, 'iki'], [20, 30, 'üç']]

    def caption(self, words, length):
        clip = Clip('', 0, 30, text=' '.join(w[2] for w in words), style={'words': [list(w) for w in words], 'look': 'vurgu'})
        track = Track('text', 'Altyazı / Captions', [clip])
        if length != 30:
            track.trim_end(clip.id, length)
        return Timeline(fps_num=10, tracks=[track]), clip

    def test_only_the_words_inside_the_clip_are_drawn(self):
        from akis import word_captions
        _, clip = self.caption(self.WORDS, 10)
        self.assertEqual(word_captions.visible(clip, 0), ([[0, 10, 'bir']], 0))
        self.assertEqual(word_captions.visible(clip, 2), ([[0, 10, 'bir']], None))

    @unittest.skipUnless(FFMPEG and FONT.is_file(), 'ffmpeg ve Arial gerekli')
    def test_the_last_frame_after_a_trim_shows_only_the_kept_word(self):
        from akis.media_service import MediaService
        from akis.timeline_render import TimelineRenderer
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            renderer = TimelineRenderer(MediaService(FFMPEG), (320, 180), font=str(FONT))
            trimmed, clip = self.caption(self.WORDS, 10)
            control, _ = self.caption(self.WORDS[:1], 10)
            renderer.preview(trimmed, 9, root / 'trimmed.png')
            renderer.preview(control, 9, root / 'control.png')
            self.assertEqual(differing_pixels(root / 'trimmed.png', root / 'control.png'), 0)
            # Lengthened again, the trimmed words come back at their own times.
            trimmed.tracks[0].trim_end(clip.id, 30)
            self.assertEqual(clip.style['words'], self.WORDS)
            full, _ = self.caption(self.WORDS, 30)
            renderer.preview(trimmed, 25, root / 'again.png')
            renderer.preview(full, 25, root / 'full.png')
            self.assertEqual(differing_pixels(root / 'again.png', root / 'full.png'), 0)
            self.assertGreater(differing_pixels(root / 'again.png', root / 'control.png'), 100)


import struct
import subprocess
from unittest.mock import patch


def make_take(path, colour, hertz, seconds=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f'color=c={colour}:size=160x90:rate=30:d={seconds}',
                    '-f', 'lavfi', '-i', f'sine=f={hertz}:d={seconds}:sample_rate=48000', '-c:v', 'libx264', '-pix_fmt',
                    'yuv420p', '-c:a', 'aac', '-shortest', str(path)], check=True)


def colour_and_pitch(path, at):
    """(average (r, g, b), dominant pitch in Hz) of the half second of `path` starting at `at` seconds."""
    raw = subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{at}', '-i', str(path), '-frames:v', '1',
                          '-vf', 'crop=16:16,scale=1:1',          # the middle of the picture, not the bars around it
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    pcm = subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{at}', '-t', '0.5', '-i', str(path), '-vn', '-ac', '1', '-ar',
                          '48000', '-f', 's16le', '-'], capture_output=True, check=True).stdout
    samples = struct.unpack(f'<{len(pcm) // 2}h', pcm)
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b)
    return tuple(raw[:3]), crossings / (len(samples) / 48000)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class SameNamedTakesTests(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shoot = self.root / 'Cekim'
        make_take(shoot / 'A' / 'take.mp4', 'red', 440)
        make_take(shoot / 'B' / 'take.mp4', 'blue', 880)
        self.project = self.root / 'proje.akis.json'
        self.window, stop = self.open_window('pc1')
        w = self.window
        self.assertTrue(w.load_video(str(shoot / 'A' / 'take.mp4')))
        self.assertTrue(w._import_media_path(str(shoot / 'B' / 'take.mp4')))
        w.write_project(str(self.project))
        stop()
        w._close_confirmed = True
        w.close()

    def open_window(self, data):
        from main import MainWindow
        patcher = patch('akis.app_support.app_data_dir', return_value=self.root / data)
        patcher.start()
        self.addCleanup(patch.stopall)
        window = MainWindow()
        self.addCleanup(lambda: (setattr(window, '_close_confirmed', True), window.close()))
        return window, patcher.stop

    def reopen(self, chosen):
        from PySide6.QtWidgets import QMessageBox
        window, _ = self.open_window('pc2')
        window.show()
        with patch('PySide6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
             patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', side_effect=chosen) as chooser, \
             patch('PySide6.QtWidgets.QMessageBox.warning') as warning:
            self.assertTrue(window.open_project_file(str(self.project)))
        return window, chooser, warning

    def export_halves(self, window):
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtTest import QTest
        out = self.root / 'cikti.mp4'
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(out), '')), \
             patch('PySide6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.No), \
             patch('PySide6.QtWidgets.QMessageBox.information'):
            window.export_video()
            while window._workers:
                QTest.qWait(50)
        return [colour_and_pitch(out, at) for at in (0.5, 2.5)]

    def assert_red_then_blue(self, halves):
        (first, low), (second, high) = halves
        self.assertGreater(first[0], 180); self.assertLess(first[2], 80)      # red
        self.assertGreater(second[2], 180); self.assertLess(second[0], 80)    # blue
        self.assertAlmostEqual(low, 440, delta=25)
        self.assertAlmostEqual(high, 880, delta=40)

    def test_the_other_take_follows_its_own_subfolder(self):
        moved = self.root / 'Tasindi' / 'Cekim'
        (self.root / 'Tasindi').mkdir()
        (self.root / 'Cekim').rename(moved)
        window, chooser, warning = self.reopen([(str(moved / 'A' / 'take.mp4'), '')] * 3)
        self.assertEqual(chooser.call_count, 1)
        warning.assert_not_called()
        sources = sorted(os.path.normcase(c.source) for t in window.multitrack.tracks for c in t.clips if c.source)
        self.assertEqual(sources, sorted(os.path.normcase(str(moved / n / 'take.mp4')) for n in 'AB'))
        self.assert_red_then_blue(self.export_halves(window))

    def test_a_take_that_cannot_be_told_apart_is_asked_about_on_its_own(self):
        (self.root / 'A-yeni').mkdir()
        (self.root / 'Cekim' / 'A' / 'take.mp4').rename(self.root / 'A-yeni' / 'take.mp4')
        (self.root / 'B-yeni').mkdir()
        (self.root / 'Cekim' / 'B' / 'take.mp4').rename(self.root / 'B-yeni' / 'take.mp4')
        window, chooser, warning = self.reopen([(str(self.root / 'A-yeni' / 'take.mp4'), ''),
                                                (str(self.root / 'B-yeni' / 'take.mp4'), '')])
        self.assertEqual(chooser.call_count, 2)              # B was not quietly given A's file
        warning.assert_not_called()
        self.assert_red_then_blue(self.export_halves(window))


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class ReplacedSourcePreviewTests(unittest.TestCase):
    def test_a_file_replaced_at_the_same_path_is_drawn_again(self):
        import time
        from akis.media_service import MediaService
        from akis.preview_widget import timeline_signature
        from akis.timeline_render import TimelineRenderer
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'cekim.mp4'
            make_take(source, 'red', 440)
            timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(source), 0, 60, source_length=60)])])
            renderer = TimelineRenderer(MediaService(FFMPEG), (160, 90), fast=True)
            pieces = root / 'pieces'
            before = timeline_signature(timeline, (160, 90), {})
            renderer.export_pieces(timeline, root / 'once.mp4', pieces)
            self.assertEqual(colour_and_pitch(root / 'once.mp4', 0.5)[0][0] > 180, True)   # red

            time.sleep(0.05)                       # a later modification time, as a real replacement has
            replacement = root / 'baska.mp4'
            make_take(replacement, 'blue', 880)
            os.replace(replacement, source)        # the same name, size class and resolution
            self.assertNotEqual(timeline_signature(timeline, (160, 90), {}), before)
            _, drawn, reused = renderer.export_pieces(timeline, root / 'again.mp4', pieces)
            self.assertEqual((drawn > 0, reused), (True, 0))
            (red, green, blue), pitch = colour_and_pitch(root / 'again.mp4', 0.5)
            self.assertGreater(blue, 180)
            self.assertLess(red, 80)
            self.assertAlmostEqual(pitch, 880, delta=40)


class SourcePhaseModelTests(unittest.TestCase):
    def test_splitting_a_fractional_speed_clip_keeps_every_source_frame(self):
        for speed in (0.25, 0.5, 0.75, 1.25, 1.5, 2.0, 3.0):
            clip = Clip('a.mp4', 0, 24, source_in=6, source_length=200, style={'speed': speed})
            track = Track('video', 'Video', [clip])
            whole = [clip.source_frame(n) for n in range(24)]
            for point in (5, 9, 13):
                current = next(c for c in track.clips if c.start < point < c.end)
                track.split(current.id, point)
            parts = [next(c for c in track.clips if c.start <= n < c.end).source_frame(n) for n in range(24)]
            self.assertEqual(parts, whole, speed)
            self.assertEqual(sum(c.source_frames for c in track.clips), Clip('a.mp4', 0, 24, style={'speed': speed}).source_frames)

    def test_slicing_and_trimming_keep_the_phase(self):
        from akis.timeline_slice import slice_timeline
        clip = Clip('a.mp4', 0, 24, source_in=6, source_length=200, style={'speed': 1.5})
        timeline = Timeline(tracks=[Track('video', 'Video', [clip])])
        part = slice_timeline(timeline, 9, 24).tracks[0].clips[0]
        self.assertEqual([part.source_frame(n) for n in range(15)], [clip.source_frame(n) for n in range(9, 24)])
        timeline.tracks[0].trim_start(clip.id, 9)
        self.assertEqual((clip.source_in, clip.source_phase), (19, 0.5))
        self.assertEqual(clip.source_frame(10), 21)

    def test_whole_speeds_and_old_projects_have_no_phase(self):
        clip = Clip('a.mp4', 0, 24, source_in=6, source_length=200)
        track = Track('video', 'Video', [clip])
        right = track.split(clip.id, 9)
        self.assertNotIn('source_phase', right.style)
        old = Timeline.from_dict({'tracks': [{'kind': 'video', 'name': 'Video', 'clips': [
            {'source': 'a.mp4', 'start': 0, 'length': 30, 'source_in': 3, 'style': {'speed': 1.5}}]}]})
        self.assertEqual(old.tracks[0].clips[0].source_phase, 0.0)        # a project saved before 0.6.9
        self.assertEqual(old.tracks[0].clips[0].source_frame(3), 7)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class SpeedFrameTests(unittest.TestCase):
    """Export, still preview and a split export all show the source frame Clip.source_frame names."""

    @classmethod
    def setUpClass(cls):
        from akis.media_service import MediaService
        from akis.timeline_render import TimelineRenderer
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.ramps = {}
        for rate in (30, 60, 24):     # brightness 4 × (the 30 fps frame the picture belongs to)
            path = cls.root / f'ramp{rate}.mp4'
            subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            f"color=c=black:size=64x64:rate={rate}:d=2.2,format=gray,geq=lum='4*floor(T*30+0.0001)'",
                            '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv444p', '-g', '1', str(path)], check=True)
            cls.ramps[rate] = path
        cls.renderer = TimelineRenderer(MediaService(FFMPEG), (64, 64))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def levels(self, path, count):
        raw = subprocess.run([FFMPEG, '-v', 'error', '-i', str(path), '-vf', 'crop=8:8,scale=1:1,format=gray',
                              '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
        return [round(b / 4) for b in raw[:count]]

    def timeline(self, rate, speed, cuts=()):
        clip = Clip(str(self.ramps[rate]), 0, 24, source_in=6, source_length=66, style={'speed': speed} if speed != 1 else {})
        timeline = Timeline(fps_num=30, tracks=[Track('video', 'Video', [clip])])
        for point in cuts:
            current = next(c for c in timeline.tracks[0].clips if c.start < point < c.end)
            timeline.tracks[0].split(current.id, point)
        return timeline

    def export(self, timeline):
        out = self.root / 'out.mp4'
        self.renderer.export(timeline, out)
        return self.levels(out, 24)

    def still(self, timeline, frame):
        out = self.root / 'still.png'
        self.renderer.preview(timeline, frame, out)
        return self.levels(out, 1)[0]

    def test_export_still_and_split_agree_with_the_model(self):
        for speed in (0.5, 1.5, 2.0):
            timeline = self.timeline(30, speed)
            clip = timeline.tracks[0].clips[0]
            model = [clip.source_frame(n) for n in range(24)]
            self.assertEqual(self.export(timeline), model, speed)
            for frame in (0, 1, 5, 9, 10, 15, 22):
                self.assertEqual(self.still(timeline, frame), model[frame], (speed, frame))
            self.assertEqual(self.export(self.timeline(30, speed, (9,))), model, speed)

    def test_sources_at_other_frame_rates_are_not_changed_by_a_split(self):
        for rate, speed in ((60, 1.0), (60, 2.0), (24, 1.0), (24, 1.5)):
            whole = self.export(self.timeline(rate, speed))
            self.assertEqual(self.export(self.timeline(rate, speed, (5, 9, 13))), whole, (rate, speed))
        model = [c.source_frame(n) for c in self.timeline(60, 1.0).tracks[0].clips for n in range(24)]
        self.assertEqual(self.export(self.timeline(60, 1.0)), model)   # 60 fps: the frame at each grid moment


if __name__ == '__main__':
    unittest.main()
