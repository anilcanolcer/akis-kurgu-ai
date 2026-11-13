"""Speech language and custom vocabulary: the settings, and what each transcription path sends."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from akis import ai_providers, speech_settings
from akis.ai_service import local_transcribe

app = QApplication.instance() or QApplication([])


class Reset(unittest.TestCase):
    def setUp(self):
        speech_settings.set_current(speech_settings.DEFAULT_LANGUAGE, '')
        self.addCleanup(speech_settings.set_current, speech_settings.DEFAULT_LANGUAGE, '')


class SettingsTests(Reset):
    def test_turkish_is_the_default_and_auto_means_no_code(self):
        self.assertEqual(speech_settings.language(), 'tr')
        speech_settings.set_current(language='auto')
        self.assertIsNone(speech_settings.language())
        speech_settings.set_current(language='klingon')          # unknown falls back, never reaches an API
        self.assertEqual(speech_settings.language(), 'tr')
        self.assertEqual(speech_settings.language('en'), 'en')   # an explicit value wins over the setting

    def test_vocabulary_is_tidied_and_capped(self):
        self.assertEqual(speech_settings.clean_vocabulary(' Anılcan ,, akış  kurgu;ANILCAN\nffmpeg '),
                         'Anılcan, akış kurgu, ffmpeg')
        long = ', '.join(f'terim{i}' for i in range(200))
        capped = speech_settings.clean_vocabulary(long)
        self.assertLessEqual(len(capped), speech_settings.MAX_VOCABULARY)
        self.assertFalse(capped.endswith(','))
        self.assertEqual(speech_settings.clean_vocabulary(None), '')

    def test_instruction_names_the_language_and_the_terms(self):
        self.assertEqual(speech_settings.instruction('tr', ''), 'Türkçe konuşmayı aynen metne çevir; sadece metni döndür.')
        self.assertIn('İngilizce konuşmayı', speech_settings.instruction('en', ''))
        auto = speech_settings.instruction(None, 'Akış Kurgu')
        self.assertIn('konuşulduğu dilde', auto)
        self.assertIn('Akış Kurgu', auto)


class LocalTests(Reset):
    def run_local(self, **options):
        model = MagicMock()
        model.transcribe.return_value = ([types.SimpleNamespace(start=0, end=1, text=' Merhaba ')], None)
        text = local_transcribe('x', 'tiny', model_factory=lambda *a, **k: model, **options)
        return text, model.transcribe.call_args.kwargs

    def test_defaults_are_what_they_always_were(self):
        text, sent = self.run_local()
        self.assertEqual(text, 'Merhaba')
        self.assertEqual((sent['language'], sent['initial_prompt'], sent['vad_filter']), ('tr', None, True))

    def test_settings_and_overrides_reach_the_model(self):
        speech_settings.set_current('auto', 'Anılcan, ffmpeg')
        _, sent = self.run_local()
        self.assertEqual((sent['language'], sent['initial_prompt']), (None, 'Anılcan, ffmpeg'))
        _, sent = self.run_local(language='en', vocabulary='')
        self.assertEqual((sent['language'], sent['initial_prompt']), ('en', None))


class CloudTests(Reset):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audio = Path(tmp.name) / 'audio.mp3'
        self.audio.write_bytes(b'ID3fake')

    def post(self, provider, reply):
        with patch('akis.ai_providers.post_json', return_value=reply) as sent:
            ai_providers.transcribe(provider, 'key', 'model', self.audio)
        return sent.call_args.args[2]

    def test_gemini_prompt_follows_the_settings(self):
        reply = {'candidates': [{'content': {'parts': [{'text': 'hello'}]}}]}
        prompt = lambda: json.loads(self.post('Gemini', reply))['contents'][0]['parts'][0]['text']
        self.assertEqual(prompt(), 'Türkçe konuşmayı aynen metne çevir; sadece metni döndür.')
        speech_settings.set_current('en', 'Akış Kurgu')
        self.assertIn('İngilizce', prompt())
        self.assertIn('Akış Kurgu', prompt())

    def test_xai_sends_the_language_field_only_when_one_is_chosen(self):
        self.assertIn(b'name="language"\r\n\r\ntr\r\n', self.post('xAI', {'text': 'merhaba'}))
        speech_settings.set_current('de')
        self.assertIn(b'name="language"\r\n\r\nde\r\n', self.post('xAI', {'text': 'hallo'}))
        speech_settings.set_current('auto')
        body = self.post('xAI', {'text': 'hello'})
        self.assertNotIn(b'name="language"', body)
        self.assertIn(b'name="model"', body)
        self.assertIn(b'ID3fake', body)

    def test_openai_gets_language_and_prompt_only_when_set(self):
        create = MagicMock(return_value=types.SimpleNamespace(text='ok'))
        client = MagicMock()
        client.audio.transcriptions.create = create
        fake = types.SimpleNamespace(OpenAI=MagicMock(return_value=client))
        with patch.dict(sys.modules, {'openai': fake}):
            ai_providers.transcribe('OpenAI', 'key', 'whisper-1', self.audio)
            self.assertEqual({k: v for k, v in create.call_args.kwargs.items() if k not in ('file', 'response_format', 'timestamp_granularities')},
                             {'model': 'whisper-1', 'language': 'tr'})
            speech_settings.set_current('auto', 'Anılcan')
            ai_providers.transcribe('OpenAI', 'key', 'whisper-1', self.audio)
            self.assertEqual({k: v for k, v in create.call_args.kwargs.items() if k not in ('file', 'response_format', 'timestamp_granularities')},
                             {'model': 'whisper-1', 'prompt': 'Anılcan'})


class WindowTests(Reset):
    def setUp(self):
        super().setUp()
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(self.tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.addCleanup(self.close_window)
        self.stored = {}
        settings = MagicMock()
        settings.setValue.side_effect = self.stored.__setitem__
        settings.value.side_effect = lambda key, default=None: self.stored.get(key, default)
        self.window.settings = settings          # never the real registry

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def test_choice_is_used_at_once_and_remembered(self):
        w = self.window
        w.speech_language.setCurrentIndex(w.speech_language.findData('en'))
        w.speech_vocabulary.setText('  Akış Kurgu ,, ffmpeg ')
        w.save_speech_settings()
        self.assertEqual((speech_settings.language(), speech_settings.vocabulary()), ('en', 'Akış Kurgu, ffmpeg'))
        self.assertEqual(w.speech_vocabulary.text(), 'Akış Kurgu, ffmpeg')
        self.assertEqual(self.stored, {'speech/language': 'en', 'speech/vocabulary': 'Akış Kurgu, ffmpeg'})

    def test_saved_choice_comes_back_and_auto_is_selectable(self):
        w = self.window
        self.stored.update({'speech/language': 'auto', 'speech/vocabulary': 'Anılcan'})
        w.load_speech_settings()
        self.assertEqual(w.speech_language.currentData(), 'auto')
        self.assertIsNone(speech_settings.language())
        self.assertEqual(w.speech_vocabulary.text(), 'Anılcan')
        self.stored['speech/language'] = 'nonsense'
        w.load_speech_settings()
        self.assertEqual(w.speech_language.currentData(), 'tr')


if __name__ == '__main__':
    unittest.main()
