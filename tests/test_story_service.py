"""Story engine: system instruction, bible, context budget, memory, visual prompts, costs, files."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from akis import gemini_api, story_service as ss
from akis.ai_providers import ResponseTruncatedError


def sample_state(scenes=0, words=50):
    bible = ss.StoryBible(
        title='Liman Feneri', premise='Bir fener bekçisinin kızı kayıp babasını arar.', genre='dram',
        setting='1974, Ayvalık', art_style='muted 35mm film photography, teal and amber palette',
        world_rules=['Fener her gece yanar.'], outline=['Elif feneri boş bulur.', 'Elif kasabaya iner.'],
        characters=[ss.Character(name='Elif', age='17', visual='a 17-year-old girl, long dark braid, freckles, '
                                 'oversized navy fisherman sweater'),
                    ss.Character(name='Rıza Usta', age='60', visual='a weathered 60-year-old man, white stubble, '
                                 'flat cap, brown wool coat'),
                    ss.Character(name='Selim', visual='a tall young postman with round glasses')])
    state = ss.StoryState(bible=bible)
    for i in range(scenes):
        state.scenes.append(ss.Scene(title=f'S{i + 1}', text=' '.join([f'kelime{i}'] * words), summary=f'özet {i + 1}'))
    return state


class InstructionTests(unittest.TestCase):
    def test_instruction_covers_quality_rules(self):
        text = ss.system_instruction('noir')
        for needle in ('Karakter tutarlılığı', 'bildiğini bilir', 'Bakış açısı', 'Göster, söyleme', 'uzun çizgiyle',
                       'klişe', 'Markdown', 'kesintisiz', 'Noir', 'Tarlabaşı'):
            self.assertIn(needle, text)
        self.assertNotEqual(ss.system_instruction('sade'), ss.system_instruction('noir'))
        self.assertEqual(ss.system_instruction('yok'), ss.system_instruction(ss.DEFAULT_STYLE))
        self.assertGreaterEqual(len(ss.STYLE_PROFILES), 4)
        for profile in ss.STYLE_PROFILES.values():
            self.assertTrue(profile.exemplar and len(profile.guidance) >= 3)


class ContextTests(unittest.TestCase):
    def test_stable_prefix_across_calls(self):
        state = sample_state(scenes=1)
        first = ss.next_scene_job(state, instruction='fırtına çıksın')
        state.scenes.append(ss.Scene(title='S2', text='Yeni sahne metni.'))
        state.rolling_summary = 'Elif babasını arıyor.'
        state.continuity = {'locations': {'Elif': 'iskele'}}
        second = ss.next_scene_job(state, instruction='başka')
        third = ss.memory_job(state, state.scenes[-1].id)
        self.assertEqual(first.system_instruction, second.system_instruction)
        self.assertEqual(first.parts[0], second.parts[0])
        self.assertEqual(first.parts[0], third.parts[0])
        self.assertEqual(first.parts[0], ss.render_bible(state.bible))
        self.assertIn('GÖREV', second.parts[-1])
        self.assertIn('Elif babasını arıyor', second.parts[1])
        self.assertIn('iskele', second.parts[1])
        self.assertIn('Sabit görsel tarif', first.parts[0])

    def test_render_bible_is_deterministic(self):
        a = ss.render_bible(sample_state().bible)
        b = ss.render_bible(ss.StoryState.from_dict(json.loads(json.dumps(sample_state().to_dict()))).bible)
        self.assertEqual(a, b)

    def test_budget_and_older_summaries(self):
        state = sample_state(scenes=6, words=400)  # ~3,600 chars each
        parts = ss.build_context(state, budget_tokens=3000, recent=3)  # 9,000 chars
        story = parts[-1]
        verbatim = story.split('# SON SAHNELER (aynen)')[1]
        self.assertLessEqual(len(verbatim), 3000 * ss.CHARS_PER_TOKEN + 200)
        self.assertIn('Sahne 6', verbatim)
        self.assertIn('Sahne 5', verbatim)
        self.assertNotIn('Sahne 4:', verbatim)
        self.assertIn('4. S4: özet 4', story)
        self.assertIn('1. S1: özet 1', story)

    def test_oversized_last_scene_keeps_its_end(self):
        state = sample_state(scenes=1, words=10)
        state.scenes[0].text = 'BAŞ ' + 'orta ' * 5000 + 'SON CÜMLE.'
        story = ss.build_context(state, budget_tokens=500)[-1]
        self.assertIn('SON CÜMLE.', story)
        self.assertNotIn('BAŞ', story)
        self.assertIn('[…]', story)
        self.assertLessEqual(len(story), 500 * ss.CHARS_PER_TOKEN + 200)

    def test_jobs_routing_and_budgets(self):
        self.assertIn('Elif kasabaya iner', ss.next_scene_job(sample_state(scenes=1)).parts[-1])  # outline step 2
        state = sample_state(scenes=2)
        draft = ss.next_scene_job(state, words=800)
        self.assertEqual((draft.model, draft.thinking_level), ('gemini-3.8-flash', 'medium'))
        final = ss.next_scene_job(state, quality='final', model='gemini-4-argon')
        self.assertEqual(final.model, 'gemini-4-argon')
        self.assertLessEqual(ss.next_scene_job(state, words=4000).max_output_tokens, gemini_api.MAX_OUTPUT_TOKENS)
        self.assertGreater(draft.max_output_tokens, 800 * 2)
        cont = ss.continue_job(state, state.scenes[0].id)
        self.assertIn('Sahne 1', cont.parts[-1])
        self.assertNotIn('Sahne 2:', ''.join(cont.parts[:-1]))
        rewrite = ss.rewrite_job(state, state.scenes[0].id, 'shorten', instruction='daha sert')
        self.assertIn(state.scenes[0].text, rewrite.parts[-1])
        self.assertIn('sonunda varılan durumu değiştirme', rewrite.parts[-1])
        self.assertEqual(ss.memory_job(state, state.scenes[0].id).thinking_level, 'low')
        with self.assertRaises(ValueError):
            ss.rewrite_job(state, 'yok', 'rewrite')
        with self.assertRaises(ValueError):
            ss.bible_job('  ')

    def test_scene_text_application(self):
        state = sample_state()
        job = ss.next_scene_job(state)
        scene = ss.apply_scene_text(state, job, '```\nSahne 1: Başlangıç\nElif feneri boş buldu.\n```')
        self.assertEqual(scene.text, 'Elif feneri boş buldu.')
        cont = ss.continue_job(state, scene.id)
        ss.apply_scene_text(state, cont, 'Merdivenleri çıktı.')
        self.assertEqual(scene.text, 'Elif feneri boş buldu.\n\nMerdivenleri çıktı.')
        rewrite = ss.rewrite_job(state, scene.id)
        ss.apply_scene_text(state, rewrite, 'Yeni metin.')
        self.assertEqual(scene.text, 'Yeni metin.')

    def test_truncated_scene_returns_partial(self):
        state = sample_state()
        job = ss.next_scene_job(state)

        def generate(*args, **kwargs):
            raise ResponseTruncatedError('kesildi', 'Yarım kalan')
        result = ss.run_text_job(job, 'k', generate=generate)
        self.assertTrue(result.truncated)
        self.assertEqual(result.text, 'Yarım kalan')
        other = sample_state(scenes=1)
        with self.assertRaises(ResponseTruncatedError):  # JSON tasks cannot use half an answer
            ss.run_text_job(ss.visual_job(other, other.scenes[0].id), 'k', generate=generate)


class MemoryTests(unittest.TestCase):
    def test_bad_json_keeps_old_state(self):
        state = sample_state(scenes=1)
        state.rolling_summary = 'eski'
        state.continuity = {'open_threads': ['baba nerede?']}
        before = json.dumps(state.to_dict(), sort_keys=True)
        for bad in ('', 'özet: ...', '{"rolling_summary": ', '[1, 2]', '{"continuity": "yok"}', None):
            self.assertFalse(ss.apply_memory(state, state.scenes[0].id, bad))
            self.assertEqual(json.dumps(state.to_dict(), sort_keys=True), before)

    def test_valid_and_partial_updates(self):
        state = sample_state(scenes=1)
        state.continuity = {'open_threads': ['baba nerede?']}
        answer = '```json\n' + json.dumps({
            'scene_summary': 'Elif feneri boş bulur.', 'rolling_summary': 'Elif yalnız.',
            'continuity': {'knowledge': {'Elif': ['babası gitti'], 'Boş': []}, 'locations': {'Elif': 'fener'},
                           'changed_facts': 'Fener söndü.'}}, ensure_ascii=False) + '\n```'
        self.assertTrue(ss.apply_memory(state, state.scenes[0].id, answer))
        self.assertEqual(state.scenes[0].summary, 'Elif feneri boş bulur.')
        self.assertEqual(state.rolling_summary, 'Elif yalnız.')
        self.assertEqual(state.continuity['knowledge'], {'Elif': ['babası gitti']})
        self.assertEqual(state.continuity['changed_facts'], ['Fener söndü.'])
        self.assertEqual(state.continuity['open_threads'], ['baba nerede?'])  # untouched field kept
        self.assertTrue(ss.apply_memory(state, state.scenes[0].id, '{"rolling_summary": "yeni", "continuity": 5}'))
        self.assertEqual(state.rolling_summary, 'yeni')
        self.assertEqual(state.continuity['locations'], {'Elif': 'fener'})
        self.assertIn('Elif şu an: fener', ss.render_memory(state))


class VisualTests(unittest.TestCase):
    def test_prompt_injects_fixed_descriptions_and_art_style(self):
        state = sample_state(scenes=1)
        scene = state.scenes[0]
        scene.text = 'Elif fenerin kapısını itti. Rıza Usta arkasındaydı.'
        answer = json.dumps({'characters': ['Elif'], 'image_prompt': 'A girl pushes open a lighthouse door at dawn',
                             'motion_prompt': 'Slow dolly forward as the door creaks open; gulls and wind.'})
        ss.apply_visual(state, scene.id, answer)
        for c in state.bible.characters[:2]:
            self.assertIn(c.visual, scene.visual_prompt)
        self.assertNotIn('postman', scene.visual_prompt)
        self.assertIn(state.bible.art_style, scene.visual_prompt)
        self.assertIn('gulls', scene.motion_prompt)
        self.assertEqual(ss.video_prompt(scene, True), scene.motion_prompt)
        self.assertIn(scene.visual_prompt, ss.video_prompt(scene, False))

    def test_bad_answer_falls_back_locally(self):
        state = sample_state(scenes=1)
        scene = state.scenes[0]
        scene.text = 'Selim mektubu uzattı.'
        ss.apply_visual(state, scene.id, 'not json')
        self.assertIn('round glasses', scene.visual_prompt)
        self.assertIn('sound', scene.motion_prompt)
        job = ss.visual_job(state, scene.id)
        self.assertEqual(job.parts[0], ss.render_bible(state.bible))
        self.assertIn('İngilizce', job.parts[-1])


class SplitTests(unittest.TestCase):
    TEXT = 'Bir.\n\nİki.\n\nÜç.\n\nDört.'

    def test_split_by_model_indices(self):
        scenes = ss.apply_split('{"scenes": [{"start": 3, "title": "Gece"}, {"start": 1, "title": "Sabah"}, '
                                '{"start": 99}]}', self.TEXT)
        self.assertEqual([(s.title, s.text) for s in scenes], [('Sabah', 'Bir.\n\nİki.'), ('Gece', 'Üç.\n\nDört.')])

    def test_malformed_falls_back(self):
        scenes = ss.apply_split('???', 'A.\n\n***\n\nB.')
        self.assertEqual([s.text for s in scenes], ['A.', 'B.'])
        self.assertEqual(len(ss.apply_split('{"scenes": "x"}', self.TEXT)), 1)
        with self.assertRaises(ValueError):
            ss.split_job(sample_state(), 'tek paragraf')


class CostTests(unittest.TestCase):
    def test_text_prices_by_date(self):
        self.assertAlmostEqual(ss.estimate_text_cost('gemini-3.8-flash', 1_000_000, 1_000_000, on=date(2026, 12, 31)), 4.50)
        self.assertAlmostEqual(ss.estimate_text_cost('gemini-3.8-flash', 1_000_000, 1_000_000, on=date(2027, 1, 1)), 9.00)
        self.assertAlmostEqual(ss.estimate_text_cost('gemini-4-argon', 1_000_000, 0, on=date(2026, 11, 30)), 2.00)
        self.assertAlmostEqual(ss.estimate_text_cost('gemini-4-argon', 1_000_000, 0, on=date(2026, 12, 1)), 4.00)
        cached = ss.estimate_text_cost('gemini-3.8-flash', 1_000_000, 0, cached_tokens=1_000_000, on=date(2026, 11, 11))
        self.assertAlmostEqual(cached, 0.075)
        self.assertIsNone(ss.estimate_text_cost('gemini-3.6-flash', 10, 10))

    def test_image_and_video_lines(self):
        self.assertAlmostEqual(ss.estimate_image_cost('gemini-nano-banana-2.1', '2K'), 0.050)
        self.assertAlmostEqual(ss.estimate_image_cost('gemini-3-pro-image', '1K', 2), 0.268)
        self.assertIsNone(ss.estimate_image_cost('gemini-3.1-flash-image', '4K'))
        self.assertIn('0.034', ss.image_cost_line('gemini-nano-banana-2.1', '1K'))
        self.assertIn('fiyat belgelenmedi', ss.video_cost_line('gemini-omni-1.2-flash', '720p', 6))
        self.assertNotRegex(ss.video_cost_line('gemini-omni-1.2-flash', '720p', 6), r'\$')

    def test_usage_line(self):
        result = gemini_api.TextResult('x', 'gemini-3.6-flash', {'prompt': 5000, 'output': 800, 'thoughts': 1054,
                                                                'cached': 4096}, requested_model='gemini-3.8-flash',
                                       fallback_reason='gemini-3.8-flash yoğun (HTTP 503)')
        line = ss.usage_line(result)
        self.assertIn('5000 girdi (4096 önbellek)', line)
        self.assertIn('1854 çıktı (1054 düşünme)', line)
        self.assertIn('yedek model', line)
        self.assertEqual(ss.route('scene', 'final'), ('gemini-4-argon', 'medium'))


class FileTests(unittest.TestCase):
    def test_round_trip_and_bad_files(self):
        with tempfile.TemporaryDirectory() as folder:
            state = sample_state(scenes=2)
            state.scenes[0].image_path = 'C:/x/gorsel.png'
            state.continuity = {'open_threads': ['a']}
            path = Path(folder) / 'a' / 'hikaye.json'
            ss.save_story(path, state)
            loaded = ss.load_story(path)
            self.assertEqual(loaded.to_dict(), state.to_dict())
            path.write_text('{bozuk', encoding='utf-8')
            with self.assertRaises(ValueError):
                ss.load_story(path)
            odd = ss.StoryState.from_dict({'bible': {'style': 'yok', 'characters': [{'name': ''}, 'x', {'name': 'A'}],
                                                     'world_rules': 'bir\n- iki'}, 'scenes': [{'text': 't'}, 3]})
            self.assertEqual(odd.bible.style, ss.DEFAULT_STYLE)
            self.assertEqual([c.name for c in odd.bible.characters], ['A'])
            self.assertEqual(odd.bible.world_rules, ['bir', 'iki'])
            self.assertTrue(odd.scenes[0].id)

    def test_media_paths_are_stable_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            state = sample_state(scenes=3)
            scene = state.scenes[1]
            first = ss.media_path(folder, state, scene, 'gorsel', '.png')
            self.assertEqual(first, Path(folder) / 'liman-feneri' / f'sahne-02-{scene.id}-gorsel.png')
            first.write_bytes(b'x')
            self.assertEqual(ss.media_path(folder, state, scene, 'gorsel', '.png').name, f'sahne-02-{scene.id}-gorsel-2.png')

    def test_bible_generation_merge(self):
        base = ss.StoryBible(premise='fikir', style='noir', pov='Birinci tekil (ben)')
        answer = 'İşte: {"title": "Gece", "style": "sade", "premise": "başka", "characters": [{"name": "Ece", ' \
                 '"visual": "short red hair"}], "outline": ["a", "b"]} bitti'
        bible = ss.apply_bible(answer, base)
        self.assertEqual((bible.title, bible.style, bible.premise, bible.pov), ('Gece', 'noir', 'fikir', 'Birinci tekil (ben)'))
        self.assertEqual(bible.characters[0].visual, 'short red hair')
        with self.assertRaises(ValueError):
            ss.apply_bible('nope', base)
        self.assertEqual(ss.apply_outline('{"outline": ["x", "", "y"]}'), ['x', 'y'])


if __name__ == '__main__':
    unittest.main()
