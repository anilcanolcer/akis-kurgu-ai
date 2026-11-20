"""Local cuts (silence, filler, retake, speaker, beat) and the other tracks: a separate microphone recording
is cut with the picture, word captions lose the words that were cut, gaps the user left stay, and clips the
cut does not touch keep their exact length, slow ones included."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from akis import edit_plan, silence_cut
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

FFMPEG = shutil.which('ffmpeg')
FPS = 30


def local_cut(timeline, sources, spans, follow=(), **options):
    segments = edit_plan.current_segments(timeline, sources, keep=True)
    new, cuts = silence_cut.keep_segments(segments, spans, **options)
    assert cuts
    return edit_plan.apply_plan(timeline, sources, {'segments': new}, follow=follow)


class GapAndLengthTests(unittest.TestCase):
    def test_local_cut_preserves_fractional_clips_and_their_markers(self):
        for speed, length, phase in [(0.25, 1, 0), (0.5, 9, 0), (0.75, 7, 0.25), (1.5, 3, 0.5)]:
            with self.subTest(speed=speed):
                first = Clip('a', 3, length, source_in=4, style={'speed': speed, 'source_phase': phase})
                following = Clip('b', first.end + 11, 90)
                markers = [{'frame': i} for i in range(following.start + 1)]
                timeline = Timeline(30000, 1001, [Track('video', 'V', [first, following])], markers)
                sources = [{'path': name, 'duration': 10} for name in ('a', 'b')]
                result = local_cut(timeline, sources, {1: [(1, 2)]}, margin=0)
                kept = result.tracks[0].clips[0]
                self.assertEqual((kept.start, kept.length, kept.source_phase), (3, length, phase))
                self.assertEqual(result.markers, markers)

    def test_gaps_on_both_sides_of_removed_clip_stay(self):
        clips = [Clip('a', 0, 30), Clip('b', 40, 30), Clip('c', 80, 30)]
        timeline = Timeline(tracks=[Track('video', 'V', clips)], markers=[{'frame': 75}])
        sources = [{'path': name, 'duration': 1} for name in ('a', 'b', 'c')]
        result = local_cut(timeline, sources, {1: [(0, 1)]}, whole=True, margin=0)
        self.assertEqual([c.start for c in result.tracks[0].clips], [0, 50])
        self.assertEqual(result.markers, [{'frame': 45}])

    def test_a_gap_left_between_clips_stays(self):
        timeline = Timeline(fps_num=FPS, tracks=[Track('video', 'Video', [
            Clip('a.mp4', 0, 75, source_length=300), Clip('b.mp4', 135, 75, source_length=300)])],
            markers=[{'frame': 100, 'label': 'boşlukta'}])
        sources = [{'path': 'a.mp4', 'duration': 10.0}, {'path': 'b.mp4', 'duration': 10.0}]
        result = local_cut(timeline, sources, {1: [(1.0, 2.0)]}, margin=0)
        main = edit_plan.primary_track(result)
        self.assertEqual([(c.source, c.start, c.length) for c in main.clips],
                         [('a.mp4', 0, 75), ('b.mp4', 135, 30), ('b.mp4', 165, 15)])
        self.assertEqual(result.markers[0]['frame'], 100)          # a marker in the gap stays in it

    def test_a_leading_gap_stays(self):
        timeline = Timeline(fps_num=FPS, tracks=[Track('video', 'Video', [Clip('a.mp4', 60, 90, source_length=300)])])
        result = local_cut(timeline, [{'path': 'a.mp4', 'duration': 10.0}], {0: [(1.0, 2.0)]}, margin=0)
        self.assertEqual([(c.start, c.length) for c in edit_plan.primary_track(result).clips], [(60, 30), (90, 30)])

    def test_untouched_slow_clips_keep_every_frame(self):
        clips, cursor = [], 0
        for number in range(30):
            length = 9 if number % 2 else 7        # odd lengths: half source frames at 0.5×
            clips.append(Clip('slow.mp4', cursor, length, source_in=number * 10, source_length=600,
                              style={'speed': 0.5}))
            cursor += length
        clips.append(Clip('b.mp4', cursor, 90, source_length=300))
        timeline = Timeline(fps_num=FPS, tracks=[Track('video', 'Video', clips)])
        sources = [{'path': 'slow.mp4', 'duration': 20.0}, {'path': 'b.mp4', 'duration': 10.0}]
        result = local_cut(timeline, sources, {1: [(1.0, 2.0)]}, margin=0)
        main = edit_plan.primary_track(result).clips
        self.assertEqual([(c.start, c.length, c.source_in, c.speed) for c in main[:30]],
                         [(c.start, c.length, c.source_in, c.speed) for c in clips[:30]])
        self.assertEqual(main[30].start, cursor)


class WordCaptionTests(unittest.TestCase):
    def test_a_word_cut_from_the_middle_leaves_the_caption(self):
        words = [[0, 30, 'bir'], [30, 60, 'iki'], [60, 90, 'üç']]
        timeline = Timeline(fps_num=FPS, tracks=[
            Track('video', 'Video', [Clip('a.mp4', 0, 90, source_length=300)]),
            Track('text', 'Altyazı / Captions', [Clip('', 0, 90, text='bir iki üç', style={'words': words})])])
        result = local_cut(timeline, [{'path': 'a.mp4', 'duration': 10.0}], {0: [(1.0, 2.0)]}, margin=0)
        caption = result.tracks[1].clips[0]
        self.assertEqual((caption.start, caption.length), (0, 60))
        self.assertEqual(caption.style['words'], [[0, 30, 'bir'], [30, 60, 'üç']])
        self.assertEqual(caption.text, 'bir üç')


def make(path, pattern, colour='blue', hertz=880, seconds=5, video=True):
    """A file whose tone sounds at the (start, end) seconds in `pattern` and is silent elsewhere."""
    volume = '+'.join(f'between(t,{a},{b})' for a, b in pattern) or '0'
    sound = ['-f', 'lavfi', '-i', f'sine=f={hertz}:d={seconds}:sample_rate=48000', '-af', f"volume='{volume}':eval=frame"]
    if video:
        command = ['-f', 'lavfi', '-i', f'color=c={colour}:size=96x64:rate={FPS}:d={seconds}', *sound,
                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest']
    else:
        command = [*sound, '-c:a', 'pcm_s16le']
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', *command, str(path)], check=True)
    return str(path)


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class MicrophoneTrackTests(unittest.TestCase):
    PATTERN = [(0, 1.5), (2.5, 5)]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.video = make(self.dir / 'scene.mp4', self.PATTERN)
        self.mic = make(self.dir / 'mic.wav', self.PATTERN, video=False)
        self.music = make(self.dir / 'music.wav', [(1.2, 2.8)], hertz=330, video=False)

    def tearDown(self):
        self.tmp.cleanup()

    def timeline(self, sound):
        return Timeline(fps_num=FPS, tracks=[
            Track('video', 'Video', [Clip(self.video, 0, 150, source_length=150, volume=0.0)]),   # only the mic is heard
            Track('audio', 'Ses', [Clip(sound, 0, 150, source_length=150)])])

    def levels(self, source):
        return silence_cut.measure(FFMPEG, source)

    def test_the_microphone_is_recognised_and_music_is_not(self):
        mic_timeline, music_timeline = self.timeline(self.mic), self.timeline(self.music)
        self.assertEqual(edit_plan.synced_sound(mic_timeline, self.levels), {mic_timeline.tracks[1].clips[0].id})
        self.assertEqual(edit_plan.synced_sound(music_timeline, self.levels), set())

    def test_the_microphone_stays_with_the_picture_after_a_silence_cut(self):
        timeline = self.timeline(self.mic)
        sources = [{'path': self.video, 'duration': 5.0}]
        follow = edit_plan.synced_sound(timeline, self.levels)
        result = local_cut(timeline, sources, {0: [(1.5, 2.5)]}, follow=follow, margin=0)
        mic = result.tracks[1].clips
        self.assertEqual([(c.start, c.length, c.source_in) for c in mic], [(0, 45, 0), (45, 75, 75)])
        output = self.dir / 'out.mp4'
        TimelineRenderer(MediaService(FFMPEG), (96, 64)).export(result, output)
        levels = silence_cut.measure(FFMPEG, output)
        heard = lambda a, b: max(levels[int(a / silence_cut.WINDOW):int(b / silence_cut.WINDOW)])
        self.assertGreater(heard(0.2, 1.3), -30)
        self.assertGreater(heard(1.7, 3.8), -30)           # the mic's second sentence, under its own picture

    def test_music_stays_a_bed(self):
        timeline = self.timeline(self.music)
        result = local_cut(timeline, [{'path': self.video, 'duration': 5.0}], {0: [(1.5, 2.5)]},
                           follow=edit_plan.synced_sound(timeline, self.levels), margin=0)
        self.assertEqual([(c.start, c.length, c.source_in) for c in result.tracks[1].clips], [(0, 120, 0)])


if __name__ == '__main__':
    unittest.main()
