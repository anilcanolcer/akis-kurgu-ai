import unittest
from akis.caption_service import caption_track, snap_frame
from akis.timeline_model import Clip, Timeline, Track

class CaptionsTests(unittest.TestCase):
    def test_maps_trimmed_source_to_timeline(self):
        timeline=Timeline(fps_num=10,tracks=[Track('video','V',[Clip('x',20,20,source_in=10)])])
        count=caption_track(timeline,'x',[{'start':0.5,'end':1.5,'text':'Merhaba'}, {'start':2,'end':4,'text':'Dünya'}])
        self.assertEqual(count,2)
        self.assertEqual([(c.start,c.length,c.text) for c in timeline.tracks[-1].clips],[(20,5,'Merhaba'),(30,10,'Dünya')])
        self.assertEqual(Timeline.from_dict(timeline.to_dict()).tracks[-1].clips[0].text,'Merhaba')
    def test_snap_and_exclusion(self):
        clip=Clip('x',10,20); timeline=Timeline(tracks=[Track('video','v',[clip])])
        self.assertEqual(snap_frame(timeline,28,3),30)
        self.assertEqual(snap_frame(timeline,28,3,(0,clip.id)),28)
        self.assertEqual(snap_frame(timeline,15,3),15)
if __name__ == '__main__': unittest.main()
