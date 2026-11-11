"""Update download, cleanup and pre-launch verification. No network, nothing is executed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import base64
import hashlib
import io
import json
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from akis import update_service
from akis.update_service import DownloadCancelled, cleanup_legacy_temp, cleanup_update_dir, download, launch_installer
from akis.update_worker import UpdateDownloadWorker

app = QApplication.instance() or QApplication([])
DATA = b'installer bytes ' * 50_000  # ~800 kB: several chunks
SHA = hashlib.sha256(DATA).hexdigest()
UPDATE = {'version': 'v9.9.9', 'url': update_service.DOWNLOAD_PREFIX + 'v9.9.9/AkisKurguAI-Setup.exe',
          'sha256': SHA, 'size': len(DATA)}


class FakeResponse(io.BytesIO):
    def __init__(self, data, delay=0.0):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}
        self.delay = delay

    def read(self, size=-1):
        if self.delay:
            time.sleep(self.delay)
        return super().read(size)


def opener_for(data, delay=0.0):
    return Mock(side_effect=lambda request, timeout: FakeResponse(data, delay))


def helper_script(command):
    return base64.b64decode(command[-1]).decode('utf-16le')


def helper_payload(script):
    encoded = re.search(r"FromBase64String\('([^']+)'\)", script).group(1)
    return json.loads(base64.b64decode(encoded).decode('utf-8'))


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / 'updates'
        self.target = update_service.installer_path(self.folder, UPDATE)

    def test_metadata_carries_size_and_fixed_target_name(self):
        asset = {'name': update_service.ASSET, 'browser_download_url': UPDATE['url'],
                 'digest': 'sha256:' + SHA.upper(), 'size': 1234}
        found = update_service.find_update({'tag_name': 'v9.9.9', 'assets': [asset]}, current='0.4.2')
        self.assertEqual((found['size'], found['sha256']), (1234, SHA))
        self.assertEqual(self.target.name, 'AkisKurguAI-Setup-9.9.9.exe')
        self.assertEqual(self.target.parent, self.folder)

    def test_verified_download_lands_in_place_without_partial(self):
        progress = []
        path = download(UPDATE, self.target, opener=opener_for(DATA), progress=lambda d, t: progress.append((d, t)))
        self.assertEqual(Path(path), self.target)
        self.assertEqual(self.target.read_bytes(), DATA)
        self.assertEqual(progress[-1], (len(DATA), len(DATA)))
        self.assertEqual([p.name for p in self.folder.iterdir()], [self.target.name])

    def test_hash_mismatch_deletes_partial(self):
        with self.assertRaises(ValueError):
            download(UPDATE, self.target, opener=opener_for(DATA + b'x'))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_cancel_deletes_partial(self):
        calls = iter([False, False, True])
        with self.assertRaises(DownloadCancelled):
            download(UPDATE, self.target, opener=opener_for(DATA), should_stop=lambda: next(calls))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_verified_existing_file_is_reused_and_tampered_one_replaced(self):
        self.folder.mkdir()
        self.target.write_bytes(DATA)
        unused = opener_for(DATA)
        download(UPDATE, self.target, opener=unused)
        unused.assert_not_called()
        self.target.write_bytes(b'tampered')
        download(UPDATE, self.target, opener=opener_for(DATA))
        self.assertEqual(self.target.read_bytes(), DATA)

    def test_cleanup_keeps_only_target_and_log(self):
        self.folder.mkdir()
        for name in ('AkisKurguAI-Setup-9.9.8.exe', 'AkisKurguAI-Setup-9.9.9.exe.part', 'install.log', self.target.name):
            (self.folder / name).write_bytes(b'x')
        removed = cleanup_update_dir(self.folder, keep=self.target)
        self.assertEqual(sorted(removed), ['AkisKurguAI-Setup-9.9.8.exe', 'AkisKurguAI-Setup-9.9.9.exe.part'])
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ['AkisKurguAI-Setup-9.9.9.exe', 'install.log'])
        cleanup_update_dir(self.folder)  # up to date: every installer is stale
        self.assertEqual([p.name for p in self.folder.iterdir()], ['install.log'])
        self.assertEqual(cleanup_update_dir(Path(self.tmp.name) / 'missing'), [])

    def test_legacy_temp_folders_removed_when_old(self):
        root = Path(self.tmp.name)
        old, fresh, other = root / 'akis_update_old', root / 'akis_update_new', root / 'something_else'
        for folder in (old, fresh, other):
            folder.mkdir()
            (folder / 'AkisKurguAI-Setup.exe').write_bytes(b'x')
        os.utime(old, (time.time() - 3 * 24 * 3600,) * 2)
        self.assertEqual(cleanup_legacy_temp(root), ['akis_update_old'])
        self.assertTrue(fresh.exists() and other.exists())


class LaunchVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.setup_file = root / 'AkisKurguAI-Setup-9.9.9.exe'
        self.setup_file.write_bytes(DATA)
        self.app = root / 'AkisKurguAI.exe'
        self.app.touch()

    def test_mismatch_aborts_before_spawning(self):
        runner = Mock()
        with self.assertRaises(ValueError) as caught:
            launch_installer(self.setup_file, self.app, 123, sha256='0' * 64, popen=runner)
        self.assertEqual(str(caught.exception), update_service.VERIFY_FAILED)
        runner.assert_not_called()
        with self.assertRaises(ValueError):
            launch_installer(self.setup_file, self.app, 123, sha256='not-a-hash', popen=runner)
        runner.assert_not_called()

    def test_helper_verifies_hash_right_before_start_process(self):
        runner = Mock()
        launch_installer(self.setup_file, self.app, 123, sha256=SHA.upper(), popen=runner)  # any case
        script = helper_script(runner.call_args.args[0])
        self.assertEqual(helper_payload(script)['sha256'], SHA)
        check = script.index('ComputeHash')
        compare = script.index('OrdinalIgnoreCase', check)
        start = script.index('Start-Process -FilePath $d.installer')
        self.assertLess(check, compare)
        self.assertLess(compare, start)
        self.assertIn("[IO.FileShare]::Read)", script)  # held open: no writer can swap the file meanwhile
        self.assertIn(update_service.VERIFY_FAILED.split(';')[0], script)
        self.assertNotIn('VERIFY_FAILED', script)


class DownloadWorkerTests(unittest.TestCase):
    def test_interruption_stops_download_and_deletes_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'AkisKurguAI-Setup-9.9.9.exe'
            started = threading.Event()
            events = []
            slow = FakeResponse(DATA * 8, delay=0.05)  # ~32 chunks: far longer than the interruption takes
            original_read = slow.read

            def read(size=-1):
                started.set()
                return original_read(size)
            slow.read = read
            with patch('akis.update_service.urllib.request.urlopen', return_value=slow):
                worker = UpdateDownloadWorker(UPDATE, str(target))
                worker.cancelled.connect(lambda: events.append('cancelled'))
                worker.completed.connect(lambda path: events.append('completed'))
                worker.start()
                self.assertTrue(started.wait(5))
                worker.requestInterruption()
                self.assertTrue(worker.wait(5000))
            QCoreApplication.processEvents()
            self.assertEqual(events, ['cancelled'])
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
