import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from akis.temp_cleanup import cleanup_stale_temp_dirs


class TempCleanupTests(unittest.TestCase):
    def test_removes_only_our_old_folders(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            now = time.time()
            old, fresh = now - 25 * 3600, now - 3600
            for name, age in (('akis_render_a', old), ('akis_proxy_b', old), ('akis_speed_c', old), ('akis_preview_d', old),
                              ('akis_render_new', fresh), ('other_old', old), ('akis_update_x', old)):
                folder = root / name
                folder.mkdir()
                (folder / 'f.txt').write_text('x')
                os.utime(folder, (age, age))
            stray = root / 'akis_render_file.txt'
            stray.write_text('not a folder')
            os.utime(stray, (old, old))
            removed = cleanup_stale_temp_dirs(root, now=now)
            self.assertEqual(sorted(removed), ['akis_preview_d', 'akis_proxy_b', 'akis_render_a', 'akis_speed_c'])
            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             ['akis_render_file.txt', 'akis_render_new', 'akis_update_x', 'other_old'])

    def test_errors_are_ignored(self):
        self.assertEqual(cleanup_stale_temp_dirs(Path(tempfile.gettempdir()) / 'does-not-exist-akis'), [])
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / 'akis_render_locked'
            folder.mkdir()
            os.utime(folder, (0, 0))
            with patch('shutil.rmtree', side_effect=PermissionError('in use')):
                self.assertEqual(cleanup_stale_temp_dirs(root), [])  # rmtree(ignore_errors) never raises; still safe
            self.assertTrue(folder.exists())


if __name__ == '__main__':
    unittest.main()
