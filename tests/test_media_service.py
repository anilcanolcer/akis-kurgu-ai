import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from akis.media_service import MediaService


class MediaTests(unittest.TestCase):
    def test_duration_and_argument_boundaries(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'Duration: 00:01:02.50, start: 0'))
        service = MediaService('ffmpeg', runner)
        self.assertEqual(service.duration('my video.mp4'), 62.5)
        self.assertEqual(runner.call_args.args[0][-1], 'my video.mp4')

    def test_missing_duration(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'Invalid data'))
        with self.assertRaises(ValueError):
            MediaService('ffmpeg', runner).duration('bad.mp4')

    def test_rotated_phone_video_reports_upright_size(self):
        report = ('  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, 1920x1080, 30 fps\n'
                  '      Side data:\n        displaymatrix: rotation of -90.00 degrees\n'
                  '  Stream #0:1[0x2](und): Audio: aac (LC), 48000 Hz, stereo\nDuration: 00:00:05.00')
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, '', report))
        self.assertEqual(MediaService('ffmpeg', runner).dimensions('phone.mp4'), (1080, 1920))
        upside_down = report.replace('-90.00', '180.00')
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, '', upside_down))
        self.assertEqual(MediaService('ffmpeg', runner).dimensions('phone.mp4'), (1920, 1080))

    def test_real_rotated_file_and_probe_cache(self):
        import main
        with tempfile.TemporaryDirectory() as tmp:
            plain, rotated = Path(tmp) / 'plain.mp4', Path(tmp) / 'rotated.mp4'
            service = MediaService(main.ffmpeg_path())
            self.assertEqual(service.run(['-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10', '-t', '1',
                                          '-c:v', 'libx264', '-pix_fmt', 'yuv420p', plain]).returncode, 0)
            self.assertEqual(service.run(['-y', '-display_rotation', '90', '-i', plain, '-c', 'copy', rotated]).returncode, 0)
            self.assertEqual(service.dimensions(plain), (320, 180))
            self.assertEqual(service.dimensions(rotated), (180, 320))
            calls = []
            counting = MediaService(main.ffmpeg_path())
            original = counting.run
            counting.run = lambda args, text=False: calls.append(args) or original(args, text=text)
            counting.duration(rotated); counting.has_audio(rotated); counting.dimensions(rotated)
            self.assertEqual(calls, [])  # already probed above

    def test_real_frame_extraction(self):
        import main
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / 'sample.mp4'
            output = Path(tmp) / 'frame.jpg'
            service = MediaService(main.ffmpeg_path())
            generated = service.run(['-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10',
                                     '-t', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', sample])
            self.assertEqual(generated.returncode, 0)
            result = service.extract_frame(sample, 0.5, output)
            self.assertEqual(result.returncode, 0)
            self.assertGreater(output.stat().st_size, 100)


if __name__ == '__main__':
    unittest.main()
