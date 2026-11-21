"""Small UI steps shared by the edge-case scripts."""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uia_env as U  # noqa: E402


def clock(window):
    for text in U.status(window):
        found = re.fullmatch(r'(\d+):(\d+\.\d+) / (\d+):(\d+\.\d+)', text.strip())
        if found:
            return int(found[1]) * 60 + float(found[2]), int(found[3]) * 60 + float(found[4])
    return None


def keys(window, text):
    window.set_focus()
    U.keyboard.send_keys(text, pause=0.05)
    time.sleep(0.4)


def add(window, app, video, seconds):
    U.press(window, 'Video ekle')
    U.file_dialog(app, video)
    U.wait_for(lambda: (clock(window) or (0, 0))[1] > seconds - 0.2, timeout=60, what='video eklenmesi')


def export(window, app, path, replace=None):
    keys(window, '^e')
    return U.file_dialog(app, path, replace=replace)
