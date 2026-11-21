"""Fixes from the 21 November 2026 project-wide audit (scripts/media-audit/fuzz.py and render_fuzz.py):
word captions cut after a word was said, a caption's start dragged in and out, transitions of clips that
are split or trimmed, the opening clip's transition in a local cut, captions of a faster clip, and the
exported frames of a sped-up clip at 25 fps."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import tempfile
import unittest
from pathlib import Path

from akis import edit_plan, silence_cut, timeline_service, word_captions
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track, cut_words
from akis.timeline_render import TimelineRenderer, transition_of
from akis.timeline_slice import slice_timeline

FFMPEG = shutil.which('ffmpeg')
WORDS = [[0, 5, 'bir'], [5, 10, 'iki'], [10, 15, 'üç']]


def caption(start=0, length=30, words=WORDS):
    return Clip('', start, length, text=' '.join(w[2] for w in words), style={'words': [list(w) for w in words]})


def lit(clip, offset):
    for a, b, index in word_captions.states(clip):
        if a <= offset < b:
            return None if index is None else clip.style['words'][index][2]


class WordCaptionTests(unittest.TestCase):
    def test_a_part_after_the_last_word_keeps_it_lit(self):
        # The last word stays lit to the end of the caption; a part cut from that silent tail showed the
        # whole sentence as plain text, because its word list came out empty.
        style = cut_words({'words': WORDS}, 20, 10)
        self.assertEqual(style['words'], [[0, 1, 'üç']])

    def test_split_delete_and_slice_keep_the_word_being_said(self):
        for make_part in (lambda t: (t.tracks[0].split(t.tracks[0].clips[0].id, 22), t.tracks[0].clips[1])[1],
                          lambda t: (timeline_service.delete_range(t, 18, 22), t.tracks[0].clips[1])[1],
                          lambda t: slice_timeline(t, 22, 30).tracks[0].clips[0]):
            timeline = Timeline(tracks=[Track('text', 'Altyazı / Captions', [caption()])])
            part = make_part(timeline)
            self.assertTrue(part.style['words'])
            self.assertEqual(lit(part, 0), 'üç')

    def test_dragging_the_start_in_and_back_out_keeps_the_words(self):
        track = Track('text', 'Altyazı / Captions', [caption()])
        clip = track.clips[0]
        track.trim_start(clip.id, 7)
        self.assertEqual([w[2] for w in word_captions.visible(clip)[0]], ['iki', 'üç'])
        self.assertEqual(lit(clip, 0), 'iki')
        track.trim_start(clip.id, 0)
        self.assertEqual(clip.style['words'], WORDS)
        self.assertEqual(lit(clip, 0), 'bir')

    def test_a_local_cut_ignores_words_trimmed_off_the_start(self):
        timeline = Timeline(tracks=[Track('video', 'Video', [Clip('a.mp4', 0, 90, source_length=300)]),
                                    Track('text', 'Altyazı / Captions', [caption(0, 30)])])
        timeline.tracks[1].trim_start(timeline.tracks[1].clips[0].id, 7)
        segments = edit_plan.current_segments(timeline, [{'path': 'a.mp4', 'duration': 10.0}], keep=True)
        new, _ = silence_cut.keep_segments(segments, {0: [(2.0, 2.5)]}, margin=0)
        result = edit_plan.apply_plan(timeline, [{'path': 'a.mp4', 'duration': 10.0}], {'segments': new})
        words = result.tracks[1].clips[0].style['words']
        self.assertEqual([w[2] for w in words], ['iki', 'üç'])
        self.assertTrue(all(0 <= a < b for a, b, _ in words))

    def test_a_faster_clip_never_gives_a_caption_word_no_length(self):
        words = [[i, i + 1, f'k{i}'] for i in range(12)]
        timeline = Timeline(tracks=[Track('video', 'Video', [Clip('a.mp4', 0, 12, source_length=300)]),
                                    Track('text', timeline_service.CAPTION_TRACK, [caption(0, 12, words)])])
        timeline_service.set_clip_speed(timeline, (0, timeline.tracks[0].clips[0].id), 4.0)
        self.assertTrue(all(b > a for a, b, _ in timeline.tracks[1].clips[0].style['words']))


class TransitionTests(unittest.TestCase):
    def clip(self, length=30, frames=10):
        return Clip('a.mp4', 0, length, source_length=300, style={'transition': 'fade', 'transition_frames': frames})

    def test_splitting_or_trimming_after_the_transition_keeps_its_length(self):
        for edit in (lambda track, clip: track.split(clip.id, 12), lambda track, clip: track.trim_end(clip.id, 12)):
            track = Track('video', 'Video', [self.clip()])
            clip = track.clips[0]
            self.assertEqual(transition_of(track, clip), ('fade', 10))
            edit(track, clip)
            self.assertEqual(transition_of(track, clip), ('fade', 10))        # was cut to 6 (half of 12)

    def test_splitting_inside_the_transition_keeps_its_speed(self):
        track = Track('video', 'Video', [self.clip()])
        clip = track.clips[0]
        track.split(clip.id, 4)
        self.assertEqual(transition_of(track, clip), ('fade', 10))          # its first four frames as before
        self.assertIsNone(transition_of(track, track.clips[1]))

    def test_older_projects_open_with_the_same_transition(self):
        short = self.clip(length=12)                                     # 10 asked, 6 played (half the clip)
        data = json.loads(json.dumps(Timeline(tracks=[Track('video', 'Video', [short])]).to_dict()))
        loaded = Timeline.from_dict(data)
        clip = loaded.tracks[0].clips[0]
        self.assertEqual(transition_of(loaded.tracks[0], clip), ('fade', 6))
        self.assertEqual(Timeline.from_dict(loaded.to_dict()).to_dict(), loaded.to_dict())

    def test_a_local_cut_keeps_the_opening_clips_transition(self):
        first = Clip('a.mp4', 0, 60, source_length=300, style={'transition': 'fade', 'transition_frames': 10})
        timeline = Timeline(tracks=[Track('video', 'Video', [first, Clip('a.mp4', 60, 60, source_in=100, source_length=300)])])
        sources = [{'path': 'a.mp4', 'duration': 10.0}]
        segments = edit_plan.current_segments(timeline, sources, keep=True)
        new, cuts = silence_cut.keep_segments(segments, {0: [(4.0, 4.5)]}, margin=0)
        self.assertTrue(cuts)
        result = edit_plan.apply_plan(timeline, sources, {'segments': new})
        self.assertEqual(transition_of(result.tracks[0], result.tracks[0].clips[0]), ('fade', 10))


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class ExactFrameTests(unittest.TestCase):
    def test_a_sped_up_clip_at_25_fps_shows_every_frame_it_should(self):
        # Output frame 28 at 25 fps (28 / 25 / 0.04 = 27.999…) was numbered 27, dropped, and the next picture
        # shown in its place.
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            media = MediaService(FFMPEG)
            raw = Path(folder) / 'n.gray'
            raw.write_bytes(b''.join(bytes([20 + (i % 8) * 30]) * (32 * 18) for i in range(120)))
            source = Path(folder) / 'n.mp4'
            media.run(['-v', 'error', '-y', '-f', 'rawvideo', '-pixel_format', 'gray', '-video_size', '32x18',
                       '-framerate', '25', '-i', str(raw), '-c:v', 'libx264', '-crf', '0', '-pix_fmt', 'yuv420p', str(source)])
            clip = Clip(str(source), 0, 32, source_in=5, style={'speed': 1.25})
            timeline = Timeline(25, 1, [Track('video', 'Video', [clip])])
            out = Path(folder) / 'out.mp4'
            TimelineRenderer(media, (32, 18)).export(timeline, out)
            data = media.run(['-v', 'error', '-i', str(out), '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-']).stdout
            shown = [round((v - 20) / 30) % 8 for v in np.frombuffer(data, dtype=np.uint8)]
            self.assertEqual(shown, [clip.source_frame(f) % 8 for f in range(32)])


if __name__ == '__main__':
    unittest.main()
