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
