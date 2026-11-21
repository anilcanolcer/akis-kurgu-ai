"""Files the program makes next to the user's own: names, overwrites, downloads and update clean-up.

Rules (each was a single example in tests until 0.6.18; here every run is a new random case):
  names       every name built from a user's file name (project autosave, its lock, version history, batch
              outputs, the three ratio outputs, Shorts parts) fits Windows' 255-character limit, can really be
              created, is the plain name + suffix whenever that fits, and two different files never share one
  overwrite   an export is refused exactly when one of its outputs is the same file as the project's main
              source, a timeline clip or a media-bin item, however the path is spelt (case, slashes, '..',
              a hard link); other outputs are allowed
  downloads   two to four editors downloading the same installer or speaker model at once all end with the
              verified file; a corrupt download fails without replacing what was there; no partial file is left
  cleanup     clearing the update folder removes only the program's own installers, old partial downloads and
              an oversized install log; the kept installer, another editor's running download, other files
              and folders stay
Usage: python scripts/media-audit/files_fuzz.py <project root> [runs] [first seed]
"""
import hashlib
import io
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import traceback
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from akis import batch_export, multi_export, project_service, shorts_split, speaker_model, update_service  # noqa: E402
from akis.app_support import safe_filename  # noqa: E402
from akis.timeline_model import Clip, Timeline, Track  # noqa: E402
from akis.window.exporting import ExportMixin  # noqa: E402
from akis.window.project import ProjectMixin  # noqa: E402

LIMIT = 255                      # UTF-16 code units in one Windows path component
LETTERS = 'pqrsPQRS aAbB çÇğĞıİöÖşŞüÜ-_()1234567890'
EMOJI = '🔥🎬'                   # two UTF-16 units each


class Broken(Exception):
    pass


def units(name):
    return len(name.encode('utf-16-le')) // 2


def random_name(rng, longest=LIMIT, ending=''):
    """A valid Windows file name of a random length (often near the limit) ending in `ending`."""
    budget = longest - units(ending)
    size = rng.choice([rng.randint(1, 30), rng.randint(min(200, budget), budget), budget, budget - 1, rng.randint(1, budget)])
    size = max(1, min(size, budget))
    out = ''
    while units(out) < size:
        piece = rng.choice(EMOJI) if rng.random() < 0.05 else rng.choice(LETTERS)
        if units(out + piece) > size:
            piece = 'x'
        out += piece
    out = out.strip(' .') or 'x'
    return out + ending


def family(rng, count, ending=''):
    """Names that share a long beginning and differ only at the end (where a cut-off name would lose them)."""
    base = random_name(rng, longest=LIMIT - units(ending) - 2)
    tails = rng.sample(['', 'A', 'B', 'ç', 'Ş', '1', '22', '🔥'], count)
    return sorted({base + tail + ending for tail in tails})


def creatable(path, what):
    name = Path(path).name
    if units(name) > LIMIT:
        raise Broken(f'{what}: ad {units(name)} karakter (Windows sınırı {LIMIT}): {name[:60]}…')
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'xb'):
            pass
    except FileExistsError:
        raise Broken(f'{what}: aynı ad iki kez üretildi: {name[:80]}') from None
    except OSError as error:
        raise Broken(f'{what}: dosya oluşturulamadı ({error}): {name[:80]}') from None


def distinct(paths, what):
    keys = [os.path.normcase(str(Path(p).resolve())) for p in paths]
    if len(set(keys)) != len(keys):
        same = [p for p in paths if keys.count(os.path.normcase(str(Path(p).resolve()))) > 1]
        raise Broken(f'{what}: farklı dosyalar aynı adı aldı: {[Path(p).name[:50] for p in same[:2]]}')


def check_names(rng, folder):
    root = folder / f'n{rng.random():.12f}'[2:]
    root.mkdir()
    kind = rng.choice(['project', 'batch', 'ratio', 'shorts'])
    if kind == 'project':
        names = family(rng, rng.randint(2, 3), '.akis.json') if rng.random() < 0.6 else \
            sorted({random_name(rng, ending='.akis.json') for _ in range(rng.randint(1, 3))})
        made = []
        for name in names:
            target = root / name
            document = project_service.make_document({}, Timeline(), {}, name[-12:])
            result = project_service.save_with_snapshot(target, document, snapshot=True)
            if not result.snapshot_saved:
                raise Broken(f'proje kaydedildi ama sürüm kopyası oluşmadı ({units(name)} karakterlik ad)')
            history = project_service.versions_folder(target)
            if units(history.name) > LIMIT or not any(history.glob('*.json')):
                raise Broken(f'sürüm klasörü yazılamadı: {history.name[:60]}…')
            stub = SimpleNamespace(project_path=str(target), _recovery_lock=None, _project_autosave_lock=None)
            auto = ProjectMixin.autosave_path(stub)
            plain = str(target.resolve()) + '.autosave'
            if units(Path(plain).name) <= LIMIT and auto != plain:
                raise Broken(f'kısa bir proje adının otomatik kayıt adı değişti: {Path(auto).name}')
            lock = ProjectMixin.lock_project_autosave(stub, auto)
            if lock is None:
                raise Broken(f'otomatik kayıt kilidi alınamadı ({units(name)} karakterlik ad)')
            try:
                project_service.save(auto, document)
                if project_service.load(auto)['ai_prompt'] != name[-12:]:
                    raise Broken('otomatik kayıt başka bir projenin dosyasını okudu')
            finally:
                lock.unlock()
            made += [auto, str(history)]
        distinct(made, 'proje yan dosyaları')
    elif kind == 'batch':
        sources = []
        for name in family(rng, rng.randint(1, 3), '.mp4') + [random_name(rng, ending=rng.choice(['.mp4', '.MOV', '.mkv']))]:
            where = root / rng.choice(['a', 'b'])
            where.mkdir(exist_ok=True)
            sources.append(where / name)
            sources[-1].touch(exist_ok=True)
        sources += [rng.choice(sources) for _ in range(rng.randint(0, 2))]     # the same video chosen twice
        out = root / rng.choice(['a', 'b', 'c'])                               # often the sources' own folder
        outputs = batch_export.outputs_for([str(s) for s in sources], out)
        if len(outputs) != len(sources):
            raise Broken('toplu işlem çıktı sayısı kaynak sayısından farklı')
        keys = {os.path.normcase(str(s.resolve())) for s in sources}
        for output, source in zip(outputs, sources):
            if os.path.normcase(str(Path(output).resolve())) in keys:
                raise Broken(f'toplu işlem çıktısı bir kaynağın üzerine yazacak: {Path(output).name[:60]}')
            if units(Path(source).stem + batch_export.SUFFIX + '_99.mp4') <= LIMIT and \
                    not Path(output).name.startswith(Path(source).stem):
                raise Broken(f'kısa bir kaynağın çıktı adı değişti: {Path(output).name}')
        distinct(outputs, 'toplu işlem çıktıları')
        for output in outputs:
            creatable(output, 'toplu işlem çıktısı')
    elif kind == 'ratio':
        chosen = root / random_name(rng, ending=rng.choice(['.mp4', '_dikey.mp4', '_kare.mp4', '_yatay.mp4']))
        outputs = [path for _, _, path in multi_export.targets(str(chosen))]
        if len(outputs) != 3:
            raise Broken('üç oran için üç çıktı beklenirdi')
        distinct(outputs, 'üç oranlı çıktı')
        for output in outputs:
            creatable(output, 'oranlı çıktı')
    else:
        titles = [rng.choice(['', random_name(rng, 120), random_name(rng), 'Giriş', 'GİRİŞ', 'giriş', '🔥🔥', '...'])
                  for _ in range(rng.randint(1, 12))]
        project = random_name(rng)
        outputs = shorts_split.outputs_for(root, titles, safe_filename(project))
        if len(outputs) != len(titles):
            raise Broken('her parça için bir çıktı beklenirdi')
        distinct(outputs, 'Shorts parçaları')
        for output in outputs:
            creatable(output, 'Shorts parçası')


def spellings(rng, path, folder):
    """Other ways to write the same path."""
    text = str(path)
    flipped = ''.join(c.swapcase() if rng.random() < 0.5 and c.isascii() else c for c in text)
    forms = [text, flipped, text.replace('\\', '/'),
             str(path.parent / '.' / path.name),
             str(path.parent / 'gecici' / '..' / path.name),
             str(folder / path.parent.name / '..' / path.parent.name / path.name)]
    return rng.choice(forms)


def check_overwrite(rng, folder):
    root = folder / f'o{rng.random():.12f}'[2:]
    (root / 'medya').mkdir(parents=True)
    (root / 'diger').mkdir()
    files = []
    for index in range(rng.randint(3, 6)):
        path = root / 'medya' / random_name(rng, 60, f'_{index}.mp4')
        if rng.random() < 0.85:
            path.write_bytes(b'kaynak')
        files.append(path)
    links = {}
    for path in files:
        if path.exists() and rng.random() < 0.3:
            link = root / 'diger' / f'baglanti_{path.name}'
            try:
                os.link(path, link)
                links[link] = path
            except OSError:
                pass
    roles = {path: rng.choice(['main', 'clip', 'bin', 'none', 'none']) for path in files}
    main = next((p for p in files if roles[p] == 'main'), None)
    roles.update({p: 'none' for p in files if roles[p] == 'main' and p != main})   # the project has one main video
    timeline = Timeline()
    timeline.tracks = [Track(kind='video', name='V1')]
    frame = 0
    for path in files:
        if roles[path] == 'clip':
            timeline.tracks[0].clips.append(Clip(source=str(path), start=frame, length=10))
            frame += 10
    stub = SimpleNamespace(state=SimpleNamespace(source=str(main) if main else ''),
                           media_bin=SimpleNamespace(paths=[str(p) for p in files if roles[p] == 'bin']),
                           multitrack=timeline, ui_text=lambda text, **kw: text)
    protected = [p for p in files if roles[p] != 'none']
    outputs, clashes = [], []
    for _ in range(rng.randint(1, 4)):
        pick = rng.random()
        if pick < 0.45 and protected:
            target = rng.choice(protected)
            outputs.append(spellings(rng, target, root))
            clashes.append(target)
        elif pick < 0.6 and links:
            link = rng.choice(list(links))
            outputs.append(str(link))
            if roles[links[link]] != 'none':
                clashes.append(links[link])
        elif pick < 0.8:
            target = rng.choice(files)
            outputs.append(spellings(rng, target, root))
            if roles[target] != 'none':
                clashes.append(target)
        else:
            outputs.append(str(root / rng.choice(['medya', 'diger']) / random_name(rng, 60, '_cikti.mp4')))
    with patch.object(QMessageBox, 'warning') as warning:
        allowed = ExportMixin.safe_export_paths(stub, list(outputs))
    if allowed and clashes:
        raise Broken(f'kaynak dosyanın üzerine yazmaya izin verildi ({roles[clashes[0]]}): {outputs}')
    if not allowed and not clashes:
        raise Broken(f'kaynakla çakışmayan çıktı reddedildi: {outputs}')
    if allowed == bool(warning.call_count):
        raise Broken('reddetme ile uyarı birbirini tutmuyor')


class Response(io.BytesIO):
    def __init__(self, data, chunk_pause):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}
        self.pause = chunk_pause

    def read(self, size=-1):
        if self.pause:
            time.sleep(self.pause)
        return super().read(size)


def check_downloads(rng, folder):
    root = folder / f'd{rng.random():.12f}'[2:]
    root.mkdir()
    data = rng.randbytes(rng.choice([1, 1000, 70_000, 300_000]))
    digest = hashlib.sha256(data).hexdigest()
    installer = rng.random() < 0.5
    target = root / 'AkisKurguAI-Setup-9.9.9.exe' if installer else speaker_model.path_in(root)
    before = rng.choice([None, None, 'corrupt', 'good'])
    if before:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if before == 'good' else b'eski ve bozuk')
    count = rng.randint(2, 4)
    corrupt = set(rng.sample(range(count), rng.choice([0, 0, 1, count - 1])))
    pauses = [rng.choice([0, 0.001, 0.003]) for _ in range(count)]
    barrier = threading.Barrier(count, timeout=10)
    results = [None] * count

    def client(index):
        body = data if index not in corrupt else data[:-1] + bytes([data[-1] ^ 1]) if data else b'x'
        opener = lambda request, timeout: Response(body, pauses[index])  # noqa: E731
        started = []

        def progress(*_):
            if not started:
                started.append(1)
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
        try:
            barrier_free = before == 'good'
            if barrier_free:
                barrier.abort()
            if installer:
                update = {'url': update_service.DOWNLOAD_PREFIX + 'v9.9.9/x', 'sha256': digest}
                got = update_service.download(update, target, opener=opener, progress=progress)
            else:
                got = speaker_model.download(root, opener=opener, on_progress=progress)
            results[index] = ('ok', str(got))
        except (ValueError, RuntimeError) as error:
            results[index] = ('refused', str(error))
        except BaseException as error:   # noqa: BLE001
            results[index] = ('crash', f'{type(error).__name__}: {error}')
        finally:
            if not started:
                try:
                    barrier.abort()
                except threading.BrokenBarrierError:
                    pass

    with patch.object(speaker_model, 'SHA256', digest):
        threads = [threading.Thread(target=client, args=(i,)) for i in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
    for index, (outcome, detail) in enumerate(results):
        if outcome == 'crash':
            raise Broken(f'eşzamanlı indirmede beklenmeyen hata: {detail}')
        good = index not in corrupt or before == 'good'
        if good and outcome != 'ok':
            raise Broken(f'doğru dosyayı indiren istemci başarısız oldu: {detail}')
        if outcome == 'ok' and Path(detail) != target:
            raise Broken(f'indirme başka bir yere yazıldı: {detail}')
    final = target.read_bytes() if target.exists() else None
    anyone = any(outcome == 'ok' for outcome, _ in results)
    if anyone and final != data:
        raise Broken('indirme bitti ama hedef dosya doğrulanmış dosya değil')
    if not anyone and final != (None if before is None else (data if before == 'good' else b'eski ve bozuk')):
        raise Broken('bozuk indirme mevcut dosyanın yerine geçti')
    left = [p.name for p in target.parent.iterdir() if p != target]
    if left:
        raise Broken(f'indirme sonrası geçici dosya kaldı: {left}')


def check_cleanup(rng, folder):
    root = folder / f'c{rng.random():.12f}'[2:]
    root.mkdir()
    prefix = update_service.INSTALLER_PREFIX
    old = time.time() - 3 * 24 * 3600
    expected_gone, made = set(), []

    def make(name, *, gone, age=None, size=4, directory=False):
        path = root / name
        if path.exists():
            return
        if directory:
            path.mkdir()
        else:
            path.write_bytes(b'x' * size)
        if age:
            os.utime(path, (age, age))
        made.append(name)
        if gone:
            expected_gone.add(name)

    for _ in range(rng.randint(2, 9)):
        version = f'{rng.randint(0, 2)}.{rng.randint(0, 20)}.{rng.randint(0, 30)}'
        installer = prefix + version + '.exe'
        if rng.random() < 0.5:
            installer = installer.lower() if rng.random() < 0.5 else installer.upper()
        token = ''.join(rng.choice('abcdefghij_0123') for _ in range(8))
        pick = rng.randrange(10)
        if pick == 0:
            make(installer, gone=True)
        elif pick == 1:
            make(installer + '.part', gone=True)
        elif pick == 2:
            make(f'{installer}.{token}.part', gone=False)                    # another editor still downloading
        elif pick == 3:
            make(f'{installer}.{token}.part', gone=True, age=old)            # left behind days ago
        elif pick == 4:
            make(rng.choice(['notlar.txt', 'Benim videom.mp4', prefix + 'notlar.txt', installer + '.bak',
                             prefix + '1.2.exe', prefix + version + '.exe.txt', 'kurulum.exe']), gone=False)
        elif pick == 5:
            make(rng.choice([installer, installer + '.klasor']), gone=False, directory=True)
        elif pick == 6:
            make(update_service.INSTALL_LOG, gone=False, size=10)
        elif pick == 7:
            make(update_service.INSTALL_LOG, gone=True, size=update_service.INSTALL_LOG_LIMIT + 1)
        else:
            make(installer, gone=True, age=old)
    keep = None
    if made and rng.random() < 0.5:
        keep = rng.choice(made)
        expected_gone.discard(keep)
    removed = update_service.cleanup_update_dir(root, keep=str(root / keep) if keep else None)
    still = {p.name for p in root.iterdir()}
    for name in made:
        if name in expected_gone and name in still:
            raise Broken(f'eski güncelleme dosyası silinmedi: {name}')
        if name not in expected_gone and name not in still:
            raise Broken(f'silinmemesi gereken dosya silindi: {name} (tutulacak: {keep})')
    if sorted(removed) != sorted(expected_gone):
        raise Broken(f'silinenler listesi yanlış: {sorted(removed)} / {sorted(expected_gone)}')


CHECKS = [check_names, check_overwrite, check_downloads, check_cleanup]


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    tmp = tempfile.mkdtemp(prefix='akis-files-')
    try:
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()),
              'groups': {name: {'count': len(cases), 'examples': cases[:4]} for name, cases in found.items()}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


if __name__ == '__main__':
    raise SystemExit(main())
