import unittest
from akis.timeline_model import Clip, Track, Timeline
from akis.timeline_service import set_clip_volume, playback_volume

class VolumeTests(unittest.TestCase):
    def test_volume_survives_split_and_project_roundtrip(self):
        c=Clip('clip.mp4',0,20); timeline=Timeline(tracks=[Track('video','v',[c])])
        set_clip_volume(timeline,(0,c.id),.25)
        self.assertAlmostEqual(playback_volume(timeline,5,.8),.2)
        right=timeline.tracks[0].split(c.id,10)
        self.assertEqual(right.volume,.25)
        self.assertEqual(Timeline.from_dict(timeline.to_dict()).tracks[0].clips[1].volume,.25)
    def test_legacy_defaults(self):
        self.assertEqual(Clip('old',0,2).volume,1)
if __name__ == '__main__': unittest.main()
