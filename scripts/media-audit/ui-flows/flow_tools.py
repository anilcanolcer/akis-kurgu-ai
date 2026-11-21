"""Real-UI flow over the edit tools, each checked on what it writes:

Session 1 (a quiet 8 s numbered video):
  title layer (Düzenle › Başlık katmanı + Enter) – the first 3 s change, the rest is untouched;
  speed 2.00× – every second frame, half the length, the sound still at its own pitch;
  "-14 LUFS" – the export's measured loudness;
  "Windows sesiyle WAV oluştur" – the WAV and its clip at the playhead;
  autosave, the editor killed, restarted, "Aç" on the recovery offer – the same edit comes back.
Session 2 (Turkish speech from the Windows voice): "Konuşmayı Türkçe metne çevir" with local Whisper, then
  "Yerel altyazıyı zaman çizelgesine ekle" and an export – captions are drawn while words are spoken.
Session 3 (24 s with 1 s pauses): "Sessizlikleri çıkar" – only silent frames are cut.

Usage: python flow_tools.py <workdir> [packaged exe]
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402
import longmedia as LM  # noqa: E402
import flow_edges_lib as L  # noqa: E402
import flow_more_lib as F  # noqa: E402

work = Path(sys.argv[1])
exe = Path(sys.argv[2]) if len(sys.argv) > 2 else None
work.mkdir(parents=True, exist_ok=True)
out = work / 'Araç çıktıları'
shutil.rmtree(out, ignore_errors=True)
out.mkdir()
results = {'mode': 'exe' if exe else 'source'}
started = time.time()
process = None


def record(name, ok, **detail):
    results[name] = {'ok': bool(ok), 't': round(time.time() - started), **detail}
    print(name, 'OK' if ok else 'FAILED', json.dumps(detail, ensure_ascii=False, default=str)[:700], flush=True)


ONLY = [s.strip() for s in os.environ.get('FLOW_SECTIONS', '').split(',') if s.strip()]


def section(name):
    def wrap(function):
        if ONLY and name not in ONLY:
            return function
        try:
            function()
        except Exception as exc:  # noqa: BLE001
            record(name, False, error=f'{type(exc).__name__}: {exc}', trace=traceback.format_exc()[-1500:],
                   dialogs=[(d.window_text(), F.texts_of(d)[:6], F.buttons(d)[:8]) for d in F.dialogs(process)])
            for d in F.dialogs(process):
                try:
                    d.close()
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1)
        return function
    return wrap


help_text = F.description


def by_help(window, kind, fragment):
    for c in window.descendants(control_type=kind):
        if fragment in help_text(c):
            return c
    raise LookupError(f'{kind} with help "{fragment}" yok')


combo_with = F.combo_offering


def export(path, timeout=300):
    L.keys(window, '^e')
    question = None
    try:
        box = F.wait_dialog(process, contains='', timeout=4)
        question = F.texts_of(box)
        F.click(box, r'(Yes|Evet)')
    except TimeoutError:
        pass
    U.file_dialog(app, path)
    return question, F.answer(process, 'başarıyla', timeout=timeout)


def gray_frames(path, w=120, h=212):
    raw = subprocess.run([M.FFMPEG, '-v', 'error', '-i', str(path), '-vf', f'scale={w}:{h}:flags=area', '-f', 'rawvideo',
                          '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w).astype(int)


def loudness(path):
    text = subprocess.run([M.FFMPEG, '-hide_banner', '-nostats', '-i', str(path), '-af', 'ebur128', '-f', 'null', '-'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace').stderr
    found = re.findall(r'I:\s+(-?[\d.]+) LUFS', text)
    return float(found[-1]) if found else None


def saved_tracks(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    timeline = data.get('timeline', {})
    return data, [(t.get('kind'), t.get('name'), [(c.get('start'), c.get('length'), c.get('text'), Path(c.get('source') or '').name)
                                                  for c in t.get('clips', [])]) for t in timeline.get('tracks', [])]


# ---------------------------------------------------------------------------------------------------------
quiet = work / 'Sessiz çekim' / 'kısık ses ğ.mp4'
if not quiet.exists():
    loud_source = M.make(work / 'Sessiz çekim' / 'kaynak.mp4')
    M.ff(['-y', '-i', str(loud_source), '-c:v', 'copy', '-af', 'volume=0.1', '-c:a', 'aac', '-b:a', '192k', str(quiet)])
settings = work / 'settings-tools.ini'
process, app, window = U.start(exe=exe, settings=settings)
process.main = window.handle
try:
    L.add(window, app, quiet, 8)

    @section('clean export')
    def _clean():
        question, message = export(out / 'temiz.mp4')
        shown = M.frames(out / 'temiz.mp4')
        results['quiet_lufs'] = loudness(out / 'temiz.mp4')
        record('clean export', shown == list(range(240)), lufs=results['quiet_lufs'], question=question)

    @section('title layer')
    def _title():
        F.tab(window, 'Düzenle')
        edit = by_help(window, 'Edit', "Enter'a basınca uygulanır")
        edit.set_focus()
        U.keyboard.send_keys('Başlık ğüş deneme', with_spaces=True, pause=0.02)
        U.keyboard.send_keys('{ENTER}')
        time.sleep(0.8)
        said = [t for t in U.status(window) if 'Başlık' in t][:2]
        question, message = export(out / 'başlıklı.mp4')
        clean, titled = gray_frames(out / 'temiz.mp4'), gray_frames(out / 'başlıklı.mp4')
        changed = [int((np.abs(a - b) > 40).sum()) for a, b in zip(clean, titled)]
        first, rest = changed[:90], changed[92:]
        record('title layer', min(first) > 50 and max(rest) < 20, status=said, frames=len(titled),
               changed_first_3s=(min(first), max(first)), changed_after=(max(rest) if rest else None))

    @section('speed 2x')
    def _speed():
        F.tab(window, 'Düzenle')
        combo = combo_with(window, '2.00×')
        F.choose(combo, '2.00×')
        time.sleep(0.5)
        question, message = export(out / 'iki kat ğ.mp4')
        shown = M.frames(out / 'iki kat ğ.mp4')
        info = M.info(out / 'iki kat ğ.mp4')
        heard = M.seconds(out / 'iki kat ğ.mp4', step=0.25)
        readable = [(i, x) for i, x in enumerate(shown) if x is not None]
        off = [(i, x) for i, x in readable if x != 2 * i]         # output frame n shows source frame 2n
        F.choose(combo, '1.00×')
        time.sleep(0.5)
        record('speed 2x', abs(info['seconds'] - 4.0) < 0.1 and not off, info=info, off=off[:8],
               heard=heard, first=shown[:6])

    @section('loudness -14 LUFS')
    def _loudness():
        F.tab(window, 'Yayın')
        box = window.child_window(title_re=".*-14 LUFS.*", control_type='CheckBox')
        box.toggle()
        time.sleep(0.5)
        question, message = export(out / 'yüksek ses.mp4')
        measured = loudness(out / 'yüksek ses.mp4')
        heard = M.seconds(out / 'yüksek ses.mp4')
        record('loudness -14 LUFS', measured is not None and abs(measured + 14) <= 1.5, before=results.get('quiet_lufs'),
               after=measured, heard=heard)

    @section('voiceover')
    def _voice():
        F.tab(window, '✦ AI Kurgu')
        voice = by_help(window, 'ComboBox', 'Windows sesi')
        top = voice.rectangle().top
        edits = [e for e in window.descendants(control_type='Edit') if e.rectangle().bottom <= top + 2]
        edit = max(edits, key=lambda e: e.rectangle().bottom)
        edit.set_focus()
        U.keyboard.send_keys('Merhaba, bu bir deneme seslendirmesidir.', with_spaces=True, pause=0.02)
        # the playhead to about 1 s with a click on the ruler (keys would go to the text box that has focus)
        r = window.child_window(class_name='MultitrackWidget').rectangle()
        U.mouse.click(coords=(r.left + 100 + 90, r.top + 15))
        time.sleep(0.6)
        playhead = round(L.clock(window)[0] * 30)
        U.press(window, 'Windows sesiyle WAV oluştur')
        wav = out / 'seslendirme ğüş.wav'
        U.file_dialog(app, wav)
        U.wait_for(lambda: any('Seslendirme zaman çizelgesine eklendi' in t for t in U.status(window)), timeout=60,
                   what='seslendirme')
        L.keys(window, '^s')
        U.file_dialog(app, out / 'seslendirme projesi.akis.json')
        U.wait_for(lambda: (out / 'seslendirme projesi.akis.json').is_file(), timeout=20, what='proje kaydı')
        time.sleep(1)
        data, tracks = saved_tracks(out / 'seslendirme projesi.akis.json')
        voice_tracks = [t for t in tracks if t[0] == 'audio' and t[1].startswith('Seslendirme')]
        info = M.info(wav) if wav.exists() else {}
        clip = voice_tracks[0][2][0] if voice_tracks else None
        record('voiceover', wav.exists() and clip is not None and clip[0] == playhead
               and abs(clip[1] / 30 - (info.get('seconds') or 0)) < 0.1, playhead=playhead, wav=info, tracks=tracks)
        results['saved_before_crash'] = tracks

    @section('voiceover over its own wav')
    def _voice_again():
        # The WAV just made is now project media: writing a new voice-over over it must be refused.
        import hashlib
        wav = out / 'seslendirme ğüş.wav'
        before = hashlib.sha256(wav.read_bytes()).hexdigest()
        U.press(window, 'Windows sesiyle WAV oluştur')
        U.file_dialog(app, wav, replace=True)           # Windows' own "replace?" is answered Yes
        box = F.wait_dialog(process, timeout=20)
        said = F.texts_of(box)
        F.click(box, r'(OK|Tamam)')
        time.sleep(1.5)
        after = hashlib.sha256(wav.read_bytes()).hexdigest()
        busy = [t for t in U.status(window) if 'oluşturuluyor' in t]
        record('voiceover over its own wav', after == before and any('kaynak medya' in t for t in said) and not busy,
               message=said, unchanged=after == before, status=busy)

    @section('recovery after crash')
    def _recovery():
        global process, app, window
        # an edit after the save, so the recovery holds more than the saved file
        view = window.child_window(class_name='MultitrackWidget')
        r = view.rectangle()
        U.mouse.click(coords=(r.left + 100 + 200, r.top + 50))
        L.keys(window, '{HOME}' + '+{RIGHT}' * 4)
        L.keys(window, 's')                                  # split at 4 s: not saved
        time.sleep(1)
        candidates = lambda: [p for p in (out.glob('*.autosave*'))] + \
            [p for p in U.RECOVERY.glob('*.akis.json') if p.name not in U.BEFORE] if U.RECOVERY.is_dir() else []  # noqa: E731
        U.wait_for(lambda: candidates(), timeout=45, step=1, what='otomatik kayıt')
        time.sleep(1)
        files = candidates()
        recovered_tracks = [saved_tracks(p)[1] for p in files if p.suffix == '.json' or p.name.endswith('.autosave')]
        U.stop(process)                                      # the editor is killed: no clean close
        time.sleep(1)
        left = [p.name for p in files if p.exists()]
        process, app, window = U.start(exe=exe, settings=settings, args=[str(out / 'seslendirme projesi.akis.json')],
                                       recovery=None)
        process.main = window.handle
        box = F.wait_dialog(process, contains='Kurtarılmış', timeout=20)
        offer = F.texts_of(box)
        F.click(box, 'Aç')
        time.sleep(2)
        clock = L.clock(window)
        L.keys(window, '^s')
        time.sleep(2)
        data, tracks = saved_tracks(out / 'seslendirme projesi.akis.json')
        record('recovery after crash', tracks == recovered_tracks[0] and len(tracks[0][2]) == 2 if recovered_tracks else False,
               autosave_files=[p.name for p in files], left_after_kill=left, offer=offer[:2], clock=clock,
               recovered=recovered_tracks[:1], reopened_saved=tracks,
               autosave_after_save=[p.name for p in out.glob('*.autosave*')])
finally:
    if process:
        U.stop(process)

# ---------------------------------------------------------------------------------------------------------
sys.path.insert(0, str(U.REPO))
speech = work / 'Konuşma ğüş' / 'konuşma videosu.mp4'
if not speech.exists():
    from akis import tts_service
    speech.parent.mkdir(parents=True, exist_ok=True)
    wav = speech.with_suffix('.wav')
    tts_service.synthesize('Bugün hava çok güzel. Kırmızı araba yavaş yavaş yolda gidiyor. Akşam eve döneceğiz.', wav,
                           language='tr')
    M.ff(['-y', '-f', 'lavfi', '-i', 'color=c=navy:s=640x360:r=30', '-i', str(wav), '-shortest', '-c:v', 'libx264',
          '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(speech)])
process, app, window = U.start(exe=exe, settings=work / 'settings-speech.ini')
process.main = window.handle
try:
    length = M.info(speech)['seconds']
    L.add(window, app, speech, length)

    @section('local captions')
    def _captions():
        F.tab(window, '✦ AI Kurgu')
        F.choose(combo_with(window, 'Yerel Whisper'), 'Yerel Whisper')
        F.choose(combo_with(window, 'tiny'), 'tiny')
        U.press(window, 'Konuşmayı Türkçe metne çevir')
        apply = U.button(window, 'Yerel altyazıyı zaman çizelgesine ekle')
        U.wait_for(lambda: apply.is_enabled() or any('hata' in t.lower() or 'başarısız' in t.lower() for t in U.status(window)),
                   timeout=240, step=1, what='konuşma metni')
        text = [e.get_value() for e in window.descendants(control_type='Edit')
                if (e.get_value() or '').startswith('KONUŞMA METNİ')][:1]
        apply.invoke()
        time.sleep(1)
        said = [t for t in U.status(window) if 'altyazı klibi' in t]
        question, message = export(out / 'altyazılı ğ.mp4')
        # The source is a plain navy picture: bright pixels in the export are caption text.
        frames = gray_frames(out / 'altyazılı ğ.mp4', 270, 480)
        bright = [int((f > 170).sum()) for f in frames]
        per_second = [max(bright[i:i + 30]) for i in range(0, len(bright), 30)]
        spoken = per_second[:int(length) - 1]
        record('local captions', bool(said) and min(spoken) > 40 and sum(b > 40 for b in bright) > len(bright) / 2,
               status=said, transcript=text, frames=len(frames), caption_frames=sum(b > 40 for b in bright),
               brightest_per_second=per_second)

    @section('captions kept without overlap')
    def _captions_again():
        # Delete the spoken clip (Delete leaves a gap), apply the same transcript again: nothing overlaps it now,
        # so the captions already made must stay and the editor must say why nothing was added.
        r = window.child_window(class_name='MultitrackWidget').rectangle()
        U.mouse.click(coords=(r.left + 100 + 30, r.top + 50))
        time.sleep(0.5)
        L.keys(window, '{DELETE}')
        time.sleep(0.8)
        U.button(window, 'Yerel altyazıyı zaman çizelgesine ekle').invoke()
        time.sleep(1)
        said = [t for t in U.status(window) if 'örtüşmüyor' in t or 'altyazı klibi' in t]
        project = out / 'altyazı korunur.akis.json'
        L.keys(window, '^s')
        U.file_dialog(app, project)
        U.wait_for(lambda: project.is_file(), timeout=20, what='proje kaydı')
        time.sleep(1)
        data, tracks = saved_tracks(project)
        captions = [t for t in tracks if t[0] == 'text' and 'Altyazı' in (t[1] or '')]
        videos = [c for t in tracks if t[0] == 'video' for c in t[2]]
        record('captions kept without overlap', any('örtüşmüyor' in t for t in said) and captions
               and len(captions[0][2]) >= 5 and not videos,
               status=said, caption_tracks=[(t[1], len(t[2])) for t in captions], video_clips=len(videos))
finally:
    U.stop(process)

# ---------------------------------------------------------------------------------------------------------
pauses = work / 'Duraklamalı ğ' / 'duraklamalı çekim.mp4'
if not pauses.exists():
    LM.make(pauses, 24)
process, app, window = U.start(exe=exe, settings=work / 'settings-silence.ini')
process.main = window.handle
try:
    L.add(window, app, pauses, 24)

    @section('silence removal')
    def _silences():
        F.tab(window, '✦ AI Kurgu')
        U.press(window, 'Sessizlikleri çıkar')
        box = F.wait_dialog(process, title='Sessiz', timeout=20)
        apply = [b for b in box.descendants(control_type='Button') if b.window_text() == 'Sessizlikleri kes'][0]
        U.wait_for(lambda: apply.is_enabled(), timeout=60, what='ölçüm')
        summary = [t for t in F.texts_of(box) if 'kes' in t.lower() or '→' in t]
        apply.invoke()
        time.sleep(1)
        said = [t for t in U.status(window) if 'sessiz yer kesildi' in t]
        question, message = export(out / 'sessizliksiz.mp4')
        shown = [x for x in LM.frames(out / 'sessizliksiz.mp4') if x is not None]
        dropped = sorted(set(range(24 * 30)) - set(shown))
        loud_dropped = [f for f in dropped if not any(LM.silent(f + d) for d in range(-9, 10))]
        kept_silent = [f for f in shown if all(LM.silent(f + d) for d in range(-9, 10))]
        record('silence removal', dropped and not loud_dropped and shown == sorted(shown),
               summary=summary, status=said, kept=len(shown), dropped=len(dropped), loud_dropped=loud_dropped[:10],
               deep_silence_kept=len(kept_silent), runs=LM.runs(shown)[:8], clock=L.clock(window))
finally:
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_tools.json').write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps({k: v.get('ok') if isinstance(v, dict) else v for k, v in results.items()}, ensure_ascii=False))
