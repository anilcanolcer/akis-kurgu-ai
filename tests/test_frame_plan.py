import unittest
from akis.frame_plan import audio_at, plan_frame, plan_segments
from akis.timeline_model import Clip, Timeline, Track


class FramePlanTests(unittest.TestCase):
    def test_layer_order_offsets_and_end_exclusive(self):
        t = Timeline(tracks=[Track('video', 'v', [Clip('a', 3, 7, source_in=4)]),
                             Track('text', 't', [Clip('', 5, 2, text='title')])])
        layers = plan_frame(t, 5)
        self.assertEqual([(x.kind, x.source_frame) for x in layers], [('video', 6), ('text', 0)])
        self.assertEqual(len(plan_frame(t, 7)), 1)

    def test_move_rolls_back_and_ripple_delete(self):
        a, b = Clip('a', 0, 10), Clip('b', 10, 10)
        track = Track('video', 'v', [a, b])
        with self.assertRaises(ValueError):
            track.move(b.id, 5)
        self.assertEqual(b.start, 10)
        track.ripple_delete(a.id)
        self.assertEqual(b.start, 0)

    def test_segments_and_audio_selection(self):
        timeline = Timeline(tracks=[Track('video', 'v', [Clip('v', 0, 10)]),
                                    Track('audio', 'a', [Clip('a', 3, 4, source_in=2)])])
        self.assertEqual([(a, b) for a, b, _ in plan_segments(timeline)], [(0, 3), (3, 7), (7, 10)])
        self.assertEqual((audio_at(timeline, 4).source, audio_at(timeline, 4).source_frame), ('a', 3))
        self.assertEqual(audio_at(timeline, 8).source, 'v')


if __name__ == '__main__':
    unittest.main()
