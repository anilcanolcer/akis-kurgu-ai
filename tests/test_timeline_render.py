import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer, active_clips


class RenderTests(unittest.TestCase):
    def test_active_clips_offsets_and_muting(self):
        timeline = Timeline(tracks=[Track('video', 'v', [Clip('a', 10, 20, source_in=3)]),
                                    Track('overlay', 'o', [Clip('b', 0, 20)], muted=True)])
        active = active_clips(timeline, 15)
        self.assertEqual([(kind, source_frame) for kind, _, source_frame in active], [('video', 8)])
        self.assertEqual(active_clips(timeline, 30), [])

    def test_renderer_refuses_source_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.mp4'; source.write_bytes(b'original')
            timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(source), 0, 30)])])
            with self.assertRaisesRegex(ValueError, 'kaynak'):
                TimelineRenderer(Mock(), (160, 90)).export(timeline, source)
            self.assertEqual(source.read_bytes(), b'original')

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
            adjusted = TimelineRenderer(media, (160, 90), brightness=-30, saturation=-50, speed=2)
            adjusted_preview, adjusted_output = root/'adjusted.png', root/'adjusted.mp4'
            adjusted.preview(timeline, 7, adjusted_preview)
            adjusted.export(timeline, adjusted_output)
            adjusted_frame = root/'adjusted-output.png'
            check = media.run(['-y', '-ss', '0.35', '-i', adjusted_output, '-frames:v', '1', adjusted_frame])
            self.assertEqual(check.returncode, 0)
            self.assertAlmostEqual(media.duration(adjusted_output), 0.5, delta=0.2)
            with Image.open(adjusted_preview) as image:
                red, green, blue = image.convert('RGB').getpixel((80, 45))
                self.assertLess(blue, 200)
                preview_pixel = (red, green, blue)
            with Image.open(adjusted_frame) as image:
                output_pixel = image.convert('RGB').getpixel((80, 45))
            for a, b in zip(preview_pixel, output_pixel):
                self.assertLess(abs(a-b), 25)

    def test_layers_start_on_their_exact_frame_and_preview_seeks_inputs(self):
        import main
        from PIL import Image
        media = MediaService(main.ffmpeg_path())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            red, blue = root / 'red.mp4', root / 'blue.mp4'
            for path, color in ((red, 'red'), (blue, 'blue')):
                self.assertEqual(media.run(['-y', '-f', 'lavfi', '-i', f'color={color}:s=160x90:r=30:d=4',
                                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path]).returncode, 0)
            # 5/30 s is not exact in floating point: the overlay used to appear one frame late.
            timeline = Timeline(tracks=[Track('video', 'v', [Clip(str(red), 0, 30, source_in=60, source_length=120)]),
                                        Track('overlay', 'o', [Clip(str(blue), 5, 10, source_in=40, source_length=120)])])
            renderer = TimelineRenderer(media, (160, 90))
            output = root / 'out.mp4'
            renderer.export(timeline, output)
            for frame, expect_blue in ((4, False), (5, True), (14, True), (15, False)):
                still, exported = root / f'p{frame}.png', root / f'e{frame}.png'
                renderer.preview(timeline, frame, still)
                self.assertEqual(media.run(['-y', '-i', output, '-vf', f'select=eq(n\\,{frame})',
                                            '-frames:v', '1', exported]).returncode, 0)
                for picture in (still, exported):
                    with Image.open(picture) as image:
                        r, _, b = image.convert('RGB').getpixel((80, 45))
                    self.assertEqual(b > r, expect_blue, f'{picture.name}')
            calls = []
            spy = MediaService(main.ffmpeg_path())
            original = spy.run
            spy.run = lambda args, text=False: calls.append(list(map(str, args))) or original(args, text=text)
            TimelineRenderer(spy, (160, 90)).preview(timeline, 20, root / 'seek.png')
            args = calls[-1]
            at = args.index(str(red))
            self.assertEqual(args[at - 3:at], ['-ss', f'{80 / 30:.9f}', '-i'])  # 60 in + 20 played


if __name__ == '__main__':
    unittest.main()
