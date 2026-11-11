import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from array import array

from akis.media_service import MediaService, RenderCancelled
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer, _escape_filter_path, active_clips, partial_output_path


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

    @staticmethod
    def _caption_timeline(count, fps=10):
        clips = [Clip('', i, 1, text=f'Caption number {i}', style={'size': 'medium'}) for i in range(count)]
        return Timeline(fps_num=fps, tracks=[Track('text', 'captions', clips)])

    def test_many_captions_keep_command_line_short(self):
        calls = []

        def run(args, text=False):
            args = list(map(str, args))
            at = args.index('-/filter_complex')
            self.assertNotIn('-filter_complex', args)
            calls.append((args, Path(args[at + 1]).read_text(encoding='utf-8')))
            Path(args[-1]).write_bytes(b'x')
            return Mock(returncode=0, stderr='')

        media = Mock(run=run)
        with tempfile.TemporaryDirectory() as tmp:
            TimelineRenderer(media, (160, 90)).export(self._caption_timeline(300), Path(tmp) / 'out.mp4')
        args, graph = calls[0]
        self.assertLess(sum(len(a) + 1 for a in args), 8000)
        self.assertEqual(graph.count('drawtext='), 300)  # graph contents are unchanged, just moved
        self.assertGreater(len(graph), 32767)

    def test_real_export_with_many_captions(self):
        import shutil
        if shutil.which('ffmpeg') is None:
            self.skipTest('ffmpeg not installed')
        import main
        media = MediaService(main.ffmpeg_path())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / 'src.mp4'
            self.assertEqual(media.run(['-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=2',
                                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', video]).returncode, 0)
            timeline = self._caption_timeline(150)
            timeline.tracks.insert(0, Track('video', 'v', [Clip(str(video), 0, 20)]))
            output = root / 'out.mp4'
            TimelineRenderer(media, (160, 90)).export(timeline, output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 100)


def _fake_media(on_run=None, returncode=0):
    """Mock media that records each run with its graph and text files (read while they exist)."""
    calls = []

    def run(args, text=False):
        args = list(map(str, args))
        graph = Path(args[args.index('-/filter_complex') + 1]).read_text(encoding='utf-8')
        texts = {p.name: p.read_bytes() for p in Path(args[args.index('-/filter_complex') + 1]).parent.glob('text*.txt')}
        calls.append((args, graph, texts))
        if on_run:
            on_run(args)
        if not returncode:
            Path(args[-1]).write_bytes(b'new')
        return Mock(returncode=returncode, stderr='boom')

    return Mock(run=run, has_audio=Mock(return_value=True)), calls


def _make(media, *args):
    result = media.run(['-y', '-v', 'error', *args])
    assert result.returncode == 0, result.stderr


@unittest.skipIf(shutil.which('ffmpeg') is None, 'ffmpeg not on PATH')
class RealRenderFixes(unittest.TestCase):
    """Real-ffmpeg checks for the seek, speed, text and path fixes (small 160x90 sources)."""

    def setUp(self):
        self.media = MediaService(shutil.which('ffmpeg'))
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def frames(self, path, size=(160, 90)):
        """Grey frames as bytes, one per frame."""
        raw = self.media.run(['-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'gray', '-']).stdout
        step = size[0] * size[1]
        return [raw[i:i + step] for i in range(0, len(raw), step)]

    @staticmethod
    def mse(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)

    def pcm(self, path):
        """Absolute mono samples at 8 kHz."""
        raw = self.media.run(['-v', 'error', '-i', path, '-map', '0:a', '-ac', '1', '-ar', '8000', '-f', 's16le', '-']).stdout
        return [abs(v) for v in array('h', raw[:len(raw) // 2 * 2])]

    def test_export_seeks_inputs_with_frames_and_sound_aligned(self):
        # 3 s source: a picture with a frame counter and a 1 kHz click at exactly 2.0 s.
        source, music = self.root / 'src.mp4', self.root / 'music.wav'
        _make(self.media, '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=3', '-f', 'lavfi', '-i',
              "aevalsrc='if(between(t,2,2.1),0.8*sin(2*PI*1000*t),0)':s=44100:d=3",
              '-c:v', 'libx264', '-g', '30', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-aac_pns', '0', source)
        _make(self.media, '-f', 'lavfi', '-i', "aevalsrc='if(between(t,2.5,2.6),0.8*sin(2*PI*500*t),0)':s=44100:d=3", music)
        # Video clip cut from the middle (1.5 s in); music cut from 2.0 s placed at 0.2 s.
        timeline = Timeline(fps_num=10, tracks=[
            Track('video', 'v', [Clip(str(source), 0, 10, source_in=15, source_length=30)]),
            Track('audio', 'a', [Clip(str(music), 2, 8, source_in=20, source_length=30)])])
        calls = []
        original = self.media.run
        self.media.run = lambda args, text=False, timeout=None: (calls.append(list(map(str, args))) or original(args, text=text, timeout=timeout))
        output = self.root / 'out.mp4'
        TimelineRenderer(self.media, (160, 90)).export(timeline, output)
        args = calls[-1]
        graph = Path(args[args.index('-/filter_complex') + 1])
        self.assertEqual(args[args.index(str(source)) - 3:args.index(str(source))], ['-ss', f'{1.0:.9f}', '-i'])  # 0.5 s audio pre-roll
        self.assertEqual(args[args.index(str(music)) - 3:args.index(str(music))], ['-ss', f'{1.5:.9f}', '-i'])
        self.assertFalse(graph.exists())  # temp dir cleaned
        # Pictures: each exported frame matches source frame 15+k, not its neighbours.
        exported, original_frames = self.frames(output), self.frames(source)
        self.assertEqual(len(exported), 10)
        for k in (0, 4, 9):
            errors = [self.mse(exported[k], original_frames[i]) for i in (14 + k, 15 + k, 16 + k)]
            self.assertEqual(errors.index(min(errors)), 1, f'frame {k}: {errors}')
        # Sound: the clip's click (2.0 s in source) at 0.5 s; the music's (2.5 s) at 0.2 + 0.5 = 0.7 s.
        loud = [i / 8000 for i, v in enumerate(self.pcm(output)) if v > 3000]
        clicks = [loud[0]] + [t for a, t in zip(loud, loud[1:]) if t - a > 0.05]
        self.assertEqual(len(clicks), 2, clicks)
        self.assertAlmostEqual(clicks[0], 0.5, delta=0.01)
        self.assertAlmostEqual(clicks[1], 0.7, delta=0.01)

    def test_speed_is_one_encode_with_exact_duration_and_fps(self):
        source = self.root / 'src.mp4'
        _make(self.media, '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=2', '-f', 'lavfi', '-i',
              'sine=frequency=440:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', source)
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'v', [Clip(str(source), 0, 20)])])
        for speed, frames in ((2.0, 10), (0.5, 40)):
            calls = []
            original = self.media.run
            self.media.run = lambda args, text=False, timeout=None: (calls.append(args) or original(args, text=text, timeout=timeout))
            output = self.root / f'speed{speed}.mp4'
            TimelineRenderer(self.media, (160, 90), speed=speed).export(timeline, output)
            self.media.run = original
            self.assertEqual(sum('libx264' in map(str, a) for a in calls), 1)
            self.assertAlmostEqual(len(self.frames(output)), frames, delta=1)
            self.assertIn(' 10 fps', self.media.probe(output))
            self.assertAlmostEqual(len(self.pcm(output)) / 8000, 2 / speed, delta=0.06)

    def test_text_in_folder_with_apostrophe_and_space(self):
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf'
        if not font.is_file():
            self.skipTest('arial.ttf not available')
        odd = self.root / "O'Neil temp [x],y;z"
        odd.mkdir()
        odd_font = odd / "fo'nt.ttf"
        shutil.copy(font, odd_font)
        timeline = Timeline(fps_num=10, tracks=[Track('text', 't', [
            Clip('', 0, 10, text='Merhaba\r\nDünya'), Clip('', 10, 10, text="O'Neil", style={'size': 'large'})])])
        with patch('tempfile.tempdir', str(odd)):
            for frame in (5, 15):
                still = self.root / f'text{frame}.png'
                TimelineRenderer(self.media, (320, 180), font=str(odd_font)).preview(timeline, frame, still)
                self.assertGreater(max(self.frames(still, (320, 180))[0]), 200, frame)  # text drawn, not black
            TimelineRenderer(self.media, (160, 90), font=str(odd_font)).export(timeline, self.root / 'text.mp4')
        self.assertEqual(len(self.frames(self.root / 'text.mp4')), 20)

    def test_cancelled_real_export_keeps_previous_file(self):
        import threading
        import time
        source = self.root / 'src.mp4'
        _make(self.media, '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=3', '-c:v', 'libx264',
              '-pix_fmt', 'yuv420p', source)
        # -re makes FFmpeg read the source in real time, so the export reliably runs for ~3 s.
        timeline = Timeline(fps_num=10, tracks=[Track('video', 'v', [Clip(str(source), 0, 30)])])
        target = self.root / 'final.mp4'
        target.write_bytes(b'previous good export')
        original = self.media.run
        self.media.run = lambda args, text=False, timeout=None: original(
            ['-re', *args] if '-/filter_complex' in map(str, args) else args, text=text, timeout=timeout)
        outcome = []

        def export():
            try:
                TimelineRenderer(self.media, (160, 90)).export(timeline, target)
                outcome.append('done')
            except RenderCancelled:
                outcome.append('cancelled')
        thread = threading.Thread(target=export)
        thread.start()
        partial = self.root / 'final.part.mp4'
        deadline = time.monotonic() + 5
        while not partial.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.media.cancel()
        thread.join(5)
        self.assertEqual(outcome, ['cancelled'])
        self.assertEqual(target.read_bytes(), b'previous good export')
        self.assertFalse(partial.exists())

    def test_line_breaks_draw_no_extra_blank_line(self):
        heights = {}
        for text in ('Bir\nIki', 'Bir\r\nIki', 'Bir\rIki', 'Bir\n\nIki'):
            for style in ({}, {'size': 'small'}):
                still = self.root / 'line.png'
                timeline = Timeline(fps_num=10, tracks=[Track('text', 't', [Clip('', 0, 10, text=text, style=style)])])
                TimelineRenderer(self.media, (320, 180)).preview(timeline, 0, still)
                picture = self.frames(still, (320, 180))[0]
                rows = [y for y in range(180) if max(picture[y * 320:(y + 1) * 320]) > 200]
                heights[text, bool(style)] = rows[-1] - rows[0]
        for styled in (False, True):
            self.assertEqual(heights['Bir\nIki', styled], heights['Bir\r\nIki', styled])
            self.assertEqual(heights['Bir\nIki', styled], heights['Bir\rIki', styled])
            self.assertLess(heights['Bir\nIki', styled], heights['Bir\n\nIki', styled])  # the user's own blank line stays


class RenderFixTests(unittest.TestCase):
    def test_text_files_keep_user_line_breaks_with_lf_only(self):
        media, calls = _fake_media()
        long = 'bu satır epeyce uzun bir cümle ve sarılması gerekiyor'
        timeline = Timeline(fps_num=10, tracks=[Track('text', 't', [
            Clip('', 0, 5, text='Bir\r\nİki\rÜç'),
            Clip('', 5, 5, text=f'Başlık\n\n{long}', style={'size': 'medium'})])])
        with tempfile.TemporaryDirectory() as tmp:
            TimelineRenderer(media, (160, 90)).export(timeline, Path(tmp) / 'out.mp4')
        plain, styled = (calls[0][2][name].decode('utf-8') for name in sorted(calls[0][2]))
        self.assertNotIn(b'\r', b''.join(calls[0][2].values()))
        self.assertEqual(plain, 'Bir\nİki\nÜç')
        lines = styled.split('\n')
        self.assertEqual(lines[:2], ['Başlık', ''])  # own break and empty line survive
        self.assertGreater(len(lines), 3)  # the long paragraph is still wrapped
        self.assertTrue(all(len(line) <= 22 for line in lines))
        self.assertEqual(' '.join(lines[2:]), long)

    def test_filter_paths_escape_apostrophes_for_both_parsers(self):
        self.assertEqual(_escape_filter_path(r"C:\Users\O'Neil\a,b.txt"), r"C\\:/Users/O\\\'Neil/a\,b.txt")
        media, calls = _fake_media()
        timeline = Timeline(fps_num=10, tracks=[Track('text', 't', [Clip('', 0, 5, text='x')])])
        with tempfile.TemporaryDirectory() as tmp:
            TimelineRenderer(media, (160, 90), font="C:/O'Neil/f.ttf").export(timeline, Path(tmp) / 'out.mp4')
        self.assertIn(r"fontfile=C\\:/O\\\'Neil/f.ttf:", calls[0][1])
        self.assertNotIn("textfile='", calls[0][1])

    def test_speed_folds_into_the_single_export_graph(self):
        media, calls = _fake_media()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'a.mp4'; source.write_bytes(b'x')
            timeline = Timeline(fps_num=10, tracks=[Track('video', 'v', [Clip(str(source), 0, 20)])])
            TimelineRenderer(media, (160, 90), speed=1.5).export(timeline, Path(tmp) / 'out.mp4')
        self.assertEqual(len(calls), 1)
        args, graph, _ = calls[0]
        self.assertIn('[graded]setpts=PTS/1.500000[timed]', graph)
        self.assertIn('atempo=1.500000[aout]', graph)
        self.assertEqual(args[args.index('-map') + 1], '[timed]')
        self.assertEqual(args[args.index('-t') + 1], f'{2 / 1.5:.9f}')

    def test_failed_or_cancelled_export_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'final.mp4'
            timeline = Timeline(fps_num=10, tracks=[Track('text', 't', [Clip('', 0, 5, text='x')])])

            def half_written(args):
                Path(args[-1]).write_bytes(b'partial')

            def cancelled_midway(args):
                half_written(args)
                raise RenderCancelled('cancelled')
            for media, error in ((_fake_media(half_written, returncode=1)[0], RuntimeError),
                                 (_fake_media(cancelled_midway)[0], RenderCancelled)):
                target.write_bytes(b'previous good export')
                with self.assertRaises(error):
                    TimelineRenderer(media, (160, 90)).export(timeline, target)
                self.assertEqual(target.read_bytes(), b'previous good export')
                self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['final.mp4'])
            media, calls = _fake_media()
            TimelineRenderer(media, (160, 90)).export(timeline, target)
            self.assertEqual(calls[0][0][-1], str(Path(tmp) / 'final.part.mp4'))
            self.assertEqual(target.read_bytes(), b'new')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['final.mp4'])

    def test_partial_name_keeps_container_extension(self):
        self.assertEqual(partial_output_path('C:/v/clip.mov').name, 'clip.part.mov')
        self.assertEqual(partial_output_path('C:/v/clip').name, 'clip.part.mp4')


if __name__ == '__main__':
    unittest.main()
