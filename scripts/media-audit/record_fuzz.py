"""The recording window under random clicks: start, stop from the bar or the window, Esc, closing with each
answer, the preview, another folder, a blocked folder, and an ffmpeg that stops by itself, fails or hangs.

Rules, checked after every step:
  while recording  the program and the window are minimised, the bar is shown in the window's language,
                   Esc changes nothing, the window cannot be closed by its buttons and no new start is offered
  otherwise        no bar, the program is back in its old state, the window is not minimised, the clock is
                   stopped, "Recording…" is not shown and a new recording can be started
  ffmpeg stops by itself, fails at the end or hangs: the window leaves recording and says why
  "keep" or Stop   the window closes with the file, which is in the chosen folder and not empty
  "drop"           the window closes and the file is gone
  "continue"       the recording goes on, out of the way again
  never            a recorded file with content is deleted without "drop"; an ffmpeg is left running
Usage: python scripts/media-audit/record_fuzz.py <project root> [runs] [first seed]
"""
import json
import os
import random
import subprocess
import sys
import tempfile
import traceback
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()))

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])

from akis import i18n  # noqa: E402
from akis.record_dialog import MIC_ONLY, RecordDialog  # noqa: E402


class Broken(Exception):
    pass


class FakeScreen:
    def __init__(self, rng, index):
        self.rect = QRect(rng.choice([-1920, 0, 1920, 2560]) * index, rng.choice([0, -180, 200]) * (index > 0),
                          rng.choice([1280, 1366, 1920, 2560]), rng.choice([720, 768, 1080, 1440]))
        self.ratio = rng.choice([1.0, 1.25, 1.5, 2.0])
        self.readable = rng.random() < 0.8
        self._name = f'Ekran {index + 1}'

    def geometry(self):
        return self.rect

    def availableGeometry(self):
        return self.rect

    def devicePixelRatio(self):
        return self.ratio

    def name(self):
        return self._name

    def grabWindow(self, _):
        if not self.readable:
            return QPixmap()
        picture = QPixmap(64, 36)
        picture.fill(Qt.GlobalColor.darkCyan)
        return picture


class FakeDevices:
    videoInputs = staticmethod(lambda: [])
    audioInputs = staticmethod(lambda: [])
    defaultAudioInput = staticmethod(lambda: None)


class Ffmpeg:
    """A screen-recording ffmpeg whose end is chosen by the run: finishes, fails, writes nothing or hangs."""

    def __init__(self, path, ending):
        self.path, self.ending, self.returncode, self.said = Path(path), ending, None, b''
        self.wrote = False

    def write(self, data):
        with open(self.path, 'ab') as file:
            file.write(data)
        self.wrote = self.wrote or bool(data)

    def poll(self):
        return self.returncode

    def die(self, code, said, partial):
        if partial:
            self.write(b'yarim')
        self.returncode, self.said = code, said

    def kill(self):
        if self.returncode is None:
            self.returncode = -9

    def communicate(self, input=None, timeout=None):
        if self.returncode is not None:
            return b'', self.said
        if self.ending == 'ok':
            self.write(b'video' * 20)
            self.returncode = 0
            return b'', b''
        if self.ending == 'fail':
            self.write(b'yarim')
            self.returncode, self.said = 1, b'Conversion failed!'
            return b'', self.said
        if self.ending == 'empty':
            self.returncode = 1
            return b'', b''
        self.write(b'yarim')                      # hangs: asked to finish, does not answer in time
        raise subprocess.TimeoutExpired('ffmpeg', timeout or 0)


class Session:
    def __init__(self, rng, root, parent, parent_state, screens):
        self.rng, self.root, self.parent, self.parent_state = rng, root, parent, parent_state
        self.language = rng.choice(['tr', 'en'])
        self.good = root / rng.choice(['Akış Kurgu kayıtları', 'kayıtlar', 'Türkçe kullanıcı/Videolar'])
        self.dialog = RecordDialog(parent, language=self.language, folder=self.good, devices=FakeDevices,
                                   executable='ffmpeg')
        self.dialog.screen_recorder.popen = self.popen
        self.processes, self.dropped, self.choices = [], set(), []
        self.asked = 0
        self.dialog.ask_while_recording = self.unexpected_question   # a real question box would wait forever
        self.dialog.show()
        self.log = []

    def unexpected_question(self):
        self.asked += 1
        return 'continue'

    def t(self, text):
        return i18n.translate(text, self.language)

    def popen(self, command, **options):
        process = Ffmpeg(options['stdout'].name, self.rng.choice(['ok', 'ok', 'ok', 'fail', 'empty', 'hang']))
        self.processes.append(process)
        return process

    @property
    def finished(self):
        return not self.dialog.isVisible()

    def step(self):
        d, rng = self.dialog, self.rng
        actions = ['tick', 'esc', 'close', 'preview', 'alt_f4_bar']
        if d.recording:
            actions += ['bar_stop', 'bar_stop', 'window_stop', 'die', 'tick', 'tick', 'quit']
        else:
            actions += ['start', 'start', 'start', 'blocked_start', 'pick', 'folder']
        action = rng.choice(actions)
        self.log.append(action)
        was_recording = d.recording
        current = self.processes[-1] if self.processes else None
        if action == 'tick':
            d._tick()
        elif action == 'esc':
            QTest.keyClick(d, Qt.Key.Key_Escape)
            if was_recording and not d.recording:
                raise Broken('Esc kaydı bitirdi')
            if self.asked:
                raise Broken('Esc kaydı durdurmak için soru sordu')
        elif action == 'close':
            choice = rng.choice(['keep', 'drop', 'continue'])
            self.choices.append(choice)
            self.log[-1] += ':' + choice
            if was_recording and choice == 'drop':
                self.dropped.add(current.path)
            d.ask_while_recording = lambda: choice
            try:
                d.reject()
            finally:
                d.ask_while_recording = self.unexpected_question
            if was_recording and choice == 'continue' and not d.recording:
                raise Broken('"Kayda devam et" kaydı durdurdu')
        elif action == 'preview' and d.bar is not None:
            d.bar.preview_button.click()
        elif action == 'alt_f4_bar' and d.bar is not None:
            d.bar.close()
            if not d.bar.isVisible():
                raise Broken('durdurma çubuğu Alt+F4 ile kapandı; kayda dönüş yolu kalmadı')
        elif action in ('bar_stop', 'window_stop'):
            (d.bar.button if action == 'bar_stop' else d.stop_button).click()
        elif action == 'die':
            said = rng.choice([b'', b'Could not find video device', b'I/O error'])
            current.die(rng.choice([1, -22, 255]), said, rng.random() < 0.5)
            d._tick()
            if d.recording:
                raise Broken('ffmpeg durdu ama pencere hâlâ kaydediyor')
            reason = said.decode() or 'çıkış kodu'
            if reason not in d.status.text():
                raise Broken(f'ffmpeg durdu, neden yazılmadı: {d.status.text()!r}')
        elif action == 'quit':
            d.done(QDialog.DialogCode.Rejected)        # the program closes while a recording runs
        elif action == 'start':
            if d.folder != self.good and rng.random() < 0.5:
                d.folder = self.good
            if d.start_button.isEnabled():
                d.start_button.click()
                kind = d.current_source()[0]
                if kind != MIC_ONLY and not d.recording and d.folder == self.good:
                    raise Broken(f'kayıt başlamadı: {d.status.text()!r}')
        elif action == 'blocked_start':
            blocked = self.root / f'engelli{rng.random():.9f}'[2:]
            blocked.write_bytes(b'')                   # a file where the folder should be
            d.folder = blocked
            if d.start_button.isEnabled():
                d.start_button.click()
                if d.recording:
                    raise Broken('kayıt klasörü yokken kayıt başladı')
                if not d.status.text():
                    raise Broken('klasör oluşturulamadı, neden yazılmadı')
        elif action == 'pick':
            d.source.setCurrentIndex(rng.randrange(d.source.count()))
        elif action == 'folder':
            with patch('akis.record_dialog.QFileDialog.getExistingDirectory', return_value=str(self.good)):
                d.folder_button.click()
            if d.folder != self.good:
                raise Broken('seçilen kayıt klasörü kullanılmadı')
        if action in ('bar_stop', 'window_stop', 'close') and was_recording and not d.recording \
                and not self.finished and current.ending == 'ok':
            raise Broken(f'kayıt durdu ama pencere dosyayla kapanmadı: {d.status.text()!r}')
        if action in ('bar_stop', 'window_stop') and current is not None and current.ending != 'ok' \
                and was_recording and not d.status.text():
            raise Broken('kayıt kapatılamadı, neden yazılmadı')
        if self.asked:
            raise Broken(f'beklenmeyen bir anda "Kayıt sürüyor" sorusu soruldu ({action})')
        self.check()

    def check(self):
        d, parent = self.dialog, self.parent
        if self.finished:
            return
        recording = d.recording
        if recording != (d.bar is not None):
            raise Broken(f'kayıt {"sürüyor" if recording else "durdu"} ama çubuk {"yok" if d.bar is None else "duruyor"}')
        if recording:
            if not d.isMinimized():
                raise Broken('kayıt sürerken kayıt penceresi ekranda')
            if self.parent_state is not None and not parent.isMinimized():
                raise Broken('kayıt sürerken program ekranda')
            if not d.bar.isVisible():
                raise Broken('kayıt sürüyor, çubuk görünmüyor')
            if d.bar.button.text() != self.t('■ Durdur ve ekle') or d.bar.preview_button.text() != self.t('Önizleme'):
                raise Broken(f'çubuk pencerenin dilinde değil: {d.bar.button.text()!r}')
            if d.close_button.isEnabled() or d.start_button.isEnabled() or d.folder_button.isEnabled():
                raise Broken('kayıt sürerken Kapat, Başlat ya da klasör düğmesi açık')
        else:
            if d.isMinimized():
                raise Broken('kayıt bitti, pencere küçük kaldı')
            if self.parent_state is not None and parent.windowState() != self.parent_state:
                raise Broken(f'program eski haline dönmedi: {parent.windowState()} / {self.parent_state}')
            if d.ticker.isActive():
                raise Broken('kayıt bitti, süre saymaya devam ediyor')
            if d.status.text() == self.t('Kaydediliyor…'):
                raise Broken('kayıt yokken "Kaydediliyor…" yazıyor')
            if d.current_source()[0] != MIC_ONLY and not d.start_button.isEnabled():
                raise Broken(f'kayıt bitti, yeni kayıt başlatılamıyor: {d.status.text()!r}')

    def finish(self):
        d = self.dialog
        if not self.finished:
            d.done(QDialog.DialogCode.Rejected)
        if d.bar is not None:
            raise Broken('pencere kapandı, çubuk kaldı')
        if self.parent_state is not None and self.parent.windowState() != self.parent_state:
            raise Broken('pencere kapandı, program eski haline dönmedi')
        if d.screen_timer.isActive():
            raise Broken('pencere kapandı, ekran önizlemesi sürüyor')
        if any(p.returncode is None for p in self.processes):
            raise Broken('pencere kapandı, ffmpeg çalışmaya devam ediyor')
        if d.result() == QDialog.DialogCode.Accepted:
            path = Path(d.path or '')
            if not path.is_file() or path.stat().st_size == 0:
                raise Broken(f'pencere kayıtla kapandı ama dosya yok ya da boş: {d.path}')
            if path.parent != self.good:
                raise Broken(f'kayıt seçilen klasörde değil: {path.parent}')
        for process in self.processes:
            if process.wrote and process.path not in self.dropped and not process.path.exists():
                raise Broken(f'içi dolu bir kayıt "Kaydı sil" seçilmeden silindi ({process.ending})')
            if process.path in self.dropped and process.path.exists():
                raise Broken('"Kaydı sil" seçildi ama dosya duruyor')
        d.deleteLater()


def run(rng, root):
    screens = [FakeScreen(rng, i) for i in range(rng.randint(1, 3))]
    shape = rng.choice(['normal', 'maximized', 'hidden', 'none'])
    parent = None if shape == 'none' else QMainWindow()
    if shape == 'normal':
        parent.show()
    elif shape == 'maximized':
        parent.showMaximized()
    state = parent.windowState() if shape in ('normal', 'maximized') else None
    try:
        with patch.object(RecordDialog, '_screens', staticmethod(lambda: screens)):
            for _ in range(rng.randint(1, 3)):
                session = Session(rng, root, parent, state, screens)
                try:
                    for _ in range(rng.randint(3, 14)):
                        session.step()
                        if session.finished:
                            break
                    session.finish()
                except Broken as error:
                    raise Broken(f'{error} · adımlar: {session.log}') from None
                finally:
                    if session.dialog.isVisible():
                        session.dialog.done(0)
                app.processEvents()
    finally:
        if parent is not None:
            parent.close()
            parent.deleteLater()
        app.processEvents()


def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    found = defaultdict(list)
    for seed in range(first, first + runs):
        rng = random.Random(seed)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                run(rng, Path(tmp))
            except Broken as error:
                found['record'].append({'seed': seed, 'problem': str(error)[:600]})
            except Exception as error:   # noqa: BLE001
                found['record'].append({'seed': seed, 'problem': f'çöktü: {type(error).__name__}: {error}'[:300],
                                        'where': traceback.format_exc(limit=-3)[-700:]})
    report = {'runs': runs, 'failed': sum(len(v) for v in found.values()),
              'groups': {name: {'count': len(cases), 'examples': cases[:4]} for name, cases in found.items()}}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if found else 0


if __name__ == '__main__':
    raise SystemExit(main())
