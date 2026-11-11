import unittest
from akis.timeline_model import Clip, Timeline, Track


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

    def _timeline(self):
        video = Track('video', 'Video', [Clip('a', 0, 30), Clip('b', 30, 20), Clip('c', 50, 40)])
        text = Track('text', 'Text', [Clip('', 35, 10, text='x'), Clip('', 70, 10, text='y')])
        timeline = Timeline(tracks=[video, text], markers=[{'frame': 10, 'label': 'm1'}, {'frame': 40, 'label': 'm2'},
                                                          {'frame': 70, 'label': 'm3'}])
        return timeline, video.clips[1]

    def test_timeline_ripple_delete_shifts_all_tracks_and_markers(self):
        timeline, b = self._timeline()
        timeline.ripple_delete(0, b.id)
        self.assertEqual([c.start for c in timeline.tracks[0].clips], [0, 30])
        self.assertEqual([c.start for c in timeline.tracks[1].clips], [35, 50])
        self.assertEqual([m['frame'] for m in timeline.markers], [10, 30, 50])
        self.assertEqual(timeline.markers[0]['label'], 'm1')

    def test_timeline_ripple_delete_keeps_track_with_spanning_clip(self):
        timeline, b = self._timeline()
        music = Track('audio', 'Music', [Clip('m.mp3', 0, 60), Clip('n.mp3', 60, 10)])
        timeline.tracks.append(music)
        timeline.ripple_delete(0, b.id)
        self.assertEqual([c.start for c in music.clips], [0, 60])
        self.assertEqual([c.start for c in timeline.tracks[0].clips], [0, 30])

    def test_timeline_ripple_delete_rolls_back(self):
        timeline, b = self._timeline()
        before = timeline.to_dict()
        original = Track.validate
        calls = []
        def failing(track):
            calls.append(1)
            raise ValueError('boom')
        Track.validate = failing
        try:
            with self.assertRaises(ValueError):
                timeline.ripple_delete(0, b.id)
        finally:
            Track.validate = original
        self.assertEqual(timeline.to_dict(), before)

    def test_legacy_conversion(self):
        timeline = Timeline.from_legacy({'source': 'x.mp4', 'start': 1, 'end': 3})
        self.assertEqual((timeline.tracks[0].clips[0].source_in, timeline.tracks[0].clips[0].length), (30, 60))


if __name__ == '__main__':
    unittest.main()
