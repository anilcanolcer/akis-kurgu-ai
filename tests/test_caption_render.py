import tempfile
import unittest
from pathlib import Path
from main import ffmpeg_path
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer
from akis.caption_service import caption_track

class CaptionRenderTest(unittest.TestCase):
    def test_caption_preview_and_export_real_ffmpeg(self):
        from PIL import Image, ImageChops
        media=MediaService(ffmpeg_path())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); video=root/'video.mp4'
            r=media.run(['-y','-f','lavfi','-i','color=black:s=160x90:r=10:d=1','-c:v','libx264',video])
            self.assertEqual(r.returncode,0)
            tl=Timeline(fps_num=10, tracks=[Track('video','v',[Clip(str(video),0,10)])])
            caption_track(tl,str(video),[{'start':0,'end':1,'text':'Hello'}])
            renderer=TimelineRenderer(media,(160,90)); frame=root/'frame.png'; out=root/'out.mp4'; extracted=root/'out.png'
            renderer.preview(tl,5,frame); renderer.export(tl,out)
            self.assertEqual(media.run(['-y','-ss','0.5','-i',out,'-frames:v','1',extracted]).returncode,0)
            with Image.open(frame) as a, Image.open(extracted) as b:
                self.assertGreater(a.convert('RGB').getbbox()[3], 0)
                self.assertIsNotNone(ImageChops.difference(a.convert('RGB'), Image.new('RGB',a.size)).getbbox())
                self.assertIsNotNone(ImageChops.difference(b.convert('RGB'), Image.new('RGB',b.size)).getbbox())
if __name__ == '__main__': unittest.main()
