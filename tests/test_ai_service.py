import unittest
from types import SimpleNamespace
import json
from akis.ai_service import plan_prompt, parse_suggestions, local_transcribe, add_plan_markers, format_suggestion
from akis.timeline_model import Timeline

class AiTests(unittest.TestCase):
    def test_options_and_plan_validation(self):
        self.assertIn('TikTok', plan_prompt('demo', 'TikTok', 'Fast', 'Minimal', 'Product'))
        plans = parse_suggestions('{"suggestions":[{"trim_start":0,"trim_end":2},{"trim_start":1,"trim_end":3}]}', 4)
        timeline = Timeline(); add_plan_markers(timeline, plans[0])
        self.assertEqual([m['frame'] for m in timeline.markers], [0, 60])
        with self.assertRaises(ValueError): parse_suggestions('{"suggestions":[{"trim_start":9,"trim_end":9},{"trim_start":1,"trim_end":1.1}]}', 4)
    def test_missing_offline_model_explains_download(self):
        def factory(*args, **kwargs):
            raise FileNotFoundError('model missing')
        with self.assertRaisesRegex(RuntimeError, 'Modeli indir'):
            local_transcribe('x', 'tiny', model_factory=factory)
        with self.assertRaises(FileNotFoundError):
            local_transcribe('x', 'tiny', download=True, model_factory=factory)
    def test_local_offline_and_download_are_explicit(self):
        calls = []
        def factory(name, **kw):
            calls.append(kw)
            return SimpleNamespace(transcribe=lambda *a, **k: ([SimpleNamespace(start=0, end=1, text=' Merhaba ')], None))
        self.assertEqual(local_transcribe('x', 'tiny', model_factory=factory), 'Merhaba')
        self.assertTrue(calls[-1]['local_files_only'])
        local_transcribe('x', 'tiny', download=True, model_factory=factory)
        self.assertFalse(calls[-1]['local_files_only'])

class SuggestionTolerance(unittest.TestCase):
    def parse(self, items, duration=10):
        return parse_suggestions(json.dumps({'suggestions': items}), duration)
    def test_overshoot_is_clamped(self):
        plan = self.parse([{'trim_start': 1, 'trim_end': 10.4}])[0]
        self.assertEqual((plan['trim_start'], plan['trim_end']), (1.0, 10.0))
    def test_zero_or_missing_end_becomes_duration(self):
        for item in ({'trim_start': 2, 'trim_end': 0.0}, {'trim_start': 2}, {'trim_start': 2, 'trim_end': None}):
            self.assertEqual(self.parse([item])[0]['trim_end'], 10.0)
    def test_reversed_is_swapped(self):
        plan = self.parse([{'trim_start': 8, 'trim_end': 3}])[0]
        self.assertEqual((plan['trim_start'], plan['trim_end']), (3.0, 8.0))
    def test_bad_ones_dropped_good_kept(self):
        plans = self.parse([{'trim_start': 5, 'trim_end': 5.1}, 'x', {'trim_start': 'abc'},
                            {'trim_start': 0, 'trim_end': 4, 'title': 'A'}, {'trim_start': 1, 'trim_end': 9, 'title': 'B'}])
        self.assertEqual([p['title'] for p in plans], ['A', 'B'])
    def test_single_good_accepted(self):
        self.assertEqual(len(self.parse([{'trim_start': 0, 'trim_end': 5}])), 1)
    def test_all_bad_raises_turkish_error(self):
        with self.assertRaisesRegex(ValueError, 'kullanılabilir'):
            self.parse([{'trim_start': 3, 'trim_end': 3.2}, 'x'])
        with self.assertRaisesRegex(ValueError, 'kullanılabilir'):
            parse_suggestions('{"suggestions":[]}', 10)
    def test_fields_normalised(self):
        plan = self.parse([{'trim_start': 0, 'trim_end': 5, 'title': '  Baş  ', 'hashtags': ['#a', '##a', 'b', '#B', ''],
                            'notes': 'x, y', 'filter': 'Vivid', 'pacing': None}])[0]
        self.assertEqual(plan['title'], 'Baş')
        self.assertEqual(plan['hashtags'], ['a', 'b'])
        self.assertEqual(plan['notes'], ['x', 'y'])
        self.assertEqual(plan['filter'], 'vivid')
        self.assertEqual(plan['pacing'], '')
        self.assertEqual(self.parse([{'trim_start': 0, 'trim_end': 5, 'filter': 'weird'}])[0]['filter'], 'natural')
    def test_format_suggestion(self):
        plan = self.parse([{'trim_start': 3, 'trim_end': 27, 'title': 'Harika', 'hashtags': ['x'], 'notes': ['n1'], 'caption': 'cap'}], 60)[0]
        out = format_suggestion(plan)
        self.assertIn('Harika', out)
        self.assertIn('Kesim: 0:03 – 0:27 (24 sn)', out)
        self.assertIn('#x', out)
        self.assertIn('• n1', out)

if __name__ == '__main__': unittest.main()
