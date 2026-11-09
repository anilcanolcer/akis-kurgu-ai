import unittest
from timeline_model import Clip, Timeline, Track


class TimelineTests(unittest.TestCase):
    def test_split_preserves_source_offsets_and_roundtrip(self):
        track = Track('video', 'Video', [Clip('a.mp4', 0, 100, source_in=10, source_length=150)])
        right = track.split(track.clips[0].id, 40)
        self.assertEqual((right.start, right.source_in, right.length), (40, 50, 60))
        restored = Timeline.from_dict(Timeline(tracks=[track]).to_dict())
        self.assertEqual(restored.tracks[0].clips[1].source_in, 50)

    def test_ripple_and_invalid_slip(self):
        a, b = Clip('a', 0, 30, source_length=50), Clip('b', 30, 20)
        track = Track('video', 'Video', [a, b])
        track.trim_end(a.id, 20, ripple=True)
        self.assertEqual(b.start, 20)
        with self.assertRaises(ValueError):
            track.slip(a.id, -1)
        self.assertEqual(a.source_in, 0)

    def test_legacy_conversion(self):
        timeline = Timeline.from_legacy({'source': 'x.mp4', 'start': 1, 'end': 3})
        self.assertEqual((timeline.tracks[0].clips[0].source_in, timeline.tracks[0].clips[0].length), (30, 60))


if __name__ == '__main__':
    unittest.main()
