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
