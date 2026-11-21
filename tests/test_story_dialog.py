"""Story workers' signals and a Hikâye Stüdyosu smoke test (fake transports, no network, no key store)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import base64
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from akis import story_service as ss, story_workers
from akis.story_dialog import StoryDialog
from akis.story_workers import ImageWorker, TextWorker, VideoWorker

app = QApplication.instance() or QApplication([])


def png_bytes():
    image = QImage(16, 9, QImage.Format.Format_RGB32)
    image.fill(0x336699)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(data)


PNG = png_bytes()


def text_response(text):
    return {'candidates': [{'content': {'parts': [{'text': text}]}, 'finishReason': 'STOP'}],
            'usageMetadata': {'promptTokenCount': 1200, 'candidatesTokenCount': 300, 'thoughtsTokenCount': 200}}


def fake_transport(calls):
    def transport(url, headers, body):
        calls.append((url, body))
        if url.endswith('/interactions'):
            return {'id': 'v1', 'status': 'completed', 'steps': [{'type': 'model_output', 'content': [
                {'type': 'video', 'mime_type': 'video/mp4', 'data': base64.b64encode(b'MP4DATA').decode()}]}]}
        if 'responseModalities' in json.dumps(body.get('generationConfig', {})):
            return {'candidates': [{'content': {'parts': [{'inlineData': {'mimeType': 'image/png',
                                                                          'data': base64.b64encode(PNG).decode()}}]}}]}
        task = body['contents'][-1]['parts'][-1]['text']
        if 'Hikâye rehberi oluştur' in task:
            return text_response(json.dumps({'title': 'Fener', 'art_style': 'muted film still', 'characters': [
                {'name': 'Elif', 'visual': 'girl with a long dark braid and navy sweater'}], 'outline': ['a', 'b']}))
        if 'Hafızayı güncelle' in task:
            return text_response('{"scene_summary": "Elif feneri bulur.", "rolling_summary": "Elif yalnız."}')
        if 'Görsel ve hareket istemi' in task:
            return text_response(json.dumps({'characters': ['Elif'], 'image_prompt': 'A girl at a lighthouse door',
                                             'motion_prompt': 'Slow push-in; wind and gulls.'}))
        return text_response('Elif fenerin kapısını itti. İçerisi soğuktu.')
    return transport


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(10)
    return condition()


class Collector:
    def __init__(self, worker):
        self.events = []
        worker.completed.connect(lambda r: self.events.append(('completed', r)))
        worker.failed.connect(lambda m: self.events.append(('failed', m)))
        worker.cancelled.connect(lambda: self.events.append(('cancelled', None)))
        worker.status.connect(lambda s: self.events.append(('status', s)))

    def final(self):
        return [e for e in self.events if e[0] in ('completed', 'failed', 'cancelled')]


def run(worker):
    collector = Collector(worker)
    worker.start()
    assert wait_until(lambda: collector.final() and worker.isFinished())
    QTest.qWait(10)
    return collector


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def test_text_worker_completed_and_failed(self):
        state = ss.StoryState()
        job = ss.next_scene_job(state)
        events = run(TextWorker(job, 'k', fake_transport([]))).final()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], 'completed')
        self.assertIn('Elif', events[0][1].text)

        def broken(url, headers, body):
            raise RuntimeError('Gemini API hatası: HTTP 400')
        events = run(TextWorker(job, 'k', broken)).final()
        self.assertEqual(events, [('failed', 'Gemini API hatası: HTTP 400')])

    def test_cancel_discards_result_and_writes_nothing(self):
        release = threading.Event()

        def slow(url, headers, body):
            release.wait(5)
            return {'candidates': [{'content': {'parts': [{'inlineData': {'mimeType': 'image/png',
                                                                          'data': base64.b64encode(PNG).decode()}}]}}]}
        target = self.folder / 'x.png'
        worker = ImageWorker('k', 'gemini-nano-banana-2.1', 'a lighthouse', lambda ext: target, transport=slow)
        collector = Collector(worker)
        worker.start()
        QTest.qWait(50)
        worker.cancel()
        self.assertTrue(wait_until(worker.isFinished, 2.0))  # ends while the call is still blocked
        release.set()
        QTest.qWait(50)
        self.assertEqual(collector.final(), [('cancelled', None)])
        self.assertFalse(target.exists())

    def test_image_and_video_workers_write_files(self):
        events = run(ImageWorker('k', 'gemini-nano-banana-2.1', 'a lighthouse', lambda ext: self.folder / f'g{ext}',
                                 transport=fake_transport([]))).final()
        self.assertEqual(events[0][0], 'completed')
        self.assertEqual(Path(events[0][1]['path']).read_bytes(), PNG)
        calls = []
        events = run(VideoWorker('k', 'gemini-omni-1.2-flash', 'push in', lambda ext: self.folder / f'v{ext}',
                                 image_path=events[0][1]['path'], duration=5, transport=fake_transport(calls))).final()
        self.assertEqual(events[0][0], 'completed')
        self.assertEqual(Path(events[0][1]['path']).name, 'v.mp4')
        self.assertEqual(Path(events[0][1]['path']).read_bytes(), b'MP4DATA')
        self.assertEqual(calls[0][1]['input'][0]['type'], 'image')

    def test_validation_error_is_failed_not_crash(self):
        events = run(ImageWorker('k', 'gemini-nano-banana-2.1', 'x', lambda ext: self.folder / 'n.png',
                                 references=[(str(self.folder / 'missing.png'), 'character', 'Elif')],
                                 transport=fake_transport([]))).final()
        self.assertEqual(events[0][0], 'failed')


class DialogSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.calls, self.added = [], []
        self.dialog = StoryDialog(api_key=lambda: 'test-key', output_dir=lambda: str(self.folder),
                                  add_media=self.added.append, default_aspect='9:16 · Reels / Shorts',
                                  transport=fake_transport(self.calls))
        self.addCleanup(self.dialog.close)

    def idle(self):
        self.assertTrue(wait_until(lambda: self.dialog.worker is None))
        QTest.qWait(10)

    def test_invalid_character_list_does_not_replace_the_guide(self):
        dialog = self.dialog
        dialog.state.bible.title = 'Original'
        dialog.bible_editor.setPlainText('{"title": "Broken", "characters": 42}')
        self.assertFalse(dialog.apply_bible_editor())
        self.assertEqual(dialog.state.bible.title, 'Original')

    def test_save_applies_manual_guide_edits_and_keeps_invalid_edits_dirty(self):
        path = self.folder / 'story.json'
        self.dialog.bible_editor.setPlainText('{"title":"Yolculuk"}')
        self.assertTrue(self.dialog.save_story(str(path)))
        self.assertEqual(ss.load_story(path).bible.title, 'Yolculuk')
        self.dialog.bible_editor.setPlainText('{"characters":')
        self.assertFalse(self.dialog.save_story(str(path)))
        self.assertTrue(self.dialog.is_dirty())
        self.assertEqual(ss.load_story(path).bible.title, 'Yolculuk')

    def test_failed_open_after_discard_keeps_current_story_dirty(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        dialog = self.dialog
        dialog.premise.setPlainText('Unsaved premise')
        self.assertTrue(dialog.is_dirty())
        with patch.object(dialog, 'can_ask', return_value=True), \
                patch.object(dialog, 'ask', return_value=QMessageBox.StandardButton.Discard):
            self.assertFalse(dialog.open_story(str(self.folder / 'missing.json')))
        self.assertEqual(dialog.premise.toPlainText(), 'Unsaved premise')
        self.assertTrue(dialog.is_dirty())

    def test_text_image_video_pass(self):
        d = self.dialog
        self.assertEqual(d.image_aspect.currentText(), '9:16')
        self.assertEqual(d.video_aspect.currentText(), '9:16')
        d.premise.setPlainText('Bir fener bekçisinin kızı kayıp babasını arar.')
        d.generate_bible()
        self.idle()
        self.assertEqual(d.state.bible.title, 'Fener')
        self.assertIn('navy sweater', d.bible_editor.toPlainText())

        d.write_scene()
        self.idle()  # scene, then the automatic memory update
        self.assertEqual(len(d.state.scenes), 1)
        self.assertIn('Elif', d.scene_text.toPlainText())
        self.assertEqual(d.state.rolling_summary, 'Elif yalnız.')
        self.assertIn('Token:', d.usage_label.text())
        text_bodies = [b for u, b in self.calls if ':generateContent' in u and 'contents' in b and
                       'responseModalities' not in json.dumps(b)]
        self.assertTrue(all('temperature' not in json.dumps(b) and b['generationConfig']['thinkingConfig']
                            for b in text_bodies))

        d.extract_visual()
        self.idle()
        self.assertIn('navy sweater', d.visual_prompt.toPlainText())
        self.assertIn('Tahmini maliyet', d.cost_label.text())

        d.generate_image()
        self.idle()
        scene = d.state.scenes[0]
        self.assertTrue(Path(scene.image_path).is_file())
        self.assertIn('sahne-01', Path(scene.image_path).name)
        image_body = [b for u, b in self.calls if 'responseModalities' in json.dumps(b)][-1]
        self.assertEqual(image_body['generationConfig']['imageConfig']['aspectRatio'], '9:16')

        d.duration.setValue(5)
        d.generate_video(from_image=True)
        self.idle()
        self.assertTrue(Path(scene.video_path).is_file())
        video_body = [b for u, b in self.calls if u.endswith('/interactions')][-1]
        self.assertEqual(video_body['response_format'], {'type': 'video', 'aspect_ratio': '9:16',
                                                         'resolution': '720p', 'duration': '5s'})
        self.assertEqual(video_body['input'][-1]['text'], scene.motion_prompt)

        d.generate_video(from_image=False)
        self.idle()
        self.assertIsInstance([b for u, b in self.calls if u.endswith('/interactions')][-1]['input'], str)

        self.assertTrue(d.add_to_project('image'))
        self.assertTrue(d.add_to_project('video'))
        self.assertEqual(self.added, [scene.image_path, scene.video_path])

        story = self.folder / 'hikaye.json'
        self.assertTrue(d.save_story(str(story)))
        d.state = ss.StoryState()
        self.assertTrue(d.open_story(str(story)))
        self.assertEqual(d.state.scenes[0].video_path, scene.video_path)

    def test_missing_key_and_rejected_media(self):
        d = StoryDialog(api_key=lambda: '', output_dir=str(self.folder), add_media=lambda p: False,
                        transport=fake_transport(self.calls))
        self.addCleanup(d.close)
        d.write_scene()
        self.assertIsNone(d.worker)
        self.assertIn('anahtar', d.status_label.text())
        self.assertEqual(self.calls, [])
        scene = ss.Scene(image_path=str(self.folder / 'a.png'))
        Path(scene.image_path).write_bytes(PNG)
        d.state.scenes.append(scene)
        d.refresh_scene_list(scene.id)
        self.assertFalse(d.add_to_project('image'))

    def test_close_while_worker_runs(self):
        release = threading.Event()
        calls = []

        def slow(url, headers, body):
            calls.append(url)
            release.wait(5)
            return text_response('geç gelen metin')
        d = StoryDialog(api_key='k', output_dir=str(self.folder), add_media=self.added.append, transport=slow)
        d.show()
        d.write_scene()
        worker = d.worker
        self.assertTrue(wait_until(lambda: calls))
        d.close()
        self.assertIsNone(d.worker)
        self.assertTrue(wait_until(worker.isFinished, 2.0))
        release.set()
        QTest.qWait(50)
        self.assertEqual(d.state.scenes, [])  # the late result was discarded
        d.deleteLater()
        QTest.qWait(20)
        self.assertEqual(story_workers.running_workers(), [])


if __name__ == '__main__':
    unittest.main()


class StoryLanguageTests(unittest.TestCase):
    def dialog(self, language='en'):
        dialog = StoryDialog(api_key='', output_dir='', add_media=lambda _: True, language=language)
        self.addCleanup(dialog.close)
        return dialog

    def test_english_static_ui_and_canonical_choices(self):
        from akis import story_service as ss
        dialog = self.dialog()
        self.assertEqual(dialog.windowTitle(), 'Story Studio')
        self.assertEqual(dialog.tabs.tabText(0), 'Idea and story bible')
        self.assertEqual(dialog.write_button.text(), 'Write scene')
        self.assertEqual(dialog.pov.currentText(), 'Third person limited')
        self.assertEqual(dialog.pov.currentData(), ss.POV_CHOICES[0])
        self.assertEqual(dialog.tense.currentData(), ss.TENSE_CHOICES[0])
        self.assertEqual(dialog.duration.suffix(), ' s')
        self.assertIn('Estimated cost:', dialog.cost_label.text())
        self.assertNotIn('görsel', dialog.quality.toolTip())
        dialog.read_idea_fields()
        self.assertEqual(dialog.state.bible.pov, ss.POV_CHOICES[0])

    def test_live_switch_preserves_dirty_content_and_retranslates_dynamic_status(self):
        from akis import story_service as ss
        dialog = self.dialog('tr')
        dialog.state.scenes = [ss.Scene(title='Görsel', text='Türkçe user text', video_path='C:/Görsel.mp4')]
        dialog.refresh_scene_list()
        dialog.style_ref_label.setText('Görsel')
        dialog.style_reference = 'C:/Görsel'
        dialog.pov.setCurrentIndex(1)
        dialog.read_idea_fields()
        dialog.mark_clean()
        snapshot = dialog._snapshot()
        scene_id = dialog.current_id
        dialog.set_status('Görsel kaydedildi: C:/Görsel.png')
        dialog.set_busy(True)
        for language in ('en', 'tr', 'en'):
            dialog.apply_language(language)
            self.assertEqual(dialog._snapshot(), snapshot)
            self.assertFalse(dialog.is_dirty())
            self.assertEqual(dialog.current_id, scene_id)
            self.assertEqual(dialog.scene_title.text(), 'Görsel')
            self.assertEqual(dialog.video_label.text(), 'C:/Görsel.mp4')
            self.assertEqual(dialog.style_ref_label.text(), 'Görsel')
            self.assertFalse(dialog.write_button.isEnabled())
        self.assertEqual(dialog.status_label.text(), 'Image saved: C:/Görsel.png')
        dialog.on_progress(5)
        dialog.on_progress(10)
        self.assertEqual(dialog.status_label.text(), 'Image saved: C:/Görsel.png — 10 s')

    def test_validation_file_dialog_and_question_follow_language(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        dialog = self.dialog()
        dialog.need_key()
        self.assertTrue(dialog.status_label.text().startswith('No Gemini API key.'))
        dialog.continue_scene()
        self.assertEqual(dialog.status_label.text(), 'Scene not found.')
        with patch('akis.story_dialog.QFileDialog.getOpenFileName', return_value=('', '')) as choose:
            dialog.open_story()
            self.assertEqual(choose.call_args.args[1], 'Open story')
            self.assertEqual(choose.call_args.args[3], 'Story (*.hikaye.json *.json)')
        with patch('akis.story_dialog.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as ask:
            dialog.ask('"Görsel" sahnesi silinsin mi? Bu işlem geri alınamaz.',
                       QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
            self.assertEqual(ask.call_args.args[2], 'Delete scene "Görsel"? This cannot be undone.')

    def test_worker_status_cost_and_usage_retranslate(self):
        from akis import gemini_api
        dialog = self.dialog('tr')
        result = gemini_api.TextResult('content', 'gemini-3.8-flash',
                   {'prompt': 120, 'cached': 20, 'output': 30, 'thoughts': 5}, 'STOP',
                   False, 'requested', 'provider reason')
        dialog.show_usage(result)
        dialog.set_status('Video üretiliyor (model, 720p, 6 sn); bu birkaç dakika sürebilir…')
        dialog.apply_language('en')
        self.assertIn('Generating video (model, 720p, 6 s)', dialog.status_label.text())
        self.assertIn('Tokens: 120 input (20 cached)', dialog.usage_label.text())
        self.assertIn('35 output (5 thinking)', dialog.usage_label.text())
        self.assertIn('(fallback model; provider reason)', dialog.usage_label.text())
        dialog.apply_language('tr')
        self.assertIn('120 girdi', dialog.usage_label.text())

    def test_editing_scene_keeps_generated_media_markers(self):
        from akis import story_service as ss
        dialog = self.dialog('tr')
        dialog.state.scenes = [ss.Scene(title='Kıyı', image_path='shore.png', video_path='shore.mp4')]
        dialog.refresh_scene_list()
        item = dialog.scene_list.currentItem()
        self.assertTrue(item.text().endswith('▣▶'))

        dialog.scene_title.setText('Gece kıyısı')  # textChanged calls store_scene()
        self.assertTrue(item.text().endswith('▣▶'))
        self.assertIn('Gece kıyısı', item.text())

    def test_clearing_genre_is_saved_and_applied(self):
        import tempfile
        from pathlib import Path
        from akis import story_service as ss
        dialog = self.dialog('tr')
        dialog.state.bible.genre = 'Dram'
        dialog.refresh_bible_editor()
        dialog.genre.clear()

        self.assertTrue(dialog.apply_bible_editor())
        self.assertEqual(dialog.state.bible.genre, '')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'story.json'
            self.assertTrue(dialog.save_story(str(path)))
            self.assertEqual(ss.load_story(path).bible.genre, '')
