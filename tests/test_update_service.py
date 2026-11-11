import unittest
import base64
import tempfile
from pathlib import Path
from unittest.mock import Mock
import re
import akis
from akis import update_service
from akis.update_service import find_update, version_tuple, launch_installer

EMPTY_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'

class UpdateTests(unittest.TestCase):
    def test_version_single_source(self):
        self.assertEqual(update_service.VERSION, akis.__version__)
        nsi = (Path(__file__).resolve().parents[1] / 'installer.nsi').read_text(encoding='utf-8-sig')
        match = re.search(r'^\s*!define\s+PRODUCT_VERSION\s+"([^"]+)"', nsi, re.M)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), akis.__version__)
    def test_new_verified_release(self):
        asset={'name':'AkisKurguAI-Setup.exe','browser_download_url':'https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/v0.3.2/AkisKurguAI-Setup.exe','digest':'sha256:'+'a'*64}
        self.assertEqual(find_update({'tag_name':'v0.3.2','assets':[asset]}, current='0.3.1')['version'],'v0.3.2')
        self.assertIsNone(find_update({'tag_name':'v0.3.1','assets':[asset]}, current='0.3.1'))
        self.assertIsNone(find_update({'tag_name':'v0.3.2','prerelease':True,'assets':[asset]}, current='0.3.1'))
        asset['browser_download_url']='https://example.com/setup.exe'
        with self.assertRaises(ValueError): find_update({'tag_name':'v0.3.2','assets':[asset]}, current='0.3.1')
    def test_installer_helper_handles_spaces_and_reports_failure(self):
        with tempfile.TemporaryDirectory(prefix='akis update ') as temp:
            root = Path(temp)
            setup = root / 'Setup File.exe'; setup.touch()
            app = root / 'Program File.exe'; app.touch()
            runner = Mock()
            launch_installer(setup, app, 123, sha256=EMPTY_SHA256, popen=runner)
            command = runner.call_args.args[0]
            script = base64.b64decode(command[-1]).decode('utf-16le')
            self.assertIn('Wait-Process', script)
            self.assertIn('MessageBox', script)
            self.assertIn('/LOG=', script)
            self.assertIn('/DIR=', script)
            self.assertIn('-Verb RunAs', script)
            self.assertNotIn('/SUPPRESSMSGBOXES', script)
            import re, json
            encoded = re.search(r"FromBase64String\('([^']+)'\)", script).group(1)
            data = json.loads(base64.b64decode(encoded).decode('utf-8'))
            self.assertEqual(data['directory'], str(root.resolve()))
            self.assertEqual(data['app'], str(app.resolve()))
            self.assertEqual(data['pid'], 123)

    def test_version(self):
        self.assertIsNone(version_tuple('v0.3.2-beta'))
if __name__ == '__main__': unittest.main()
