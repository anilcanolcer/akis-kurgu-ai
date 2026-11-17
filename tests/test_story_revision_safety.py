"""Regression coverage for cancelled preparation and stale story responses."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import ai_providers, privacy_log, story_service as ss
from akis.story_dialog import StoryDialog
from akis.story_workers import ImageWorker, VideoWorker
from tests.test_story_dialog import Collector, wait_until, text_response

app = QApplication.instance() or QApplication([])


class StorySafetyTests(unittest.TestCase):
    def test_cancel_during_image_preparation_never_starts_provider(self):
        for kind in ('image', 'video'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                started, release = threading.Event(), threading.Event()
                calls = []

                def prepare(*args):
                    started.set()
                    release.wait(5)
                    return object()

                target = Path(folder) / 'generated.bin'
                options = dict(transport=lambda *args: calls.append(args))
                if kind == 'image':
                    worker = ImageWorker('key', 'model', 'prompt', lambda _: target,
                                         references=[('reference.png', 'object', 'reference')], **options)
                else:
                    worker = VideoWorker('key', 'model', 'prompt', lambda _: target,
                                         image_path='reference.png', **options)
                collector = Collector(worker)
                with patch('akis.gemini_api.load_image', side_effect=prepare):
                    worker.start()
                    try:
                        self.assertTrue(started.wait(2))
                        worker.cancel()
                    finally:
                        release.set()
                    self.assertTrue(wait_until(worker.isFinished))
                    self.assertTrue(wait_until(lambda: collector.final()))
                self.assertEqual(collector.final(), [('cancelled', None)])
                self.assertEqual(calls, [])
                self.assertFalse(target.exists())

    def test_rewrite_preserves_edits_made_while_request_is_pending(self):
        started, release = threading.Event(), threading.Event()

        def transport(*args):
            started.set()
            release.wait(5)
            return text_response('generated rewrite')

        with tempfile.TemporaryDirectory() as folder:
            dialog = StoryDialog(api_key='key', output_dir=folder,
                                 add_media=lambda _: True, transport=transport)
            scene = ss.Scene(title='Scene', text='original text')
            dialog.state.scenes = [scene]
            dialog.refresh_scene_list(scene.id)
            dialog.auto_memory.setChecked(False)
            dialog.rewrite_scene()
            try:
                self.assertTrue(started.wait(2))
                dialog.scene_text.setPlainText('edited while pending')
                release.set()
                self.assertTrue(wait_until(lambda: dialog.worker is None))
                self.assertEqual(scene.text, 'edited while pending')
                self.assertEqual(dialog.scene_text.toPlainText(), 'edited while pending')
                self.assertIn('düzenlemeleriniz korundu', dialog.status_label.text())
            finally:
                release.set()
                if dialog.worker:
                    dialog.worker.cancel()
                    wait_until(lambda: dialog.worker is None)
                dialog.close()

    def test_bible_generation_preserves_pending_editor_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = StoryDialog(api_key='key', output_dir=folder, add_media=lambda _: True)
            callbacks = []
            try:
                dialog.start = lambda worker, done: callbacks.append(done) or True
                dialog.premise.setPlainText('original premise')
                dialog.generate_bible()
                dialog.premise.setPlainText('new premise')
                callbacks[0](type('Result', (), {'text': '{}', 'usage': {}, 'model': 'model'})())
                self.assertEqual(dialog.premise.toPlainText(), 'new premise')
                self.assertEqual(dialog.state.bible.premise, 'new premise')
            finally:
                dialog.close()


class PrivacyValidationTests(unittest.TestCase):
    def setUp(self):
        privacy_log.clear()
        self.addCleanup(privacy_log.clear)

    def test_invalid_cloudflare_credentials_are_not_logged_as_sent(self):
        with patch('akis.ai_providers.post_json') as post:
            with self.assertRaises(ValueError):
                ai_providers.request_plan('Cloudflare', 'invalid', '@cf/model', 'prompt', [(0, b'jpeg')])
        post.assert_not_called()
        self.assertEqual(privacy_log.sent(), [])

    def test_oversized_gemini_audio_is_not_logged_as_sent(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'audio.mp3'
            source.write_bytes(b'0' * 14_000_001)
            with patch('akis.ai_providers.post_json') as post:
                with self.assertRaises(ValueError):
                    ai_providers.transcribe('Gemini', 'key', 'model', source)
            post.assert_not_called()
        self.assertEqual(privacy_log.sent(), [])


if __name__ == '__main__':
    unittest.main()
