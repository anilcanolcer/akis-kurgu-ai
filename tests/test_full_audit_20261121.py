"""Fixes from the second 21 November 2026 audit (scripts/media-audit/ai_fuzz.py and the other checkers)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import tempfile
import unittest
from pathlib import Path

from akis import edit_plan, speakers
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

FFMPEG = shutil.which('ffmpeg')


class PlanOnFastClipTests(unittest.TestCase):
    def test_a_plan_that_keeps_a_sliver_of_a_fast_clip_applies(self):
        # The kept stretch begins a fraction of a frame before the 4× clip ends: it rounded to a piece of
        # no length, and moving the sound track along failed with a TypeError instead of giving the edit.
        timeline = Timeline(24, 1, [
            Track('video', 'Video', [Clip('a.mp4', 0, 21, source_in=10),
                                     Clip('a.mp4', 21, 63, source_in=49, style={'speed': 4.0})]),
            Track('audio', 'Ses', [Clip('mic.wav', 0, 42), Clip('mic.wav', 42, 42, source_in=42)]),
            Track('overlay', 'İşaretler', [Clip('', 65, 25, style={'shape': 'circle'})])])
        sources = [{'path': 'a.mp4', 'duration': 20.0}, {'path': 'b.mp4', 'duration': 20.0}]
        result = edit_plan.apply_plan(timeline, sources, {'segments': [{'source': 0, 'start': 12.440225874683163, 'end': 18.0}]})
        main = edit_plan.primary_track(result)
        self.assertEqual([(c.start, c.source_in) for c in main.clips][:1], [(0, 299)])     # 12.44 s × 24 = frame 298.6
        for track in result.tracks:
            track.validate()


class SpeakerMarkerTests(unittest.TestCase):
    def test_a_change_in_a_split_clips_first_fraction_stays_inside_the_clip(self):
        # The 0.25× clip starts a quarter frame into source frame 30: a speaker change at source frame 30 was
        # put at timeline frame -1, before the video.
        clip = Clip('a.mp4', 0, 40, source_in=30, style={'speed': 0.25, 'source_phase': 0.25})
        found = [(30 / 30, 2.0, 1, 'merhaba')]
        self.assertEqual(speakers.markers(found, [clip], 30), [{'frame': 0, 'label': 'Konuşmacı 2'}])


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class SlowSoundTests(unittest.TestCase):
    def sound(self, path, media):
        import numpy as np
        data = media.run(['-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', '8000', '-f', 'f32le', '-']).stdout
        return np.frombuffer(data, dtype=np.float32)

    def test_a_slow_clip_keeps_the_end_of_its_sound_and_the_sound_lasts_as_long_as_the_picture(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            media = MediaService(FFMPEG)
            source = Path(folder) / 'ton.mp4'
            media.run(['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:size=32x18:rate=30:d=4',
                       '-f', 'lavfi', '-i', 'sine=f=440:d=4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                       '-shortest', str(source)])
            # A 0.25× clip of six frames (its last 50-70 ms of sound used to be lost), then a 1 s gap.
            slice_ = Timeline(30, 1, [Track('video', 'Video', [Clip(str(source), 0, 30),
                                                              Clip(str(source), 30, 6, source_in=60, style={'speed': 0.25})])])
            slice_.length_floor = 66
            out = Path(folder) / 'out.mp4'
            TimelineRenderer(media, (32, 18)).export(slice_, out)
            sound = self.sound(out, media)
            self.assertAlmostEqual(len(sound) / 8000, 66 / 30, delta=0.04)     # was 1.2 s against 2.2 s
            slow = sound[int(1.0 * 8000):int(1.16 * 8000)]                     # the slow clip's last frames
            self.assertGreater(float(np.sqrt(np.mean(slow ** 2))), 0.05)        # the tone's own level is 0.088
            self.assertLess(float(np.sqrt(np.mean(sound[int(1.5 * 8000):] ** 2))), 0.01)


if __name__ == '__main__':
    unittest.main()
