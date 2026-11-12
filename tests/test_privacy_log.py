"""The sidebar's list of what left the computer: recorded where requests are made, never by tests' stand-ins."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import ai_providers, gemini_api, i18n, privacy_log, update_service

app = QApplication.instance() or QApplication([])
EN = lambda text: i18n.translate(text, 'en')


class Clean(unittest.TestCase):
    def setUp(self):
        privacy_log.clear()
        self.addCleanup(privacy_log.clear)


class LogTests(Clean):
    def test_nothing_sent_says_so(self):
        self.assertEqual(privacy_log.summary(), 'Bu oturumda bilgisayarınızdan hiçbir şey gönderilmedi.')
        self.assertEqual(privacy_log.summary(EN), 'Nothing has been sent from your computer in this session.')

    def test_each_receiver_is_listed_once_with_what_it_got(self):
        for receiver, kind in (('OpenAI', 'frames'), ('GitHub', 'update'), ('OpenAI', 'audio'), ('OpenAI', 'frames')):
            privacy_log.note(receiver, kind)
        self.assertEqual(privacy_log.summary(), 'Bu oturumda gönderilenler:\n'
                         '• OpenAI: video kareleri ve istek metni, videonun sesi\n'
                         '• GitHub: sürüm denetimi (video gönderilmez)')
        self.assertIn("• OpenAI: video frames and the request text, the video's sound", privacy_log.summary(EN))

    def test_unknown_kinds_and_empty_receivers_are_ignored(self):
        privacy_log.note('OpenAI', 'secrets')
        privacy_log.note('', 'audio')
        self.assertEqual(privacy_log.sent(), [])


class HookTests(Clean):
    def test_plan_request_is_recorded_only_when_it_really_goes_out(self):
        reply = {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
        ai_providers.request_plan('xAI', 'k', 'grok', 'kes', [(1.0, b'jpeg')], transport=lambda url, headers, body: reply)
        self.assertEqual(privacy_log.sent(), [])
        with patch('akis.ai_providers.post_json', return_value=reply):
            ai_providers.request_plan('xAI', 'k', 'grok', 'kes', [(1.0, b'jpeg')])
            ai_providers.request_plan('xAI', 'k', 'grok', 'kes', [])
        self.assertEqual(privacy_log.sent(), [('xAI', 'frames'), ('xAI', 'text')])

    def test_transcription_records_the_sound(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'a.mp3'
            audio.write_bytes(b'ID3')
            with patch('akis.ai_providers.post_json', return_value={'text': 'merhaba'}):
                ai_providers.transcribe('xAI', 'k', 'model', audio)
        self.assertEqual(privacy_log.sent(), [('xAI', 'audio')])

    def test_update_check_is_recorded_only_for_a_real_check(self):
        fresh = lambda *args, **kwargs: io.BytesIO(json.dumps({'tag_name': 'v0.0.1', 'assets': []}).encode())
        update_service.check_update('9.9.9', fresh)
        self.assertEqual(privacy_log.sent(), [])
        with patch('akis.update_service.urllib.request.urlopen', side_effect=fresh):
            update_service.check_update('9.9.9')
        self.assertEqual(privacy_log.sent(), [('GitHub', 'update')])

    def test_story_requests_are_recorded_only_when_they_really_go_out(self):
        reply = {'candidates': [{'content': {'parts': [{'text': 'bir hikâye'}]}, 'finishReason': 'STOP'}]}
        gemini_api.generate_text('k', gemini_api.TEXT_MODELS[0], 'yaz', transport=lambda url, headers, body: reply)
        self.assertEqual(privacy_log.sent(), [])
        with patch('akis.gemini_api.post_json', return_value=reply):
            gemini_api.generate_text('k', gemini_api.TEXT_MODELS[0], 'yaz')
        self.assertEqual(privacy_log.sent(), [(gemini_api.PROVIDER, 'story')])


class WindowTests(Clean):
    def setUp(self):
        super().setUp()
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch('main.recovery_dir', return_value=Path(self.tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_sidebar_follows_the_log_and_the_language(self):
        w = self.window
        w.refresh_privacy()
        self.assertIn('hiçbir şey gönderilmedi', w.privacy_label.text())
        privacy_log.note('Gemini', 'audio')
        w.refresh_privacy()
        self.assertEqual(w.privacy_label.text(), 'Bu oturumda gönderilenler:\n• Gemini: videonun sesi')
        w.apply_language('en')
        w.refresh_privacy()
        self.assertEqual(w.privacy_label.text(), "Sent in this session:\n• Gemini: the video's sound")
        w.apply_language('tr')


if __name__ == '__main__':
    unittest.main()
