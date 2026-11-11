import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from akis.media_service import MediaService, RenderCancelled


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

    def test_text_mode_decodes_utf8_with_replacement(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        service = MediaService('ffmpeg', runner)
        service.run(['-i', 'a.mp4'], text=True)
        self.assertTrue(runner.call_args.kwargs['text'])
        self.assertEqual(runner.call_args.kwargs['encoding'], 'utf-8')
        self.assertEqual(runner.call_args.kwargs['errors'], 'replace')
        service.run(['-i', 'a.mp4'], text=False)
        kwargs = runner.call_args.kwargs
        self.assertNotIn('encoding', kwargs)
        self.assertNotIn('errors', kwargs)
        self.assertFalse(kwargs.get('text', False))

    @unittest.skipIf(shutil.which('ffmpeg') is None, 'ffmpeg not on PATH')
    def test_real_turkish_file_name_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ĞüzelÇekim şöğüı.mp4'
            service = MediaService(shutil.which('ffmpeg'))
            made = service.run(['-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10', '-t', '1',
                                '-pix_fmt', 'yuv420p', path])
            self.assertEqual(made.returncode, 0)
            self.assertAlmostEqual(service.duration(path), 1.0, delta=0.2)

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


# A real FFmpeg run that takes ~30 s unless stopped (-re reads the generated input in real time).
SLOW = ['-v', 'error', '-re', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=30', '-f', 'null', '-']


class CancellationTests(unittest.TestCase):
    @unittest.skipIf(shutil.which('ffmpeg') is None, 'ffmpeg not on PATH')
    def test_cancel_from_another_thread_kills_ffmpeg_promptly(self):
        import threading
        import time
        service = MediaService(shutil.which('ffmpeg'))
        outcome = []

        def work():
            try:
                service.run(SLOW, text=True)
                outcome.append('finished')
            except RenderCancelled:
                outcome.append('cancelled')
        thread = threading.Thread(target=work)
        thread.start()
        deadline = time.monotonic() + 5
        while service._process is None and time.monotonic() < deadline:
            time.sleep(0.01)
        started = time.monotonic()
        service.cancel()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(outcome, ['cancelled'])
        self.assertIsNone(service._process)
        with self.assertRaises(RenderCancelled):  # stays cancelled: a worker's later steps stop too
            service.run(['-version'])
        self.assertIsInstance(RenderCancelled('x'), RuntimeError)

    @unittest.skipIf(shutil.which('ffmpeg') is None, 'ffmpeg not on PATH')
    def test_timeout_stops_ffmpeg_and_probe_reports_nothing(self):
        import time
        service = MediaService(shutil.which('ffmpeg'))
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            service.run(SLOW, timeout=0.5)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(service.run(['-version']).returncode, 0)  # a timeout is not a cancel
        stalled = MediaService(shutil.which('ffmpeg'))
        stalled.run = Mock(side_effect=subprocess.TimeoutExpired('ffmpeg', 30))
        self.assertEqual(stalled.probe('//slow-share/video.mp4'), '')
        self.assertEqual(stalled.run.call_args.kwargs['timeout'], 30)
        with self.assertRaises(ValueError):
            stalled.duration('//slow-share/video.mp4')

    def test_fake_runner_is_called_as_before_and_respects_cancel(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', 'Duration: 00:00:01.00'))
        service = MediaService('ffmpeg', runner)
        service.duration('a.mp4')
        self.assertEqual(set(runner.call_args.kwargs), {'capture_output', 'text', 'encoding', 'errors', 'creationflags'})
        service.cancel()
        with self.assertRaises(RenderCancelled):
            service.run(['-i', 'a.mp4'])
        self.assertEqual(runner.call_count, 1)

    @unittest.skipUnless(os.name == 'nt' and shutil.which('ffmpeg'), 'Windows priority classes')
    def test_low_priority_runs_below_normal(self):
        real = subprocess.Popen
        seen = []

        def spy(*args, **kwargs):
            seen.append(kwargs['creationflags'])
            return real(*args, **kwargs)
        with patch('subprocess.Popen', spy):
            MediaService(shutil.which('ffmpeg'), low_priority=True).run(['-version'])
            MediaService(shutil.which('ffmpeg')).run(['-version'])
        self.assertTrue(seen[0] & subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        self.assertFalse(seen[1] & subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        self.assertTrue(seen[1] & subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    unittest.main()
