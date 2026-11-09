import unittest
from unittest.mock import patch
from timeline_model import Timeline, Track, Clip
from template_service import TEMPLATES, STYLES, TEMPOS, apply_template
from ai_providers import PROVIDERS, request_plan, TRANSCRIPTION_MODELS

class TemplateTests(unittest.TestCase):
    def test_all_templates_apply_and_preserve_clips(self):
        self.assertGreaterEqual(len(TEMPLATES), 8)
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                clip = Clip('video.mp4', 0, 60)
                timeline = Timeline(tracks=[Track('video', 'Existing', [clip])])
                apply_template(timeline, template)
                self.assertIs(timeline.tracks[0].clips[0], clip)
                self.assertTrue(any(c.text == template.title for t in timeline.tracks for c in t.clips))
                self.assertTrue(all(any(t.kind == k and t.name == n for t in timeline.tracks) for k,n in template.tracks))
                self.assertIn(template.style, STYLES); self.assertIn(template.tempo, TEMPOS)
                Timeline.from_dict(timeline.to_dict())

class ProviderTests(unittest.TestCase):
    def test_request_formats_and_response_selection(self):
        responses = {
            'OpenAI': {'output': [{'content': [{'type': 'output_text', 'text': 'ok'}]}]},
            'Anthropic': {'content': [{'type': 'text', 'text': 'ok'}]},
            'xAI': {'choices': [{'message': {'content': 'ok'}}]},
            'Gemini': {'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]},
        }
        for provider, models in PROVIDERS.items():
            with self.subTest(provider=provider):
                calls=[]
                def transport(url, headers, body):
                    calls.append((url, headers, body)); return responses[provider]
                self.assertEqual(request_plan(provider, 'secret', models[0], 'prompt', [(0, b'jpeg')], transport), 'ok')
                self.assertEqual(calls[0][2].get('model', models[0]), models[0])
                self.assertNotIn('secret', calls[0][0])
        self.assertEqual(set(TRANSCRIPTION_MODELS), {'OpenAI', 'xAI', 'Gemini'})
    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValueError): request_plan('unknown', 'key', 'model', '', [])
if __name__ == '__main__': unittest.main()
