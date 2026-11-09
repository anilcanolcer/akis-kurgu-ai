import unittest
from types import SimpleNamespace
from akis.ai_service import plan_prompt, parse_suggestions, local_transcribe, add_plan_markers
from akis.timeline_model import Timeline

class AiTests(unittest.TestCase):
    def test_options_and_plan_validation(self):
        self.assertIn('TikTok', plan_prompt('demo', 'TikTok', 'Fast', 'Minimal', 'Product'))
        plans = parse_suggestions('{"suggestions":[{"trim_start":0,"trim_end":2},{"trim_start":1,"trim_end":3}]}', 4)
        timeline = Timeline(); add_plan_markers(timeline, plans[0])
        self.assertEqual([m['frame'] for m in timeline.markers], [0, 60])
        with self.assertRaises(ValueError): parse_suggestions('{"suggestions":[{"trim_start":0,"trim_end":9},{"trim_start":1,"trim_end":2}]}', 4)
    def test_local_offline_and_download_are_explicit(self):
        calls = []
        def factory(name, **kw):
            calls.append(kw)
            return SimpleNamespace(transcribe=lambda *a, **k: ([SimpleNamespace(start=0, end=1, text=' Merhaba ')], None))
        self.assertEqual(local_transcribe('x', 'tiny', model_factory=factory), 'Merhaba')
        self.assertTrue(calls[-1]['local_files_only'])
        local_transcribe('x', 'tiny', download=True, model_factory=factory)
        self.assertFalse(calls[-1]['local_files_only'])
if __name__ == '__main__': unittest.main()
