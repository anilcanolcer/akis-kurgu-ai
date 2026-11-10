import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class InstallerManifestTests(unittest.TestCase):
    def test_uninstall_manifest_only_targets_packaged_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'package'
            nested = root / 'media$test'
            nested.mkdir(parents=True)
            (root / 'AkisKurguAI.exe').write_bytes(b'app')
            (nested / 'dep.dll').write_bytes(b'dep')
            output = Path(folder) / 'uninstall.nsh'
            subprocess.run([sys.executable, 'scripts/generate-nsis-uninstall.py', str(root), str(output)], check=True)
            data = output.read_text(encoding='utf-8-sig')
            self.assertIn('Delete "$INSTDIR\\AkisKurguAI.exe"', data)
            self.assertIn('Delete "$INSTDIR\\media$$test\\dep.dll"', data)
            self.assertIn('RMDir "$INSTDIR\\media$$test"', data)
            self.assertNotIn('RMDir /r', data)

if __name__ == '__main__':
    unittest.main()
