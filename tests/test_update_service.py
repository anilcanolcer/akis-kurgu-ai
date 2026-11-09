import unittest
from akis.update_service import find_update, version_tuple

class UpdateTests(unittest.TestCase):
    def test_new_verified_release(self):
        asset={'name':'AkisKurguAI-Setup.exe','browser_download_url':'https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/v0.3.2/AkisKurguAI-Setup.exe','digest':'sha256:'+'a'*64}
        self.assertEqual(find_update({'tag_name':'v0.3.2','assets':[asset]}, current='0.3.1')['version'],'v0.3.2')
        self.assertIsNone(find_update({'tag_name':'v0.3.1','assets':[asset]}, current='0.3.1'))
        self.assertIsNone(find_update({'tag_name':'v0.3.2','prerelease':True,'assets':[asset]}, current='0.3.1'))
        asset['browser_download_url']='https://example.com/setup.exe'
        with self.assertRaises(ValueError): find_update({'tag_name':'v0.3.2','assets':[asset]}, current='0.3.1')
    def test_version(self):
        self.assertIsNone(version_tuple('v0.3.2-beta'))
if __name__ == '__main__': unittest.main()
