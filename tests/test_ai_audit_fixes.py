"""Audit fixes: tolerant plan decoration, prompt cancel, response guards, timeouts, keys, story dialog safety."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import io
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from akis import ai_providers, edit_plan, gemini_api, story_service as ss
from akis.ai_providers import (PLAN_DEADLINE, ProviderHTTPError, ProviderResponseError, _plan_text, fallback_note,
                               post_json, request_plan)
from akis.ai_workers import AIWorker, PromptEditWorker, TranscriptWorker
from akis.story_dialog import StoryDialog
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])
Button = QMessageBox.StandardButton


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(10)
    return condition()


class TolerantDecorationTests(unittest.TestCase):
    def parse(self, data):
        return edit_plan.parse_plan(json.dumps(data), [10.0, 4.0])

    def test_null_decoration_uses_defaults_and_keeps_the_plan(self):
        plan = self.parse({'summary': 'x', 'texts': [{'start': 0, 'end': 2, 'text': 'Selam', 'x': None, 'y': None}],
                           'marks': [{'type': 'circle', 'source': None, 'start': 1, 'x': None, 'size': None}]})
        self.assertEqual((plan['texts'][0]['x'], plan['texts'][0]['y']), (0.5, 0.78))
        self.assertEqual((plan['marks'][0]['source'], plan['marks'][0]['x'], plan['marks'][0]['size']), (0, 0.5, 0.3))
        self.assertNotIn('warnings', plan)  # null is the same as "not given"

    def test_garbage_decoration_is_reported_not_fatal(self):
        plan = self.parse({'summary': 'x', 'texts': [{'start': 0, 'end': 2, 'text': 'Selam', 'x': 'orta'}],
                           'marks': [{'type': 'arrow', 'start': 1, 'end': 'sonra', 'y': True,
                                      'from_x': 'a', 'from_y': 0.2}],
                           'color': {'contrast': 'çok', 'saturation': 10}, 'speed': 'hızlı', 'volume': 'yüksek'})
        self.assertEqual(plan['texts'][0]['x'], 0.5)
        mark = plan['marks'][0]
        self.assertEqual((mark['y'], mark['end']), (0.5, 2.5))
        self.assertNotIn('from_x', mark)
        self.assertEqual(plan['color'], {'saturation': 10})
        self.assertNotIn('speed', plan)
        self.assertNotIn('volume', plan)
        text = '\n'.join(plan['warnings'])
        for part in ('"orta"', 'end', 'from_x', 'Renk', 'Hız', 'Ses seviyesi'):
            self.assertIn(part, text)

    def test_timing_stays_strict(self):
        for data in ({'texts': [{'start': None, 'end': 2, 'text': 'a'}]},
                     {'texts': [{'start': 0, 'end': 'iki', 'text': 'a'}]},
                     {'marks': [{'type': 'circle', 'start': 'x'}]},
                     {'segments': [{'source': 0, 'start': 0, 'end': None}]}):
            with self.assertRaisesRegex(ValueError, 'geçersiz sayı'):
                self.parse(data)


def fake_analyse(worker):
    for source in worker.sources:
        source.update(silences=[], scenes=[], size=(160, 90), transcript=[])
    return [(0, 1.0, b'jpg')]


def blocking(release, seen=None):
    def fn(*args, **kwargs):
        if seen is not None:
            seen.append(args)
        release.wait(10)
        return '{"suggestions":[]}'
    return fn


class PromptCancelTests(unittest.TestCase):
    """cancel() ends the worker while the network call is still blocked; the late result is dropped."""

    def run_and_cancel(self, worker, started):
        events = []
        worker.completed.connect(lambda *a: events.append('completed'))
        worker.failed.connect(lambda m: events.append(('failed', m)))
        worker.cancelled.connect(lambda: events.append('cancelled'))
        worker.start()
        self.assertTrue(wait_until(lambda: started, 5))
        began = time.monotonic()
        worker.cancel()
        self.assertTrue(worker.wait(2000))
        self.assertLess(time.monotonic() - began, 1.0)
        QTest.qWait(20)
        self.assertEqual(events, ['cancelled'])

    def test_suggestion_worker(self):
        release, seen = threading.Event(), []
        self.addCleanup(release.set)
        worker = AIWorker('k', 'm', 'v.mp4', 10.0, 'kısa', 'ffmpeg')

        def frame(video, at, target):
            Path(target).write_bytes(b'jpg')
            return types.SimpleNamespace(returncode=0)
        worker.media.extract_frame = frame
        with patch('akis.ai_workers.request_plan', blocking(release, seen)):
            self.run_and_cancel(worker, seen)

    def test_transcript_worker(self):
        release, seen = threading.Event(), []
        self.addCleanup(release.set)
        worker = TranscriptWorker('k', 'v.mp4', 'ffmpeg')

        def audio(video, target):
            Path(target).write_bytes(b'mp3')
            return types.SimpleNamespace(returncode=0)
        worker.media.extract_audio = audio
        with patch('akis.ai_workers.transcribe', blocking(release, seen)):
            self.run_and_cancel(worker, seen)

    def test_prompt_edit_worker(self):
        release, seen = threading.Event(), []
        self.addCleanup(release.set)
        base = Timeline(tracks=[Track('video', 'V', [Clip('a.mp4', 0, 90, source_length=90)])])
        worker = PromptEditWorker('k', 'm', 'OpenAI', 'kes', base, [('a.mp4', 3.0)], 'ffmpeg',
                                  request_fn=blocking(release, seen))
        worker.analyse = lambda temp: fake_analyse(worker)
        self.run_and_cancel(worker, seen)


class FallbackNoteTests(unittest.TestCase):
    PLAN = json.dumps({'summary': 'ok', 'segments': [{'source': 0, 'start': 0, 'end': 2}]})

    def gemini_transport(self, calls):
        def transport(url, headers, body):
            calls.append(url)
            if 'gemini-4-argon' in url:
                raise ProviderHTTPError('Gemini API hatası: HTTP 503', 503)
            return {'candidates': [{'content': {'parts': [{'text': self.PLAN}]}, 'finishReason': 'STOP'}]}
        return transport

    def test_request_plan_names_the_fallback_model(self):
        calls = []
        text = request_plan('Gemini', 'k', 'gemini-4-argon', 'p', [], transport=self.gemini_transport(calls))
        self.assertEqual(text, self.PLAN)
        self.assertEqual((text.model, text.requested_model), ('gemini-3.8-flash', 'gemini-4-argon'))
        note = fallback_note(text)
        self.assertIn('gemini-4-argon', note)
        self.assertIn('yedek model gemini-3.8-flash', note)
        self.assertIn('HTTP 503', note)
        direct = request_plan('Gemini', 'k', 'gemini-3.8-flash', 'p', [], transport=self.gemini_transport([]))
        self.assertEqual(fallback_note(direct), '')
        self.assertEqual(fallback_note('düz metin'), '')

    def test_prompt_edit_worker_reports_fallback_in_warnings(self):
        base = Timeline(tracks=[Track('video', 'V', [Clip('a.mp4', 0, 90, source_length=90)])])
        reply = _plan_text(self.PLAN, 'gemini-3.8-flash', 'gemini-4-argon', ['gemini-4-argon yoğun (HTTP 503)'])
        worker = PromptEditWorker('k', 'm', 'Gemini', 'kes', base, [('a.mp4', 3.0)], 'ffmpeg',
                                  request_fn=lambda *a, **k: reply)
        worker.analyse = lambda temp: fake_analyse(worker)
        done = []
        worker.completed.connect(lambda plan, sources: done.append(plan))
        worker.failed.connect(self.fail)
        worker.run()
        self.assertIn('yedek model gemini-3.8-flash', done[0]['warnings'][0])

    def test_suggestion_worker_adds_note(self):
        reply = _plan_text('{"suggestions":[{"trim_start":0,"trim_end":8,"notes":["a"]}]}', 'b', 'a', [])
        worker = AIWorker('k', 'a', 'v.mp4', 10.0, 'kısa', 'ffmpeg', 'Gemini')

        def frame(video, at, target):
            Path(target).write_bytes(b'jpg')
            return types.SimpleNamespace(returncode=0)
        worker.media.extract_frame = frame
        done = []
        worker.completed.connect(done.append)
        worker.failed.connect(self.fail)
        with patch('akis.ai_workers.request_plan', lambda *a, **k: reply):
            worker.run()
        self.assertEqual(done[0][0]['notes'][0], 'a')
        self.assertIn('yedek model b', done[0][0]['notes'][1])


class ResponseShapeTests(unittest.TestCase):
    def test_odd_shapes_raise_provider_response_error(self):
        for provider, result in (('xAI', {'choices': ['x']}), ('Cloudflare', {'choices': [{'message': 'x'}]}),
                                 ('OpenAI', {'output': [{'content': ['x']}]}), ('Gemini', {'candidates': ['x']}),
                                 ('Anthropic', {'content': 5}), ('xAI', ['x'])):
            key = '0' * 32 + ':t' if provider == 'Cloudflare' else 'k'
            with self.subTest(provider=provider, result=result):
                with self.assertRaises(ProviderResponseError) as caught:
                    request_plan(provider, key, 'm', 'p', [], transport=lambda *a: result)
                self.assertIn('beklenmeyen', str(caught.exception))
                self.assertNotIn("attribute 'get'", str(caught.exception))


class PlanTimeoutTests(unittest.TestCase):
    def test_plan_requests_never_retry_a_timeout_and_carry_a_deadline(self):
        seen = []

        def fake(provider, url, body, headers, timeout, **kwargs):
            seen.append(kwargs)
            return {'choices': [{'message': {'content': 'tamam'}, 'finish_reason': 'stop'}]}
        with patch('akis.ai_providers.post_json', fake):
            before = time.monotonic()
            self.assertEqual(request_plan('xAI', 'k', 'grok', 'p', []), 'tamam')
        self.assertFalse(seen[0]['retry_timeout'])
        self.assertAlmostEqual(seen[0]['deadline'], before + PLAN_DEADLINE, delta=5)

    def test_spent_deadline_stops_the_fallback_chain(self):
        calls = []

        def slow_timeout(provider, url, body, headers, timeout, **kwargs):
            calls.append(url)
            time.sleep(0.1)
            try:
                raise TimeoutError()
            except TimeoutError as exc:
                raise RuntimeError('Gemini 300 saniyede yanıt vermedi.') from exc
        with patch('akis.ai_providers.post_json', slow_timeout):
            with self.assertRaisesRegex(RuntimeError, 'yanıt vermedi'):
                request_plan('Gemini', 'k', 'gemini-4-argon', 'p', [], deadline=0.05)
        self.assertEqual(len(calls), 1)  # the next model would start past the deadline

    def test_post_json_fits_attempts_and_waits_into_the_deadline(self):
        timeouts, sleeps = [], []

        def busy(request, timeout):
            timeouts.append(timeout)
            raise HTTPError(request.full_url, 503, 'busy', {}, io.BytesIO(b'{}'))
        with self.assertRaises(ProviderHTTPError):
            post_json('xAI', 'https://x', b'{}', {}, 300, opener=busy, sleep=sleeps.append,
                      deadline=105.0, clock=lambda: 100.0)
        self.assertEqual(timeouts, [5.0, 5.0])  # cut to what is left of the deadline
        self.assertEqual(sleeps, [4])           # the 10 s backoff would not fit, so no third attempt


class KeyTests(unittest.TestCase):
    def test_delete_key_ignores_missing_entry(self):
        from keyring.errors import PasswordDeleteError
        calls = []

        def delete(service, name):
            calls.append((service, name))
            raise PasswordDeleteError('not found')
        with patch('keyring.delete_password', delete):
            ai_providers.delete_key('Akış', 'OpenAI')
        self.assertEqual(calls, [('Akış', 'openai_api_key')])


def fake_openai(behaviour):
    module = types.ModuleType('openai')

    class OpenAIError(Exception):
        pass

    class APIConnectionError(OpenAIError):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    class APIStatusError(OpenAIError):
        def __init__(self, message, status_code, body):
            super().__init__(message)
            self.status_code, self.body = status_code, body

    made = []

    class OpenAI:
        def __init__(self, **kwargs):
            made.append(kwargs)
            self.audio = types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            return behaviour(module)

    module.OpenAI, module.OpenAIError, module.APIConnectionError = OpenAI, OpenAIError, APIConnectionError
    module.APITimeoutError, module.APIStatusError, module.made = APITimeoutError, APIStatusError, made
    return module


class OpenAITranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audio = Path(self.tmp.name) / 'a.mp3'
        self.audio.write_bytes(b'mp3')

    def transcribe(self, behaviour, key='sk-secretsecret1234'):
        module = fake_openai(behaviour)
        with patch.dict(sys.modules, {'openai': module}):
            return ai_providers.transcribe('OpenAI', key, 'whisper-1', self.audio), module

    def test_explicit_timeout_and_single_retry(self):
        text, module = self.transcribe(lambda m: types.SimpleNamespace(text='merhaba'))
        self.assertEqual(text, 'merhaba')
        self.assertEqual((module.made[0]['timeout'], module.made[0]['max_retries']),
                         (ai_providers.TRANSCRIBE_TIMEOUT, 1))

    def test_errors_are_mapped_and_scrubbed(self):
        def unauthorized(m):
            raise m.APIStatusError('Incorrect API key sk-secretsecret1234', 401,
                                   {'error': {'message': 'Incorrect API key provided: sk-secretsecret1234'}})
        with self.assertRaises(ProviderHTTPError) as caught:
            self.transcribe(unauthorized)
        message = str(caught.exception)
        self.assertEqual(caught.exception.code, 401)
        self.assertIn('HTTP 401', message)
        self.assertIn('anahtar', message)
        self.assertNotIn('secretsecret', message)

        def slow(m):
            raise m.APITimeoutError('timed out')
        with self.assertRaisesRegex(RuntimeError, f'{ai_providers.TRANSCRIBE_TIMEOUT} saniyede'):
            self.transcribe(slow)


class ListModelsErrorTests(unittest.TestCase):
    def test_bad_key_shows_detail_and_hint(self):
        def getter(url, headers, timeout):
            body = json.dumps({'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.'}})
            raise HTTPError(url, 400, 'Bad Request', {}, io.BytesIO(body.encode()))
        with self.assertRaises(ProviderHTTPError) as caught:
            gemini_api.list_models('AIzaSyFAKEFAKEFAKE123', getter=getter)
        message = str(caught.exception)
        self.assertIn('HTTP 400', message)
        self.assertIn('API key not valid', message)
        self.assertIn('Ayarlardan anahtarı kontrol edin', message)
        self.assertNotIn('AIzaSyFAKE', message)


class StoryDialogSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.calls = []
        self.models = ['gemini-3.8-flash']

        def getter(url, headers, timeout):
            return json.dumps({'models': [{'name': 'models/' + m} for m in self.models]}).encode()

        def transport(url, headers, body):
            self.calls.append(url)
            return {'candidates': [{'content': {'parts': [{'text': 'Metin.'}]}, 'finishReason': 'STOP'}]}
        self.dialog = StoryDialog(api_key='k', output_dir=str(self.folder), add_media=lambda p: True,
                                  transport=transport, file_getter=getter)
        self.answers = []
        self.questions = []
        self.dialog.can_ask = lambda: True

        def ask(text, buttons, default):
            self.questions.append(text)
            return self.answers.pop(0)
        self.dialog.ask = ask
        self.addCleanup(self.close)

    def close(self):
        self.dialog.can_ask = lambda: False
        self.dialog.close()

    def test_clean_until_changed(self):
        d = self.dialog
        self.assertFalse(d.is_dirty())
        d.add_empty_scene()
        self.assertTrue(d.is_dirty())
        self.assertTrue(d.save_story(str(self.folder / 's.hikaye.json')))
        self.assertFalse(d.is_dirty())
        d.scene_text.setPlainText('elle yazıldı')
        self.assertTrue(d.is_dirty())

    def test_open_asks_and_cancel_keeps_the_story(self):
        d = self.dialog
        other = self.folder / 'o.hikaye.json'
        ss.save_story(other, ss.StoryState())
        d.add_empty_scene()
        self.answers = [Button.Cancel]
        self.assertFalse(d.open_story(str(other)))
        self.assertEqual(len(d.state.scenes), 1)
        self.answers = [Button.Discard]
        self.assertTrue(d.open_story(str(other)))
        self.assertEqual(d.state.scenes, [])
        self.assertFalse(d.is_dirty())
        self.assertEqual(len(self.questions), 2)

    def test_close_asks_once_and_cancel_keeps_dialog_open(self):
        d = self.dialog
        d.show()
        d.add_empty_scene()
        self.answers = [Button.Cancel]
        self.assertFalse(d.close())
        self.assertTrue(d.isVisible())
        self.answers = [Button.Discard]
        self.assertTrue(d.close())
        self.assertFalse(d.isVisible())
        self.assertEqual(len(self.questions), 2)  # closeEvent and the reject() it triggers share one answer
        d.show()
        d.add_empty_scene()
        self.answers = [Button.Cancel]
        d.reject()  # Esc
        self.assertTrue(d.isVisible())

    def test_hidden_dialog_closes_without_asking(self):
        d = self.dialog
        d.can_ask = lambda: False
        d.add_empty_scene()
        self.assertTrue(d.close())
        self.assertEqual(self.questions, [])

    def test_delete_scene_confirms_and_is_blocked_while_busy(self):
        d = self.dialog
        d.add_empty_scene()
        self.answers = [Button.No]
        self.assertFalse(d.delete_scene())
        self.assertEqual(len(d.state.scenes), 1)
        self.answers = [Button.Yes]
        self.assertTrue(d.delete_scene())
        self.assertEqual(d.state.scenes, [])
        d.add_empty_scene()
        d.set_busy(True)
        self.assertFalse(d.delete_scene_button.isEnabled())
        d.worker = object()
        try:
            self.assertFalse(d.delete_scene())
        finally:
            d.worker = None
            d.set_busy(False)
        self.assertEqual(len(d.state.scenes), 1)

    def test_invalid_guide_stops_write_and_keeps_error(self):
        d = self.dialog
        d.bible_editor.setPlainText('{"title": "eksik"')
        self.assertFalse(d.write_scene())
        self.assertIsNone(d.worker)
        self.assertIn('geçerli JSON değil', d.status_label.text())
        self.assertEqual(self.calls, [])

    def test_generate_bible_asks_before_replacing_work(self):
        d = self.dialog
        d.premise.setPlainText('Bir fener bekçisi.')
        d.bible_editor.setPlainText(json.dumps({'outline': ['elle yazılan adım']}))
        self.answers = [Button.No]
        d.generate_bible()
        self.assertIsNone(d.worker)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.questions), 1)

    def test_check_models_keeps_hand_typed_id(self):
        d = self.dialog
        d.text_model.setCurrentText('gemini-ozel-deneme')
        d.check_models()
        self.assertTrue(wait_until(lambda: d.worker is None))
        QTest.qWait(10)
        self.assertEqual(d.text_model.currentText(), 'gemini-ozel-deneme')
        self.assertIn('gemini-3.8-flash', [d.text_model.itemText(i) for i in range(d.text_model.count())])


if __name__ == '__main__':
    unittest.main()
