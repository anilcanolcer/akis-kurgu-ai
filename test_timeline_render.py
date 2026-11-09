import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from media_service import MediaService
from timeline_model import Clip, Timeline, Track
from timeline_render import TimelineRenderer, active_clips


class RenderTests(unittest.TestCase):
    def test_active_clips_offsets_and_muting(self):
        timeline = Timeline(tracks=[Track('video', 'v', [Clip('a', 10, 20, source_in=3)]),
                                    Track('overlay', 'o', [Clip('b', 0, 20)], muted=True)])
        active = active_clips(timeline, 15)
        self.assertEqual([(kind, source_frame) for kind, _, source_frame in active], [('video', 8)])
        self.assertEqual(active_clips(timeline, 30), [])

    def test_real_multitrack_preview_and_export(self):
        import main
        media = MediaService(main.ffmpeg_path())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one, two = root/'one.mp4', root/'two.mp4'
            for path, color in ((one, 'red'), (two, 'blue')):
                result = media.run(['-y', '-f', 'lavfi', '-i', f'color={color}:s=160x90:r=10:d=1',
                                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path])
                self.assertEqual(result.returncode, 0)
            timeline = Timeline(fps_num=10, tracks=[Track('video', 'base', [Clip(str(one), 0, 10)]),
                Track('overlay', 'top', [Clip(str(two), 5, 5)])])
            renderer = TimelineRenderer(media, (160, 90))
            preview = root/'frame.png'
            output = root/'result.mp4'
            renderer.preview(timeline, 7, preview)
            renderer.export(timeline, output)
            exported_frame = root/'exported.png'
            extracted = media.run(['-y', '-ss', '0.7', '-i', output, '-frames:v', '1', exported_frame])
            self.assertEqual(extracted.returncode, 0)
            from PIL import Image
            with Image.open(preview) as image:
                red, green, blue = image.convert('RGB').getpixel((80, 45))
                self.assertGreater(blue, red + 100)
            with Image.open(exported_frame) as image:
                red, green, blue = image.convert('RGB').getpixel((80, 45))
                self.assertGreater(blue, red + 100)
            self.assertGreater(preview.stat().st_size, 50)
            self.assertGreater(output.stat().st_size, 100)
            self.assertAlmostEqual(media.duration(output), 1, delta=0.2)


if __name__ == '__main__':
    unittest.main()
