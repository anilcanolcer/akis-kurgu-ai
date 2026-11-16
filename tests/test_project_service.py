import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akis import project_service


class ProjectServiceTests(unittest.TestCase):
    def test_migrate_save_and_load(self):
        old = {'format': 'akis-kurgu-project', 'version': 1,
               'state': {'source': 'test.mp4', 'start': 1, 'end': 3}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'project.json'
            project_service.save(path, old)
            result = project_service.load(path)
            self.assertEqual(result['version'], 2)
            self.assertEqual(result['timeline']['tracks'][0]['clips'][0]['source_in'], 30)
            self.assertEqual(result['state'], old['state'])

    def test_document_snapshot_and_relative_source(self):
        from akis.timeline_model import Timeline
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'video.mp4').touch()
            target = root / 'edit.akis.json'
            document = project_service.make_document({'source': 'video.mp4'}, Timeline(), {}, '')
            project_service.save_with_snapshot(target, document, snapshot=True)
            project_service.save_with_snapshot(target, document, snapshot=True)
            self.assertEqual(len(list((root / 'edit.akis.json.versions').glob('*.json'))), 2)
            loaded, source = project_service.load_with_source(target)
            self.assertEqual(Path(source), (root / 'video.mp4').resolve())
            self.assertEqual(loaded['state']['source'], str((root / 'video.mp4').resolve()))

    def test_reject_future_format(self):
        with self.assertRaises(ValueError):
            project_service.migrate({'format': 'akis-kurgu-project', 'version': 99})

    def test_failed_atomic_replace_preserves_previous_project(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'project.akis.json'
            target.write_bytes(b'previous project')
            document = {'format': 'akis-kurgu-project', 'version': 1,
                        'state': {'source': 'video.mp4', 'start': 0, 'end': 1}}
            with patch('akis.project_service.os.replace', side_effect=PermissionError(13, 'Access denied')):
                with self.assertRaises(PermissionError):
                    project_service.save(target, document)
            self.assertEqual(target.read_bytes(), b'previous project')
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_snapshot_failure_is_reported_after_main_project_is_saved(self):
        from akis.timeline_model import Timeline
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'project.akis.json'
            document = project_service.make_document({'source': 'video.mp4'}, Timeline(), {}, '')
            real_save = project_service.save

            def deny_snapshot(path, value):
                if Path(path).parent.name == f'{target.name}.versions':
                    raise PermissionError(13, 'Access denied')
                return real_save(path, value)

            with patch('akis.project_service.save', side_effect=deny_snapshot):
                result = project_service.save_with_snapshot(target, document, snapshot=True)
            self.assertFalse(result.snapshot_saved)
            self.assertIsInstance(result.snapshot_error, PermissionError)
            saved = project_service.load(target)
            self.assertEqual(saved['state']['source'], 'video.mp4')
            self.assertTrue(target.is_file())

    def test_atomic_replace_retries_transient_windows_sharing_violation(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'project.akis.json'
            target.write_bytes(b'previous project')
            document = {'format': 'akis-kurgu-project', 'version': 1,
                        'state': {'source': 'video.mp4', 'start': 0, 'end': 1}}
            real_replace = project_service.os.replace
            calls = []

            def sharing_lock_once(source, destination):
                calls.append((source, destination))
                if len(calls) < 3:
                    error = PermissionError(13, 'Access denied', str(destination))
                    error.winerror = 32
                    raise error
                return real_replace(source, destination)

            with patch('akis.project_service.os.replace', side_effect=sharing_lock_once), \
                 patch('akis.project_service.time.sleep') as sleep:
                project_service.save(target, document)
            self.assertEqual(len(calls), 3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.1])
            self.assertEqual(project_service.load(target)['state']['source'], 'video.mp4')

    def test_atomic_replace_does_not_retry_persistent_access_denial(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'project.akis.json'
            target.write_bytes(b'previous project')
            document = {'format': 'akis-kurgu-project', 'version': 1,
                        'state': {'source': 'video.mp4', 'start': 0, 'end': 1}}
            error = PermissionError(13, 'Access denied', str(target))
            error.winerror = 5
            with patch('akis.project_service.os.replace', side_effect=error) as replace, \
                 patch('akis.project_service._is_transient_delete_share_lock', return_value=False), \
                 patch('akis.project_service.time.sleep') as sleep:
                with self.assertRaises(PermissionError):
                    project_service.save(target, document)
            replace.assert_called_once()
            sleep.assert_not_called()
            self.assertEqual(target.read_bytes(), b'previous project')

    @unittest.skipUnless(__import__('sys').platform == 'win32', 'requires Windows file sharing semantics')
    def test_atomic_replace_waits_for_a_real_temporary_delete_sharing_lock(self):
        import ctypes
        import threading
        import time
        from ctypes import wintypes

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'project.akis.json'
            target.write_bytes(b'previous project')
            document = {'format': 'akis-kurgu-project', 'version': 1,
                        'state': {'source': 'video.mp4', 'start': 0, 'end': 1}}
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                              wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel32.CreateFileW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.CreateFileW(str(target), 0x80000000, 0x1 | 0x2, None, 3, 0, None)
            invalid = ctypes.c_void_p(-1).value
            self.assertNotEqual(handle, invalid, f'CreateFileW failed: {ctypes.get_last_error()}')
            released = threading.Event()

            def unlock_after_scan():
                time.sleep(0.12)
                kernel32.CloseHandle(handle)
                released.set()

            thread = threading.Thread(target=unlock_after_scan, daemon=True)
            thread.start()
            try:
                project_service.save(target, document)
            finally:
                if not released.is_set():
                    kernel32.CloseHandle(handle)
                thread.join(timeout=1)
            self.assertTrue(released.is_set())
            self.assertEqual(project_service.load(target)['state']['source'], 'video.mp4')


def project_with_media(folder, names=('video.mp4',), outside=None):
    from akis.timeline_model import Clip, Timeline, Track
    folder = Path(folder)
    (folder / 'media').mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = folder / 'media' / name
        path.touch()
        paths.append(str(path))
    if outside:
        paths.append(str(outside))
    clips, start = [], 0
    for path in paths:
        clips.append(Clip(path, start, 30))
        start += 30
    timeline = Timeline(tracks=[Track('video', 'Video', clips), Track('audio', 'Audio')])
    return project_service.make_document({'source': paths[0]}, timeline, {}, ''), paths


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_save_records_relative_paths_without_changing_the_version(self):
        outside = self.root / 'elsewhere.mp4'
        outside.touch()
        document, paths = project_with_media(self.root / 'proj', ('a.mp4', 'b.mp4'), outside)
        target = self.root / 'proj' / 'demo.akis.json'
        project_service.save(target, document)
        import json
        saved = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(saved['version'], 2)
        self.assertEqual(saved['relative_media'], {paths[0]: 'media/a.mp4', paths[1]: 'media/b.mp4'})
        self.assertEqual(saved['state']['source'], paths[0])  # absolute path kept for older versions
        self.assertNotIn('relative_media', document)  # caller's document untouched

    def test_moved_project_folder_opens_with_media_beside_it(self):
        import shutil
        document, paths = project_with_media(self.root / 'old', ('a.mp4', 'b.mp4'))
        project_service.save(self.root / 'old' / 'demo.akis.json', document)
        shutil.move(str(self.root / 'old'), str(self.root / 'new'))
        loaded, source, missing = project_service.load_project(self.root / 'new' / 'demo.akis.json')
        expected = [str((self.root / 'new' / 'media' / n).resolve()) for n in ('a.mp4', 'b.mp4')]
        self.assertEqual(missing, [])
        self.assertEqual(source, expected[0])
        self.assertEqual(loaded['state']['source'], expected[0])
        self.assertEqual([c['source'] for c in loaded['timeline']['tracks'][0]['clips']], expected)

    def test_missing_main_source_falls_back_to_timeline_video_and_lists_missing(self):
        gone = self.root / 'gone.mp4'
        gone.touch()
        document, paths = project_with_media(self.root / 'proj', ('a.mp4',), gone)
        document['state']['source'] = str(gone)
        project_service.save(self.root / 'proj' / 'demo.akis.json', document)
        gone.unlink()
        loaded, source, missing = project_service.load_project(self.root / 'proj' / 'demo.akis.json')
        self.assertEqual(source, paths[0])
        self.assertEqual(loaded['state']['source'], paths[0])
        self.assertEqual(missing, [str(gone)])

    def test_no_usable_video_still_refuses(self):
        document, paths = project_with_media(self.root / 'proj', ('a.mp4',))
        project_service.save(self.root / 'proj' / 'demo.akis.json', document)
        Path(paths[0]).unlink()
        with self.assertRaises(FileNotFoundError):
            project_service.load_project(self.root / 'proj' / 'demo.akis.json')


class VersionPruneTests(unittest.TestCase):
    def test_only_newest_snapshots_are_kept(self):
        from akis.timeline_model import Timeline
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'edit.akis.json'
            versions = Path(folder) / 'edit.akis.json.versions'
            versions.mkdir()
            for i in range(5):  # older snapshots from earlier sessions
                (versions / f'2020010{i}-000000-000000.json').write_text('{}', encoding='utf-8')
            document = project_service.make_document({'source': 'v.mp4'}, Timeline(), {}, '')
            project_service.save_with_snapshot(target, document, snapshot=True, keep=3)
            names = sorted(p.name for p in versions.glob('*.json'))
            self.assertEqual(len(names), 3)
            self.assertNotIn('20200100-000000-000000.json', names)
            self.assertFalse(any(n.startswith('2020010') and n < '20200103' for n in names))
            self.assertTrue(any(not n.startswith('2020') for n in names))  # the new snapshot survives

    def test_default_keeps_twenty(self):
        self.assertEqual(project_service.KEEP_VERSIONS, 20)

    def test_normalize_project_path(self):
        self.assertEqual(project_service.normalize_project_path('proje'), 'proje.akis.json')
        self.assertEqual(project_service.normalize_project_path('x.json'), 'x.akis.json')
        self.assertEqual(project_service.normalize_project_path('x.JSON'), 'x.akis.json')
        self.assertEqual(project_service.normalize_project_path('y.akis.json'), 'y.akis.json')


if __name__ == '__main__':
    unittest.main()
