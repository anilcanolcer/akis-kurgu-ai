import tempfile
import unittest
from pathlib import Path

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


if __name__ == '__main__':
    unittest.main()
