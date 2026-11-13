"""Cloud transcripts with timings: grouping xAI's words, OpenAI's whisper-1 segments, and the window."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from akis import ai_providers, speech_settings
from akis.ai_providers import Transcript, group_words

app = QApplication.instance() or QApplication([])


def words(*items):
    return [{'text': text, 'start': start, 'end': end} for text, start, end in items]


class GroupTests(unittest.TestCase):
    def test_sentence_end_and_pause_start_a_new_caption(self):
        found = group_words(words(('Merhaba', 0.0, 0.4), ('arkadaşlar.', 0.5, 1.0), ('Bugün', 1.1, 1.4),
                                  ('çok', 1.5, 1.7), ('güzel', 1.8, 2.2), ('bir', 3.5, 3.7), ('gün', 3.8, 4.0)))
        self.assertEqual(found, [{'start': 0.0, 'end': 1.0, 'text': 'Merhaba arkadaşlar.'},
                                 {'start': 1.1, 'end': 2.2, 'text': 'Bugün çok güzel'},
                                 {'start': 3.5, 'end': 4.0, 'text': 'bir gün'}])

    def test_long_runs_are_cut_and_bad_entries_skipped(self):
        many = words(*[(f'k{i}', i * 0.3, i * 0.3 + 0.25) for i in range(40)]) + [{'text': 'x'}, {'start': 1}]
        found = group_words(many)
        self.assertTrue(all(len(s['text'].split()) <= 14 for s in found))
        self.assertEqual(sum(len(s['text'].split()) for s in found), 40)
        self.assertEqual(group_words(None), [])

    def test_transcript_is_still_plain_text(self):
        said = Transcript('Merhaba', [{'start': 0, 'end': 1, 'text': 'Merhaba'}])
        self.assertEqual(said, 'Merhaba')
        self.assertEqual(said.upper(), 'MERHABA')
        self.assertIsNone(Transcript('x', []).segments)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        speech_settings.set_current(speech_settings.DEFAULT_LANGUAGE, '')
        self.addCleanup(speech_settings.set_current, speech_settings.DEFAULT_LANGUAGE, '')
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audio = Path(tmp.name) / 'a.mp3'
        self.audio.write_bytes(b'ID3')

    def test_xai_words_become_segments(self):
        reply = {'text': 'Merhaba arkadaşlar.', 'words': words(('Merhaba', 0.0, 0.4), ('arkadaşlar.', 0.5, 1.0))}
        with patch('akis.ai_providers.post_json', return_value=reply):
            said = ai_providers.transcribe('xAI', 'k', 'model', self.audio)
        self.assertEqual(said, 'Merhaba arkadaşlar.')
        self.assertEqual(said.segments, [{'start': 0.0, 'end': 1.0, 'text': 'Merhaba arkadaşlar.'}])

    def test_xai_without_words_has_no_timings(self):
        with patch('akis.ai_providers.post_json', return_value={'text': 'Merhaba'}):
            self.assertIsNone(ai_providers.transcribe('xAI', 'k', 'model', self.audio).segments)

    def openai(self, model, result):
        create = MagicMock(return_value=result)
        client = MagicMock()
        client.audio.transcriptions.create = create
        fake = types.ModuleType('openai')
        fake.OpenAI = MagicMock(return_value=client)
        for name in ('APITimeoutError', 'APIConnectionError', 'APIStatusError', 'OpenAIError'):
            setattr(fake, name, type(name, (Exception,), {}))
        with patch.dict(sys.modules, {'openai': fake}):
            said = ai_providers.transcribe('OpenAI', 'k', model, self.audio)
        return said, create.call_args.kwargs

    def test_whisper_1_asks_for_segments_and_returns_them(self):
        result = types.SimpleNamespace(text='Bir. İki.', segments=[types.SimpleNamespace(start=0.0, end=1.2, text=' Bir. '),
                                                                    {'start': 1.2, 'end': 2.0, 'text': 'İki.'},
                                                                    {'start': 'x', 'end': 2, 'text': 'bozuk'}])
        said, sent = self.openai('whisper-1', result)
        self.assertEqual((sent['response_format'], sent['timestamp_granularities']), ('verbose_json', ['segment']))
        self.assertEqual(said.segments, [{'start': 0.0, 'end': 1.2, 'text': 'Bir.'}, {'start': 1.2, 'end': 2.0, 'text': 'İki.'}])

    def test_other_openai_models_are_asked_for_text_only(self):
        said, sent = self.openai('gpt-4o-mini-transcribe', types.SimpleNamespace(text='Merhaba'))
        self.assertNotIn('response_format', sent)
        self.assertIsNone(said.segments)


class WorkerAndWindowTests(unittest.TestCase):
    def test_worker_hands_timings_over_before_the_text(self):
        from akis.ai_workers import TranscriptWorker
        worker = TranscriptWorker('k', 'v.mp4', 'ffmpeg')
        seen = []
        worker.timed.connect(lambda segments: seen.append(('timed', segments)))
        worker.completed.connect(lambda text: seen.append(('text', text)))
        said = Transcript('Merhaba', [{'start': 0, 'end': 1, 'text': 'Merhaba'}])
        with patch.object(worker.media, 'extract_audio', side_effect=lambda video, audio: (Path(audio).write_bytes(b'x'),
                                                                                          types.SimpleNamespace(returncode=0))[1]), \
             patch.object(worker, 'call', return_value=said):
            worker.run()
        self.assertEqual(seen, [('timed', [{'start': 0, 'end': 1, 'text': 'Merhaba'}]), ('text', 'Merhaba')])
        self.assertIs(type(seen[1][1]), str)

    def test_window_can_make_captions_from_a_cloud_transcript(self):
        from main import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch('main.recovery_dir', return_value=Path(tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        window = MainWindow()
        self.assertFalse(window.apply_captions_button.isEnabled())
        window.on_cloud_segments([{'start': 0, 'end': 1, 'text': 'Merhaba'}], 'C:/v/a.mp4')
        self.assertTrue(window.apply_captions_button.isEnabled())
        self.assertEqual((window.caption_source, len(window.caption_segments)), ('C:/v/a.mp4', 1))
        window.on_cloud_segments([], 'C:/v/b.mp4')                     # nothing timed: nothing changes
        self.assertEqual(window.caption_source, 'C:/v/a.mp4')
        window._close_confirmed = True
        window.close()


if __name__ == '__main__':
    unittest.main()
