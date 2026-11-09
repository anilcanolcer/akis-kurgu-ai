import tempfile
import unittest
from pathlib import Path
from main import ffmpeg_path
from media_service import MediaService
from timeline_model import Clip, Track, Timeline
from timeline_render import TimelineRenderer

class VolumeExportTest(unittest.TestCase):
    def test_audio_clip_volume_affects_real_export(self):
        media=MediaService(ffmpeg_path())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'tone.wav'; output=root/'out.mp4'; raw=root/'audio.raw'
            self.assertEqual(media.run(['-y','-f','lavfi','-i','sine=frequency=440:duration=1',source]).returncode,0)
            clip=Clip(str(source),0,10,volume=0)
            timeline=Timeline(fps_num=10,tracks=[Track('audio','a',[clip])])
            TimelineRenderer(media,(160,90)).export(timeline,output)
            self.assertEqual(media.run(['-y','-i',output,'-f','s16le','-ac','1','-ar','8000',raw]).returncode,0)
            self.assertTrue(raw.stat().st_size>100)
            self.assertEqual(set(raw.read_bytes()),{0})
if __name__ == '__main__': unittest.main()
