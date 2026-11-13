"""Crash recovery, error reporting, proxy retry, stale AI results, overwrite prompts and portable projects."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import logging
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import PropertyMock, patch

from PySide6.QtWidgets import QApplication, QMessageBox

import main
from akis import project_service
from akis.preview_widget import ProxyPlayback
from akis.timeline_model import Clip, Timeline, Track
from main import EditState, ExceptionHook, MainWindow

app = QApplication.instance() or QApplication([])
YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


class WindowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.recovery = self.root / 'recovery'
        patch('akis.app_support.recovery_dir', return_value=self.recovery).start()
        patch('akis.media_service.MediaService.duration', return_value=2.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')  # independent of the language saved on, or used by, this machine
        self.addCleanup(self.close_window)
        self.preview = patch.object(self.window.preview, 'request').start()
        self.video = self.root / 'a.mp4'
        self.video.touch()

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def load(self):
        self.window.load_video(str(self.video))

    def save_as(self, path):
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(path), '')):
            self.window.save_project()


class AutosaveTests(WindowCase):
    def test_autosave_only_with_unsaved_changes(self):
        self.load()
        project = self.root / 'a.akis.json'
        self.save_as(project)
        self.assertFalse(self.window.autosave_project())
        self.assertFalse(Path(str(project) + '.autosave').exists())
        self.window.publish_title.setText('değişti')
        self.assertTrue(self.window.autosave_project())
        saved = json.loads(Path(str(project) + '.autosave').read_text(encoding='utf-8'))
        self.assertEqual(saved['publish']['title'], 'değişti')

    def test_autosave_failure_is_logged_and_reported(self):
        self.load()
        self.window.publish_title.setText('değişti')
        with patch.object(self.window, 'write_project', side_effect=OSError('disk dolu')), \
             self.assertLogs('akis', level='ERROR') as logs:
            self.assertFalse(self.window.autosave_project())
        self.assertIn('disk dolu', '\n'.join(logs.output))
        self.assertIn('Otomatik kayıt yapılamadı', self.window.status_label.text())

    def test_save_removes_autosave(self):
        self.load()
        project = self.root / 'a.akis.json'
        self.save_as(project)
        self.window.publish_title.setText('değişti')
        self.window.autosave_project()
        autosave = Path(str(project) + '.autosave')
        self.assertTrue(autosave.exists())
        self.window.save_project()
        self.assertFalse(autosave.exists())

    def test_untitled_recovery_is_removed_after_first_save(self):
        self.load()
        self.window.publish_title.setText('değişti')
        self.window.autosave_project()
        own = self.recovery / f'recovery-{os.getpid()}.akis.json'
        self.assertTrue(own.exists())
        self.save_as(self.root / 'a.akis.json')
        self.assertFalse(own.exists())
        self.assertIsNone(self.window._recovery_lock)

    def test_discard_and_clean_close_remove_autosave(self):
        self.load()
        self.window.publish_title.setText('değişti')
        self.window.autosave_project()
        own = self.recovery / f'recovery-{os.getpid()}.akis.json'
        with patch.object(self.window, 'isVisible', return_value=True), \
             patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.window.confirm_close())
        self.assertFalse(own.exists())
        self.window.autosave_project()
        self.assertTrue(own.exists())
        self.window.close()  # hidden window: no prompt, a clean close
        self.assertFalse(own.exists())

    def test_cancelled_close_keeps_autosave(self):
        self.load()
        self.window.publish_title.setText('değişti')
        self.window.autosave_project()
        own = self.recovery / f'recovery-{os.getpid()}.akis.json'
        with patch.object(self.window, 'isVisible', return_value=True), \
             patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.confirm_close())
        self.assertTrue(own.exists())


class ProjectRecoveryTests(WindowCase):
    def setUp(self):
        super().setUp()
        self.load()
        self.project = self.root / 'a.akis.json'
        self.save_as(self.project)
        self.window.publish_title.setText('kurtarılacak')
        self.window.autosave_project()
        self.autosave = Path(str(self.project) + '.autosave')
        past = time.time() - 60
        os.utime(self.project, (past, past))  # the autosave is newer than the project file
        # As after a crash and restart: the window shows the saved state and does not own the autosave.
        self.window.publish_title.setText('')
        self.window._autosave_file = ''
        self.window.mark_saved()

    def reopen(self, answer):
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(self.project), '')), \
             patch.object(self.window, 'ask_recovery', return_value=answer) as ask, \
             patch('main.QMessageBox.critical') as critical:
            self.window.open_project()
        critical.assert_not_called()
        return ask

    def test_accepting_loads_autosave_but_keeps_real_project_path(self):
        ask = self.reopen('open')
        ask.assert_called_once_with(self.autosave)
        w = self.window
        self.assertEqual(w.publish_title.text(), 'kurtarılacak')
        self.assertEqual(w.project_path, str(self.project))
        self.assertTrue(w.has_unsaved_changes())
        self.assertTrue(self.autosave.exists())  # still protects the recovered work until it is saved
        w.save_project()
        self.assertFalse(self.autosave.exists())
        saved = json.loads(self.project.read_text(encoding='utf-8'))
        self.assertEqual(saved['publish']['title'], 'kurtarılacak')

    def test_delete_removes_autosave_and_opens_project(self):
        self.reopen('delete')
        self.assertFalse(self.autosave.exists())
        self.assertEqual(self.window.publish_title.text(), '')
        self.assertFalse(self.window.has_unsaved_changes())

    def test_ask_later_keeps_autosave_and_does_not_open(self):
        self.window.publish_title.setText('açık olan')
        self.reopen('later')
        self.assertTrue(self.autosave.exists())
        self.assertEqual(self.window.publish_title.text(), 'açık olan')  # nothing was loaded
        self.assertIn('kurtarma dosyası saklandı', self.window.status_label.text())

    def test_older_autosave_is_not_offered(self):
        future = time.time() + 60
        os.utime(self.project, (future, future))
        ask = self.reopen('open')
        ask.assert_not_called()
        self.assertFalse(self.autosave.exists())


class UntitledRecoveryTests(WindowCase):
    def orphan(self, pid=999_999_9, title='yetim'):
        self.recovery.mkdir(parents=True, exist_ok=True)
        timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(self.video), 0, 60)])])
        document = project_service.make_document(asdict(EditState(source=str(self.video))), timeline,
                                                 {'title': title, 'caption': '', 'hashtags': ''}, '')
        path = self.recovery / f'recovery-{pid}.akis.json'
        project_service.save(path, document)
        return path

    def test_accepting_orphan_loads_it_untitled_and_unsaved(self):
        orphan = self.orphan()
        with patch.object(self.window, 'ask_recovery', return_value='open') as ask:
            self.assertTrue(self.window.offer_recovery())
        ask.assert_called_once_with(orphan)
        w = self.window
        self.assertEqual(w.publish_title.text(), 'yetim')
        self.assertEqual(w.project_path, '')
        self.assertTrue(w.has_unsaved_changes())
        self.assertFalse(orphan.exists())
        self.assertTrue((self.recovery / f'recovery-{os.getpid()}.akis.json').exists())  # now our own copy
        self.assertFalse((self.recovery / f'recovery-{999_999_9}.lock').exists())

    def test_delete_removes_orphan(self):
        orphan = self.orphan()
        with patch.object(self.window, 'ask_recovery', return_value='delete'):
            self.assertFalse(self.window.offer_recovery())
        self.assertFalse(orphan.exists())
        self.assertFalse(self.window.has_unsaved_changes())

    def test_ask_later_keeps_orphan_for_the_next_launch(self):
        orphan = self.orphan()
        with patch.object(self.window, 'ask_recovery', return_value='later'):
            self.assertFalse(self.window.offer_recovery())
        self.assertTrue(orphan.exists())
        found = main.orphan_recovery_files(self.recovery)  # its lock was released: offered again
        self.assertEqual([path for path, _lock in found], [orphan])
        for _path, lock in found:
            lock.unlock()

    def test_prompt_shows_date_and_three_choices(self):
        orphan = self.orphan()
        stamp = time.mktime((2026, 3, 4, 15, 7, 0, 0, 0, -1))
        os.utime(orphan, (stamp, stamp))
        seen = []

        def click(label):
            def exec_(box):
                seen.append((box.text(), [b.text() for b in box.buttons()]))
                next(b for b in box.buttons() if b.text() == label).click()
                return 0
            return exec_

        for label, expected in (('Aç', 'open'), ('Sonra sor', 'later'), ('Sil', 'delete')):
            with patch.object(QMessageBox, 'exec', new=click(label)):
                self.assertEqual(self.window.ask_recovery(orphan), expected)
        text, buttons = seen[0]
        self.assertIn('04.03.2026 15:07', text)
        self.assertEqual(sorted(buttons), sorted(['Aç', 'Sonra sor', 'Sil']))
        with patch.object(QMessageBox, 'exec', new=lambda box: 0):  # closed without a choice
            self.assertEqual(self.window.ask_recovery(orphan), 'later')
        self.assertTrue(orphan.exists())

    def test_file_of_running_instance_is_not_offered(self):
        orphan = self.orphan(pid=4242)
        live = main.recovery_lock(orphan)
        self.assertTrue(live.tryLock(0))  # held by a running process (this one)
        self.addCleanup(live.unlock)
        with patch.object(self.window, 'ask_recovery') as ask:
            self.assertFalse(self.window.offer_recovery())
        ask.assert_not_called()
        self.assertTrue(orphan.exists())

    def test_two_instances_use_different_files(self):
        self.load()
        self.window.publish_title.setText('x')
        self.window.autosave_project()
        self.assertEqual(Path(self.window._autosave_file).name, f'recovery-{os.getpid()}.akis.json')
        self.assertEqual(main.orphan_recovery_files(self.recovery), [])  # our own file is never an orphan


class ErrorReportingTests(unittest.TestCase):
    def test_hook_logs_and_shows_one_dialog_without_reentry(self):
        hook = ExceptionHook(Path('akis.log'), show_dialogs=True)
        calls = []

        def critical(*args):
            calls.append(args)
            try:
                raise RuntimeError('ikinci')
            except RuntimeError as inner:
                hook(type(inner), inner, inner.__traceback__)  # error while the message is up

        with patch('main.QMessageBox.critical', side_effect=critical), self.assertLogs('akis', 'CRITICAL') as logs:
            try:
                raise ValueError('patladı')
            except ValueError as exc:
                hook(type(exc), exc, exc.__traceback__)
        self.assertEqual(len(calls), 1)
        self.assertIn('patladı', calls[0][2])
        self.assertTrue(any('patladı' in line for line in logs.output))
        self.assertTrue(any('ikinci' in line for line in logs.output))

    def test_automated_hook_only_logs(self):
        hook = ExceptionHook(None, show_dialogs=False)
        with patch('main.QMessageBox.critical') as critical, self.assertLogs('akis', 'CRITICAL'):
            hook(ValueError, ValueError('x'), None)
        critical.assert_not_called()

    def test_setup_logging_writes_rotating_log_and_crash_log(self):
        import faulthandler
        with tempfile.TemporaryDirectory() as folder:
            saved = main._log_handler, main._crash_log
            level = logging.getLogger().level
            self.addCleanup(logging.getLogger().setLevel, level)
            main._log_handler = main._crash_log = None
            try:
                log_path = main.setup_logging(Path(folder))
                logging.getLogger('akis').error('deneme kaydı')
                main._log_handler.flush()
                self.assertIn('deneme kaydı', log_path.read_text(encoding='utf-8'))
                self.assertTrue((Path(folder) / 'crash.log').exists())
                self.assertTrue(faulthandler.is_enabled())
            finally:
                logging.getLogger().removeHandler(main._log_handler)
                main._log_handler.close()
                faulthandler.disable()
                main._crash_log.close()
                main._log_handler, main._crash_log = saved


class CanvasErrorTests(WindowCase):
    def source_ratio_without_video(self):
        w = self.window
        w.state.source, w.state.duration = str(self.video), 2.0
        w.multitrack = Timeline(tracks=[Track('video', 'Video'), Track('text', 'Text', [Clip('', 0, 30, text='Merhaba')])])
        w.multitrack_view.set_model(w.multitrack)
        blocked = w.aspect.blockSignals(True)
        w.select_choice(w.aspect, 'Kaynak oranı')
        w.aspect.blockSignals(blocked)

    def test_export_reports_instead_of_raising(self):
        self.source_ratio_without_video()
        with patch('main.QMessageBox.warning') as warning, patch('akis.window.exporting.TimelineRenderWorker') as worker, \
             patch('PySide6.QtWidgets.QFileDialog.getSaveFileName') as dialog:
            self.window.export_video()
        warning.assert_called_once()
        worker.assert_not_called()
        dialog.assert_not_called()

    def test_element_at_and_proxy_signature_fail_gracefully(self):
        self.source_ratio_without_video()
        self.assertIsNone(self.window.element_at(0.5, 0.78))
        self.assertIn('Önizleme boyutu', self.window.status_label.text())
        self.assertIsNone(self.window.proxy_signature())
        with patch.object(self.window.proxy, 'prepare') as prepare:
            self.window.prepare_proxy()
        prepare.assert_not_called()


class ProxyRetryTests(WindowCase):
    def test_failure_blocks_only_that_signature(self):
        self.load()
        w = self.window
        with patch.object(ProxyPlayback, 'available', new_callable=PropertyMock, return_value=True), \
             patch.object(w.proxy, 'prepare') as prepare:
            w.prepare_proxy()
            self.assertEqual(prepare.call_count, 1)
            w.on_proxy_failed('kodlayıcı yok')
            self.assertIn('Akıcı önizleme kullanılamadı', w.status_label.text())
            w.prepare_proxy()
            self.assertEqual(prepare.call_count, 1)  # the same edit is not re-rendered
            self.assertFalse(w.proxy_usable())
            w.brightness.setValue(10)  # any change to the edit
            self.assertTrue(w.proxy_usable())
            w.prepare_proxy()
            self.assertEqual(prepare.call_count, 2)


class StalePlanTests(WindowCase):
    def run_prompt(self, change, answer):
        self.load()
        w = self.window
        w._prompt_revision = w.timeline_revision()
        if change:
            w.multitrack.tracks[2].add(Clip('', 0, 10, text='kullanıcı'))
        result = Timeline(tracks=[Track('video', 'Video', [Clip(str(self.video), 0, 15)])])
        with patch('main.QMessageBox.question', return_value=answer) as ask, \
             patch('akis.edit_plan.apply_plan', return_value=result) as apply, \
             patch('akis.edit_plan.describe', return_value='özet'):
            w.on_prompt_edit({}, [(str(self.video), 2.0)])
        return ask, apply, result

    def test_unchanged_timeline_applies_without_asking(self):
        ask, apply, result = self.run_prompt(False, NO)
        ask.assert_not_called()
        self.assertIs(self.window.multitrack, result)

    def test_changed_timeline_asks_and_keeps_user_edits_on_no(self):
        ask, apply, result = self.run_prompt(True, NO)
        self.assertEqual(ask.call_args.args[2], main.STALE_PLAN_QUESTION)
        apply.assert_not_called()
        self.assertTrue(any(c.text == 'kullanıcı' for t in self.window.multitrack.tracks for c in t.clips))
        self.assertEqual(self.window._undo_stack, [])

    def test_changed_timeline_applies_on_yes(self):
        ask, apply, result = self.run_prompt(True, YES)
        ask.assert_called_once()
        self.assertIs(self.window.multitrack, result)
        self.assertEqual(len(self.window._undo_stack), 1)


class OverwritePromptTests(WindowCase):
    def test_save_name_without_extension_asks_before_overwriting(self):
        self.load()
        existing = self.root / 'proje.akis.json'
        existing.write_text('eski', encoding='utf-8')
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(self.root / 'proje'), '')), \
             patch('main.QMessageBox.question', return_value=NO) as ask:
            self.window.save_project()
        ask.assert_called_once()
        self.assertEqual(existing.read_text(encoding='utf-8'), 'eski')
        self.assertEqual(self.window.project_path, '')
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(self.root / 'proje'), '')), \
             patch('main.QMessageBox.question', return_value=YES):
            self.window.save_project()
        self.assertEqual(self.window.project_path, str(existing))
        self.assertEqual(json.loads(existing.read_text(encoding='utf-8'))['format'], 'akis-kurgu-project')

    def test_json_name_becomes_akis_json_and_confirmed_name_is_not_asked_again(self):
        self.load()
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(self.root / 'x.json'), '')), \
             patch('main.QMessageBox.question') as ask:
            self.window.save_project()
        ask.assert_not_called()
        self.assertEqual(self.window.project_path, str(self.root / 'x.akis.json'))
        self.assertFalse((self.root / 'x.json.akis.json').exists())

    def test_export_name_without_extension_asks_before_overwriting(self):
        self.load()
        (self.root / 'klip.mp4').write_bytes(b'eski')
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(self.root / 'klip'), '')), \
             patch('main.QMessageBox.question', return_value=NO) as ask, \
             patch('akis.window.exporting.TimelineRenderWorker') as worker:
            self.window.export_video()
        ask.assert_called_once()
        worker.assert_not_called()

    def test_export_path_normalisation(self):
        self.assertEqual(main.normalize_export_path('a/klip'), 'a/klip.mp4')
        self.assertEqual(main.normalize_export_path('klip.MP4'), 'klip.MP4')
        self.assertEqual(Path(main.normalize_export_path('klip.mov')).name, 'klip.mp4')


class PortableOpenTests(WindowCase):
    def test_missing_main_source_opens_with_one_warning(self):
        gone = self.root / 'gone.mp4'
        timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(self.video), 0, 60)]),
                                    Track('audio', 'Audio', [Clip(str(self.root / 'müzik.wav'), 0, 30)])])
        document = project_service.make_document(asdict(EditState(source=str(gone))), timeline,
                                                 {'title': 'taşındı', 'caption': '', 'hashtags': ''}, '')
        project = self.root / 'p.akis.json'
        project_service.save(project, document)
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(project), '')), \
             patch('main.QMessageBox.warning') as warning, patch('main.QMessageBox.critical') as critical:
            self.window.open_project()
        critical.assert_not_called()
        warning.assert_called_once()
        text = warning.call_args.args[2]
        self.assertIn(str(gone), text)
        self.assertIn('müzik.wav', text)
        self.assertEqual(self.window.project_path, str(project))
        self.assertEqual(self.window.state.source, str(self.video))
        self.assertEqual(self.window.publish_title.text(), 'taşındı')


if __name__ == '__main__':
    unittest.main()
