"""Fixes from the 20 November 2026 tools audit: silence, filler, retake and speaker cuts keep every clip's
own sound, speed and markers; Shorts of an edit with gaps or cut inside a transition match the full export;
a silent recording has no highlights; beats of sped-up music land where they are heard."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from akis import beat_sync, edit_plan, highlights, silence_cut
from akis.media_service import MediaService
from akis.shorts_split import ShortsExportWorker
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer
from akis.timeline_slice import slice_timeline

FFMPEG = shutil.which('ffmpeg')
FPS = 30


def make(path, colour='gray', tone=None, seconds=3):
    """A small test video; tone: [(start, end)] seconds where a 440 Hz tone sounds, silence elsewhere."""
    volume = '+'.join(f'between(t,{a},{b})' for a, b in tone) if tone else '0'
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f'color=c={colour}:size=96x64:rate={FPS}:d={seconds}',
                    '-f', 'lavfi', '-i', f'sine=f=440:d={seconds}:sample_rate=48000', '-af', f"volume='{volume}':eval=frame",
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path)], check=True)
    return str(path)


def loudness(path, start, end):
    """Loudest 20 ms level (dBFS) of `path` between two moments."""
    levels = silence_cut.measure(FFMPEG, path)
    return max(levels[int(start / silence_cut.WINDOW):int(end / silence_cut.WINDOW)], default=silence_cut.FLOOR_DB)


def colour_at(path, frame):
    raw = subprocess.run([FFMPEG, '-v', 'error', '-i', str(path), '-vf', f'select=eq(n\\,{frame}),crop=8:8,scale=1:1',
                          '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    return tuple(raw[:3])


def seconds_of(path):
    return MediaService(FFMPEG).duration(path)


def sources_of(timeline):
    media = MediaService(FFMPEG)
    paths = []
    for clip in edit_plan.primary_track(timeline).clips:
        if clip.source not in paths:
            paths.append(clip.source)
    return [{'path': path, 'duration': media.duration(path)} for path in paths]


class LocalCutSegmentTests(unittest.TestCase):
    """The pure part: no media needed."""

    def test_pieces_keep_their_clip_and_speed(self):
        segments = [{'source': 0, 'start': 0.0, 'end': 6.0, 'clip': 'a', 'speed': 2.0}]
        new, cuts = silence_cut.keep_segments(segments, {0: [(2.0, 3.0)]}, margin=0)
        self.assertEqual(new, [{'source': 0, 'start': 0.0, 'end': 2.0, 'clip': 'a', 'speed': 2.0},
                               {'source': 0, 'start': 3.0, 'end': 6.0, 'clip': 'a', 'speed': 2.0}])
        self.assertEqual(cuts, [(0, 2.0, 3.0)])
        self.assertEqual(silence_cut.duration(new), 2.5)       # heard seconds, not source seconds

    def test_a_speaker_filling_a_whole_clip_removes_that_clip(self):
        segments = [{'source': 0, 'start': 0.0, 'end': 3.0}, {'source': 0, 'start': 5.0, 'end': 8.0}]
        spans = {0: [(0.0, 3.0), (6.0, 7.0)]}
        kept, _ = silence_cut.keep_segments(segments, spans, margin=0, min_keep=0.3)
        self.assertEqual(kept[0], segments[0])                  # silence cut: never empties a clip
        new, cuts = silence_cut.keep_segments(segments, spans, margin=0, min_keep=0.3, whole=True)
        self.assertEqual([(s['start'], s['end']) for s in new], [(5.0, 6.0), (7.0, 8.0)])
        self.assertIn((0, 0.0, 3.0), cuts)

    def test_beats_of_sped_up_music_are_where_they_are_heard(self):
        music = Clip('m.mp3', 30, 300, style={'speed': 1.5})
        # A beat 3.15 s into the music's source is heard 2.10 s after the clip starts.
        self.assertAlmostEqual(beat_sync.timeline_beats([3.15], music, FPS)[0], 1 + 2.10)

    def test_snapping_a_sped_up_clip_counts_heard_seconds(self):
        segments = [{'source': 0, 'start': 0.0, 'end': 4.0, 'speed': 2.0}, {'source': 1, 'start': 0.0, 'end': 2.0}]
        new, moved = beat_sync.snap_segments(segments, [2.2], {0: 10.0, 1: 10.0})
        self.assertEqual(moved, 1)
        self.assertAlmostEqual(new[0]['end'], 4.4)              # 0.2 heard seconds = 0.4 s of 2× source

    def test_a_silent_recording_has_no_highlights(self):
        self.assertEqual(highlights.score([silence_cut.FLOOR_DB] * int(65 / highlights.WINDOW), 45), [])

    def test_speech_still_scores_above_room_tone(self):
        quiet, talk = [-70.0] * 1500, [-20.0] * 1500
        found = highlights.score(quiet + talk + quiet, 30)
        best = max(found, key=lambda item: item[1])
        self.assertGreaterEqual(best[0], 20)                    # the talking stretch, not the quiet one
        self.assertEqual(min(item[2]['speech'] for item in found), 0.0)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class SilenceCutKeepsClipsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cut(self, timeline, spans, **options):
        sources = sources_of(timeline)
        segments = edit_plan.current_segments(timeline, sources, keep=True)
        index = {source['path']: i for i, source in enumerate(sources)}
        new, cuts = silence_cut.keep_segments(segments, {index[path]: found for path, found in spans.items()}, **options)
        self.assertTrue(cuts)
        return edit_plan.apply_plan(timeline, sources, {'segments': new})

    def test_a_muted_second_use_stays_muted_and_keeps_its_marker(self):
        take = make(self.dir / 'take.mp4', 'red', tone=[(0, 3)])
        later = make(self.dir / 'later.mp4', 'blue', tone=[(0, 1), (2, 3)])
        timeline = Timeline(fps_num=FPS, tracks=[Track('video', 'Video', [
            Clip(take, 0, 30, source_length=90), Clip(take, 30, 30, source_length=90, volume=0.0),
            Clip(later, 60, 90, source_length=90)])], markers=[{'frame': 45, 'label': 'ikinci çekim'}])
        result = self.cut(timeline, {later: [(1.0, 2.0)]}, margin=0)
        main = edit_plan.primary_track(result)
        self.assertEqual([(c.start, c.length, c.volume) for c in main.clips[:2]], [(0, 30, 1.0), (30, 30, 0.0)])
        self.assertEqual(result.markers, [{'frame': 45, 'label': 'ikinci çekim'}])
        output = self.dir / 'out.mp4'
        TimelineRenderer(MediaService(FFMPEG), (96, 64)).export(result, output)
        self.assertGreater(loudness(output, 0.2, 0.8), -30)      # the first use is heard
        self.assertLess(loudness(output, 1.1, 1.9), -60)         # the muted second use is not

    def test_a_2x_clip_stays_2x_after_its_silence_is_cut(self):
        take = make(self.dir / 'take.mp4', 'red', tone=[(0, 2), (3, 6)], seconds=6)
        timeline = Timeline(fps_num=FPS, tracks=[Track('video', 'Video', [
            Clip(take, 0, 90, source_length=180, style={'speed': 2.0})])])
        result = self.cut(timeline, {take: [(2.0, 3.0)]}, margin=0)
        main = edit_plan.primary_track(result)
        self.assertEqual([(c.length, c.speed) for c in main.clips], [(30, 2.0), (45, 2.0)])
        output = self.dir / 'out.mp4'
        TimelineRenderer(MediaService(FFMPEG), (96, 64)).export(result, output)
        self.assertAlmostEqual(seconds_of(output), 2.5, delta=0.1)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class ShortsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_edit_with_gaps_makes_every_part_at_its_planned_length(self):
        first = make(self.dir / 'first.mp4', 'red', tone=[(0, 3)])
        last = make(self.dir / 'last.mp4', 'blue', tone=[(0, 3)])
        timeline = Timeline(fps_num=FPS, tracks=[Track('video', 'Video', [
            Clip(first, 0, 90, source_length=90), Clip(last, 42 * FPS, 90, source_length=90)])])
        outputs = [str(self.dir / f'{n}.mp4') for n in (1, 2, 3)]
        worker = ShortsExportWorker(timeline, [(0, 15), (15, 30), (30, 45)], outputs, FFMPEG, canvas=(64, 96))
        failures = []
        worker.failed.connect(failures.append)
        worker.run()
        self.assertEqual(failures, [])
        self.assertEqual([round(seconds_of(path)) for path in outputs], [15, 15, 15])
        self.assertGreater(colour_at(outputs[2], 13 * FPS)[2], 150)   # the last take reached the last part

    def test_a_part_starting_inside_a_transition_continues_it(self):
        red = make(self.dir / 'red.mp4', 'red', seconds=2)
        blue = make(self.dir / 'blue.mp4', 'blue', seconds=2)
        timeline = Timeline(fps_num=FPS, tracks=[Track('video', 'Video', [
            Clip(red, 0, 60, source_length=60),
            Clip(blue, 60, 60, source_length=60, style={'transition': 'fade', 'transition_frames': 10})])])
        renderer = TimelineRenderer(MediaService(FFMPEG), (96, 64))
        whole, first, second = (self.dir / name for name in ('whole.mp4', 'first.mp4', 'second.mp4'))
        renderer.export(timeline, whole)
        renderer.export(slice_timeline(timeline, 0, 65), first)
        renderer.export(slice_timeline(timeline, 65, 120), second)
        middle = colour_at(whole, 65)
        self.assertGreater(min(middle[0], middle[2]), 60)              # the full export is mid-fade there
        for part, frame, at in ((second, 0, 65), (second, 3, 68), (first, 64, 64), (second, 10, 75)):
            got, want = colour_at(part, frame), colour_at(whole, at)
            self.assertTrue(all(abs(a - b) <= 12 for a, b in zip(got, want)), (part.name, frame, got, want))


if __name__ == '__main__':
    unittest.main()
