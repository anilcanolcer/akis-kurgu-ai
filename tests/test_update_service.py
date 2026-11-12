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
        # The installer reads the version from akis/__init__.py itself, and refuses a different /D value.
        self.assertIn('!searchparse /file "akis\\__init__.py" "__version__ = \'" APP_SOURCE_VERSION "\'"', nsi)
        self.assertRegex(nsi, r'(?m)^\s*!define PRODUCT_VERSION "\$\{APP_SOURCE_VERSION\}"')
        self.assertIn('!error "PRODUCT_VERSION ${PRODUCT_VERSION} does not match', nsi)
        self.assertEqual(re.search(r"__version__ = '([^']+)'",
                                   (Path(__file__).resolve().parents[1] / 'akis' / '__init__.py').read_text()).group(1),
                         akis.__version__)
    def test_new_verified_release(self):
        asset={'name':'AkisKurguAI-Setup.exe','browser_download_url':'https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/v0.3.2/AkisKurguAI-Setup.exe','digest':'sha256:'+'a'*64}
        self.assertEqual(find_update({'tag_name':'v0.3.2','assets':[asset]}, current='0.3.1')['version'],'v0.3.2')
        self.assertIsNone(find_update({'tag_name':'v0.3.1','assets':[asset]}, current='0.3.1'))
        self.assertIsNone(find_update({'tag_name':'v0.3.2','prerelease':True,'assets':[asset]}, current='0.3.1'))
        asset['browser_download_url']='https://example.com/setup.exe'
        with self.assertRaises(ValueError): find_update({'tag_name':'v0.3.2','assets':[asset]}, current='0.3.1')
    def test_installer_arguments_handle_spaces(self):
        with tempfile.TemporaryDirectory(prefix='akis update ') as temp:
            root = Path(temp)
            setup = root / 'Setup File.exe'; setup.touch()
            app = root / 'Program File.exe'; app.touch()
            runner = Mock(return_value=42)
            launch_installer(setup, app, 123, sha256=EMPTY_SHA256, start=runner)
            path, arguments, _ = runner.call_args.args
            self.assertEqual(Path(path), setup.resolve())
            self.assertIn(f'/DIR="{root.resolve()}"', arguments)
            self.assertIn('/LOG="', arguments)
            self.assertIn('/UPDATE', arguments)
            self.assertNotIn('/VERYSILENT', arguments)

    def test_version(self):
        self.assertIsNone(version_tuple('v0.3.2-beta'))
if __name__ == '__main__': unittest.main()
