"""Real-UI flow: "✦ Prompt ile kurgula" with the AI service replaced by fixed replies (fake_ai_launch.py).

The request is typed and the button pressed as a person would; what the editor sends is logged (pictures,
the request text); the plan review dialog is accepted; the edit is exported and read frame by frame; undo and
redo are pressed. Then a reply that is not a plan is answered, and the edit must stay as it was.
Nothing reaches an AI service and the Windows credential store is not touched.

Usage: python flow_ai.py <workdir>          (source only: the fake service is patched into the Python code)
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402
import uitest_media as M  # noqa: E402
import flow_edges_lib as L  # noqa: E402
import flow_more_lib as F  # noqa: E402

work = Path(sys.argv[1])
work.mkdir(parents=True, exist_ok=True)
video = work / 'AI çekimi ğ' / 'ai örnek.mp4'
if not video.exists():
    M.make(video)
reply_file, log_file = work / 'fake-reply.txt', work / 'fake-requests.jsonl'
log_file.unlink(missing_ok=True)
PLAN = {'summary': 'İki parça: 1–3 sn ve 5–7 sn.', 'segments': [{'source': 0, 'start': 1.0, 'end': 3.0},
                                                                 {'source': 0, 'start': 5.0, 'end': 7.0}],
        'title': 'Deneme başlığı ğüş'}
reply_file.write_text(json.dumps(PLAN, ensure_ascii=False), encoding='utf-8')
os.environ['FAKE_AI_REPLY'], os.environ['FAKE_AI_LOG'] = str(reply_file), str(log_file)
results = {}


def record(name, ok, **detail):
    results[name] = {'ok': bool(ok), **detail}
    print(name, 'OK' if ok else 'FAILED', json.dumps(detail, ensure_ascii=False, default=str)[:900], flush=True)


process, app, window = U.start(settings=work / 'settings-ai.ini',
                               command=[str(U.PYTHON), str(Path(__file__).resolve().parent / 'fake_ai_launch.py')])
process.main = window.handle
try:
    L.add(window, app, video, 8)
    F.tab(window, '✦ AI Kurgu')
    edits = window.descendants(control_type='Edit')
    secret = [e for e in edits if e.element_info.element.CurrentIsPassword]
    remember = window.child_window(title="Windows'ta güvenli sakla", control_type='CheckBox')
    if remember.get_toggle_state():
        remember.toggle()
    secret[0].set_edit_text('sk-test-anahtar')
    prompt = min((e for e in edits if not e.element_info.element.CurrentIsPassword),
                 key=lambda e: e.rectangle().top)
    prompt.set_focus()
    U.keyboard.send_keys('Sadece 1-3 ve 5-7. saniyeleri tut', with_spaces=True, pause=0.02)

    try:
        U.press(window, 'Prompt ile kurgula')
        review = F.wait_dialog(process, contains='', title='', timeout=120)
        shown = F.texts_of(review)
        boxes = [c.window_text() for c in review.descendants(control_type='CheckBox')]
        F.click(review, 'Seçilenleri uygula')
        U.wait_for(lambda: any('AI kurgusu uygulandı' in t for t in U.status(window)), timeout=30, what='uygulama')
        after = L.clock(window)
        sent = [json.loads(line) for line in log_file.read_text(encoding='utf-8').splitlines()]
        L.keys(window, '^e')
        U.file_dialog(app, work / 'ai kurgusu ğ.mp4')
        F.answer(process, 'başarıyla', timeout=120)
        frames = M.frames(work / 'ai kurgusu ğ.mp4')
        heard = M.seconds(work / 'ai kurgusu ğ.mp4')
        expected = list(range(30, 90)) + list(range(150, 210))
        L.keys(window, '^z')
        undone = L.clock(window)
        L.keys(window, '^y')
        redone = L.clock(window)
        record('prompt edit', frames == expected and abs(after[1] - 4.0) < 0.05 and abs(undone[1] - 8.0) < 0.05
               and abs(redone[1] - 4.0) < 0.05 and sent and sent[0]['pictures'] > 0,
               review_texts=shown[:8], review_boxes=boxes, clock_after=after, undo=undone, redo=redone,
               requests=[{k: (v if k != 'prompt' else ('Sadece 1-3' in v)) for k, v in s.items()} for s in sent],
               frames_ok=frames == expected, frame_runs=[f for f in frames[:3]] + ['…'] + frames[-3:], heard=heard)
    except Exception as exc:  # noqa: BLE001
        record('prompt edit', False, error=f'{type(exc).__name__}: {exc}', trace=traceback.format_exc()[-1200:],
               dialogs=[(d.window_text(), F.texts_of(d)[:6], F.buttons(d)) for d in F.dialogs(process)])

    try:
        reply_file.write_text('Bu bir plan değil, üzgünüm.', encoding='utf-8')
        before = L.clock(window)
        U.press(window, 'Prompt ile kurgula')
        box = F.wait_dialog(process, timeout=120)
        texts = F.texts_of(box)
        F.click(box, r'(OK|Tamam)')
        time.sleep(1)
        record('reply that is not a plan', L.clock(window) == before and not any(
            w in ' '.join(texts) for w in ('Traceback', 'Expecting value', 'JSONDecodeError', 'NoneType')),
            message=texts, clock=L.clock(window))
    except Exception as exc:  # noqa: BLE001
        record('reply that is not a plan', False, error=f'{type(exc).__name__}: {exc}',
               dialogs=[(d.window_text(), F.texts_of(d)[:6], F.buttons(d)) for d in F.dialogs(process)])
finally:
    U.stop(process)
    U.clean_recovery()
    (work / 'flow_ai.json').write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
