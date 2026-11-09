import tempfile
import unittest
from pathlib import Path

import project_service


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

    def test_reject_future_format(self):
        with self.assertRaises(ValueError):
            project_service.migrate({'format': 'akis-kurgu-project', 'version': 99})


if __name__ == '__main__':
    unittest.main()
