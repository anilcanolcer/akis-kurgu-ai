"""Stories, personal templates and update versions: random content saved and read back.

Rules:
  story       a story with random text (any characters, empty fields, long lists) saves and opens unchanged;
              random JSON either opens or is refused with ValueError, never another exception
  templates   a random series of add and remove calls leaves the file holding exactly the templates a plain
              list would; applying a template twice adds no second copy of its tracks
  versions    an update is offered only for a higher x.y.z; tags in any other shape are ignored
Usage: python scripts/media-audit/store_fuzz.py <project root> [runs] [first seed]
"""
import json
import os
import random
import sys
import tempfile
import traceback
from collections import defaultdict
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from akis import story_service, update_service, user_templates  # noqa: E402
from akis.timeline_model import Timeline, Track  # noqa: E402

CHARS = 'abcçğıiİöşüÂâ çok güzel “tırnak” \'tek\' \\ / \n\t🔥 {} [] ,.:;!?€₺'


class Broken(Exception):
    pass


def text(rng, longest=40):
    return ''.join(rng.choice(CHARS) for _ in range(rng.randint(0, longest)))


def check_story(rng, folder):
    state = story_service.StoryState()
    bible = state.bible
    for name in ('title', 'premise', 'genre', 'setting', 'art_style', 'notes'):
        setattr(bible, name, text(rng).strip())
    bible.style = rng.choice(list(story_service.STYLE_PROFILES))
    bible.world_rules = [t for t in (text(rng).strip().strip(' -•\t') for _ in range(rng.randint(0, 4))) if t and '\n' not in t]
    bible.outline = [t for t in (text(rng).strip().strip(' -•\t') for _ in range(rng.randint(0, 4))) if t and '\n' not in t]
    bible.characters = [story_service.Character(name=n, role=text(rng).strip(), visual=text(rng).strip())
                        for n in (text(rng, 12).strip() for _ in range(rng.randint(0, 3))) if n]
    state.scenes = [story_service.Scene(title=text(rng).strip(), text=text(rng, 400).strip(), summary=text(rng).strip())
                    for _ in range(rng.randint(0, 5))]
    state.rolling_summary = text(rng).strip()
    path = folder / f'story{rng.random()}.json'
    story_service.save_story(path, state)
    loaded = story_service.load_story(path)
    if loaded.to_dict() != state.to_dict():
        a, b = loaded.to_dict(), state.to_dict()
        diff = [k for k in b if a.get(k) != b.get(k)]
        raise Broken(f'hikâye kaydedip açınca değişti: {diff} · {json.dumps(b, ensure_ascii=False)[:300]}')
    junk = rng.choice([[], 'x', 5, None, {'format': 'akis-story', 'version': rng.choice([1, '1', 2, True])},
                       {'bible': rng.choice([{}, [], {'characters': rng.choice([None, 'x', [{}], [{'name': 5}]])}]),
                        'scenes': rng.choice([[], [None, 'x', {'text': 5, 'id': None}], 'x'])},
                       {'scenes': [{'title': ['a', 'b']}], 'continuity': rng.choice([None, 'x', {'a': [1]}, [1]])}])
    junk_path = folder / 'junk.json'
    junk_path.write_text(json.dumps(junk), encoding='utf-8')
    try:
        story_service.load_story(junk_path)
    except ValueError:
        pass


def check_templates(rng, folder):
    place = folder / f'templates{rng.random()}'
    expected = []
    for _ in range(rng.randint(1, 12)):
        if expected and rng.random() < .3:
            name = rng.choice(expected)['name']
            user_templates.remove(place, name)
            expected = [item for item in expected if item['name'] != name]
            continue
        name = rng.choice(['Vlog', 'vlog', 'Röportaj', 'İnceleme', text(rng, 70)])
        timeline = Timeline(tracks=[Track(rng.choice(['video', 'audio', 'text', 'overlay']), text(rng, 10) or 'İz')
                                    for _ in range(rng.randint(0, 4))])
        try:
            item = user_templates.capture(name, timeline, aspect=rng.choice(['9:16', '16:9']),
                                          color=(rng.randint(-50, 50), 0, 0), speed=rng.choice([0.5, 1.0, 2.0]))
        except ValueError:
            continue
        user_templates.add(place, item)
        cleaned = user_templates._valid(item)
        expected = [old for old in expected if old['name'].casefold() != cleaned['name'].casefold()] + [cleaned]
    stored = user_templates.load(place)
    if stored != expected:
        raise Broken(f'şablon dosyası beklenenden farklı: {[i["name"] for i in stored]} · {[i["name"] for i in expected]}')
    for item in stored:
        timeline = Timeline(tracks=[Track('video', 'Video')])
        user_templates.apply(timeline, dict(item, title=''))
        once = [(t.kind, t.name) for t in timeline.tracks]
        user_templates.apply(timeline, dict(item, title=''))
        if [(t.kind, t.name) for t in timeline.tracks] != once:
            raise Broken(f'şablonu iki kez uygulamak izleri çoğalttı: {once}')


def check_versions(rng, folder):
    current = f'{rng.randint(0, 2)}.{rng.randint(0, 12)}.{rng.randint(0, 20)}'
    tag = rng.choice([f'v{rng.randint(0, 2)}.{rng.randint(0, 12)}.{rng.randint(0, 20)}',
                      f'{rng.randint(0, 2)}.{rng.randint(0, 12)}.{rng.randint(0, 20)}',
                      'v1.0', 'v1.0.0-beta', 'latest', '', 'v01.2.3', ' v1.2.3'])
    digest = 'sha256:' + 'a' * 64
    data = {'tag_name': tag, 'draft': False, 'prerelease': False,
            'assets': [{'name': update_service.ASSET, 'browser_download_url': update_service.DOWNLOAD_PREFIX + tag + '/x',
                        'digest': digest, 'size': 10}]}
    try:
        found = update_service.find_update(data, current)
    except ValueError:
        found = 'error'
    newer = update_service.version_tuple(tag)
    should = newer is not None and newer > update_service.version_tuple(current)
    if bool(found) != should or found == 'error':
        raise Broken(f'{current} kuruluyken {tag!r}: güncelleme {"önerildi" if found else "önerilmedi"}')


def guide_text(rng):
    """What a person might leave in the Story Studio guide box: an edited guide, or something broken."""
    if rng.random() < 0.6:
        data = {}
        for name in rng.sample(['title', 'genre', 'setting', 'art_style', 'notes'], rng.randint(0, 5)):
            data[name] = text(rng).strip()
        if rng.random() < 0.6:
            data['characters'] = [{'name': text(rng, 12).strip() or 'Ada', 'role': text(rng).strip()}
                                  for _ in range(rng.randint(0, 3))]
        if rng.random() < 0.5:
            data['world_rules'] = [text(rng, 20).strip() for _ in range(rng.randint(0, 3))]
        body = json.dumps(data, ensure_ascii=rng.random() < 0.3, indent=rng.choice([None, 2]))
        return rng.choice([body, '```json\n' + body + '\n```', 'Rehber:\n' + body])
    return rng.choice(['{"characters":', '[', 'karakterler', '{"title": }', '{"characters": 5}', '',
                       '["Ada", "Can"]', '{"characters": "Ada"}'])


_story_app = []


def check_story_guide(rng, folder):
    """Rule: Save writes the guide that is on screen. A guide that cannot be read stops the save; the file on
    disk stays as it was and the story stays unsaved. (0.6.17 saved the old guide and dropped the edit.)"""
    if not _story_app:
        from PySide6.QtWidgets import QApplication
        _story_app.append(QApplication.instance() or QApplication([]))
    from akis.story_dialog import StoryDialog
    dialog = StoryDialog(api_key=lambda: 'test', output_dir=lambda: str(folder), add_media=lambda *_: None)
    path = folder / f'rehber{rng.random():.9f}.hikaye.json'[2:]
    steps = []
    try:
        for _ in range(rng.randint(1, 7)):
            action = rng.choice(['guide', 'guide', 'apply', 'genre', 'save', 'save'])
            steps.append(action)
            if action == 'guide':
                dialog.bible_editor.setPlainText(guide_text(rng))
            elif action == 'apply':
                dialog.apply_bible_editor()
            elif action == 'genre':
                dialog.genre.setText(text(rng, 15))
            else:
                shown = dialog.bible_editor.toPlainText()
                before = path.read_bytes() if path.exists() else None
                try:
                    readable = story_service.bible_from_dict(story_service.extract_json(shown))
                except ValueError:
                    readable = None
                saved = dialog.save_story(str(path))
                if readable is None:
                    if saved:
                        raise Broken(f'okunamayan rehberle kaydedildi: {shown[:80]!r} · {steps}')
                    if (path.read_bytes() if path.exists() else None) != before:
                        raise Broken(f'kaydetme reddedildi ama dosya değişti · {steps}')
                    if not dialog.is_dirty():
                        raise Broken(f'kaydedilemeyen değişiklik kaydedilmiş sayıldı · {steps}')
                    continue
                if not saved:
                    raise Broken(f'geçerli rehberle kaydedilemedi · {steps}')
                loaded = story_service.load_story(path).to_dict()['bible']
                fresh = story_service.StoryState()
                fresh.bible = readable
                wanted = fresh.to_dict()['bible']
                for name in ('premise', 'style', 'pov', 'tense', 'genre'):
                    wanted.pop(name, None)
                    loaded.pop(name, None)
                if loaded != wanted:
                    diff = [k for k in wanted if wanted.get(k) != loaded.get(k)]
                    raise Broken(f'dosyadaki rehber ekrandakinden farklı: {diff} · {steps}')
                if story_service.load_story(path).bible.genre != dialog.genre.text().strip():
                    raise Broken(f'tür alanı kaydedilmedi · {steps}')
                if dialog.is_dirty():
                    raise Broken(f'kaydettikten sonra değişiklik var görünüyor · {steps}')
    finally:
        dialog.close()
        dialog.deleteLater()


def check_project_file(rng, folder):
    """Rule: a project file either opens, or is refused with a ValueError in plain Turkish (never Python's
    parser text, an English model error, or another exception type)."""
    from akis import project_service
    from akis.timeline_model import Clip
    good = project_service.make_document({}, Timeline(tracks=[Track('video', 'V1', [Clip('a.mp4', 0, 30)])]), {}, 'x')
    text = json.dumps(good, ensure_ascii=False)
    pick = rng.randrange(8)
    if pick == 0:
        body = text[:rng.randrange(len(text))].encode('utf-8')                      # cut off while writing
    elif pick == 1:
        body = rng.randbytes(rng.randint(0, 64))                                    # not text
    elif pick == 2:
        body = json.dumps(rng.choice([[], {}, 'x', 5, None, {'format': 'akis-story'}])).encode()
    elif pick == 3:
        good['version'] = rng.choice([0, -1, project_service.CURRENT_VERSION + 1, 99, '2', True, None, 1.5])
        body = json.dumps(good).encode()
    else:                                                                           # a hand-edited timeline
        doc = json.loads(text)
        tracks = doc['timeline']['tracks']
        damage = rng.choice(['kind', 'overlap', 'length', 'start', 'source', 'tracks', 'clips', 'fps', 'speed'])
        clip = tracks[0]['clips'][0]
        if damage == 'kind':
            tracks[0]['kind'] = rng.choice(['film', '', 5, None])
        elif damage == 'overlap':
            tracks[0]['clips'].append(dict(clip, id='b', start=10))
        elif damage == 'length':
            clip['length'] = rng.choice([0, -5, 'uzun', None])
        elif damage == 'start':
            clip['start'] = rng.choice([-1, 'baş', None, 1.5])
        elif damage == 'source':
            clip['source'] = rng.choice([None, 5, ['a']])
        elif damage == 'tracks':
            doc['timeline']['tracks'] = rng.choice([None, 'iz', [None], [5]])
        elif damage == 'clips':
            tracks[0]['clips'] = rng.choice([None, 'k', [None], [5]])
        elif damage == 'fps':
            doc['timeline'][rng.choice(['fps_num', 'fps_den'])] = rng.choice([0, -30, 'otuz', None])
        else:
            clip['speed'] = rng.choice([0, -1, 'hızlı', 1000])
        body = json.dumps(doc).encode()
    path = folder / f'proje{rng.random():.9f}.akis.json'[2:]
    path.write_bytes(body)
    try:
        project_service.load(path)
    except ValueError as error:
        said = str(error)
        known = (project_service.NOT_A_PROJECT, project_service.NEWER_PROJECT, project_service.DAMAGED_PROJECT_TIMELINE)
        if said not in known and not said.startswith('Proje dosyası bozuk ya da yarım kalmış (satır '):
            raise Broken(f'proje açma hatası anlaşılır değil: {said!r} · {body[:120]!r}')


CHECKS = [check_story, check_templates, check_versions, check_story_guide, check_project_file]


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for seed in range(first, first + runs):
            rng = random.Random(seed)
            check = CHECKS[seed % len(CHECKS)]
            try:
                check(rng, folder)
            except Broken as error:
                found[check.__name__].append({'seed': seed, 'problem': str(error)[:500]})
            except Exception as error:   # noqa: BLE001
                found[check.__name__].append({'seed': seed, 'problem': f'çöktü: {type(error).__name__}: {error}'[:300],
                                              'where': traceback.format_exc(limit=-3)[-600:]})
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()),
              'groups': {name: {'count': len(cases), 'examples': cases[:4]} for name, cases in found.items()}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


if __name__ == '__main__':
    raise SystemExit(main())
