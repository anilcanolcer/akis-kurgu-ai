"""Main-window update flow: ask before downloading, fixed folder, postponing, bounded close, verified launch.

Nothing touches the network or starts a process: workers and the installer launch are faked.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

import main
from akis import update_service
from main import MainWindow

app = QApplication.instance() or QApplication([])
YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
SHA = 'ab' * 32
UPDATE = {'version': 'v9.9.9', 'url': update_service.DOWNLOAD_PREFIX + 'v9.9.9/AkisKurguAI-Setup.exe',
          'sha256': SHA, 'size': 150 * 1024 * 1024}


class UpdateFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('main.recovery_dir', return_value=self.root / 'recovery').start()
        patch('main.app_data_dir', return_value=self.root / 'appdata').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        # A throwaway settings file: postponing must not write into this machine's real settings.
        self.window.settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        self.addCleanup(self.close)
        self.folder = self.root / 'appdata' / 'updates'

    def close(self):
        self.window._close_confirmed = True
        self.window.close()

    def offer(self, answer):
        with patch('main.QMessageBox.question', return_value=answer) as ask, \
             patch('main.UpdateDownloadWorker') as worker:
            self.window.offer_update(dict(UPDATE))
        return ask, worker

    def test_asks_with_size_before_downloading_into_fixed_folder(self):
        self.folder.mkdir(parents=True)
        (self.folder / 'AkisKurguAI-Setup-9.9.8.exe').write_bytes(b'old')
        (self.folder / 'AkisKurguAI-Setup-9.9.9.exe.part').write_bytes(b'partial')
        ask, worker = self.offer(YES)
        ask.assert_called_once()
        self.assertIn('v9.9.9', ask.call_args.args[2])
        self.assertIn('150.0 MB', ask.call_args.args[2])
        target = self.folder / 'AkisKurguAI-Setup-9.9.9.exe'
        worker.assert_called_once_with(UPDATE, str(target))
        worker.return_value.start.assert_called_once()
        self.assertEqual(list(self.folder.iterdir()), [])  # stale installer and partial download gone

    def test_declined_update_is_not_downloaded_or_offered_again(self):
        ask, worker = self.offer(NO)
        worker.assert_not_called()
        self.assertTrue(self.window.update_postponed('v9.9.9'))
        ask, worker = self.offer(YES)
        ask.assert_not_called()
        worker.assert_not_called()
        # A new window (next launch) within the reminder period does not ask either...
        self.window._declined_updates.clear()
        self.assertTrue(self.window.update_postponed('v9.9.9'))
        self.assertFalse(self.window.update_postponed('v9.9.10'))
        # ...but does once it has passed.
        with patch('main.time.time', return_value=time.time() + main.UPDATE_REMIND_AFTER + 1):
            self.assertFalse(self.window.update_postponed('v9.9.9'))

    def test_up_to_date_check_removes_every_downloaded_installer(self):
        self.folder.mkdir(parents=True)
        (self.folder / 'AkisKurguAI-Setup-9.9.9.exe').write_bytes(b'x')
        with patch('main.UpdateCheckWorker') as check, patch('main.update_service.cleanup_legacy_temp') as legacy:
            self.window.check_for_updates()
        legacy.assert_called_once()
        check.return_value.start.assert_called_once()
        check.return_value.up_to_date.connect.call_args.args[0]()  # the check reports "up to date"
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_close_interrupts_download_with_bounded_wait(self):
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = False  # still blocked on a slow link
        self.window.update_download = thread
        self.close()
        thread.requestInterruption.assert_called_once()
        thread.wait.assert_called_once_with(main.THREAD_STOP_WAIT_MS)
        self.assertIn(thread, main._background_threads)
        main._background_threads.remove(thread)
        self.assertTrue(self.window._shutting_down)
        with patch('main.QMessageBox.question') as ask:
            self.window.install_update('late.exe')  # a download finishing after close does nothing
        ask.assert_not_called()

    def test_install_passes_expected_hash_and_handles_mismatch(self):
        self.window._update = dict(UPDATE)
        installer = self.root / 'AkisKurguAI-Setup-9.9.9.exe'
        installer.write_bytes(b'x')
        with patch('main.QMessageBox.question', return_value=YES), \
             patch('main.update_service.launch_installer', side_effect=ValueError(update_service.VERIFY_FAILED)) as launch, \
             patch('main.QMessageBox.critical') as critical:
            self.window.install_update(str(installer))
        self.assertEqual(launch.call_args.kwargs['sha256'], SHA)
        critical.assert_called_once()
        self.assertFalse(installer.exists())  # a file that failed verification is not kept
        self.assertFalse(self.window._shutting_down)

        installer.write_bytes(b'x')
        with patch('main.QMessageBox.question', return_value=YES), \
             patch('main.update_service.launch_installer') as launch:
            self.window.install_update(str(installer))
        launch.assert_called_once()
        self.assertTrue(self.window._shutting_down)  # the window closed for the installer

    def test_declining_install_postpones_and_keeps_verified_file(self):
        self.window._update = dict(UPDATE)
        installer = self.root / 'AkisKurguAI-Setup-9.9.9.exe'
        installer.write_bytes(b'x')
        with patch('main.QMessageBox.question', return_value=NO), \
             patch('main.update_service.launch_installer') as launch:
            self.window.install_update(str(installer))
        launch.assert_not_called()
        self.assertTrue(installer.exists())
        self.assertTrue(self.window.update_postponed('v9.9.9'))


if __name__ == '__main__':
    unittest.main()
