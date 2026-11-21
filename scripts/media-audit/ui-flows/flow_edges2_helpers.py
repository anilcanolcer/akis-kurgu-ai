import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402


def dialogs(process):
    out = []
    for w in U.Desktop(backend='uia').windows():
        if w.process_id() in process.owners:
            out += [c for c in w.children() if c.element_info.control_type == 'Window']
    return out


def message(process, timeout=20, contains=''):
    def find():
        for d in dialogs(process):
            if d.element_info.class_name == '#32770':
                continue
            texts = [c.window_text() for c in d.descendants(control_type='Text') if c.window_text()]
            if texts and contains in ' '.join(texts):
                return d, texts, [b.window_text() for b in d.descendants(control_type='Button')]
        return None
    return U.wait_for(find, timeout=timeout, what='ileti penceresi')


def click(box, pattern):
    for b in box.descendants(control_type='Button'):
        if re.fullmatch(pattern, b.window_text().replace('&', '')):
            b.invoke()
            return b.window_text()
    raise LookupError(f'{pattern} yok: {[b.window_text() for b in box.descendants(control_type="Button")]}')
