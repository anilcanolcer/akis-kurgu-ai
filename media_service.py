"""FFmpeg process boundary, injectable for tests and reusable by media workers."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


class MediaService:
    def __init__(self, executable, runner=None):
        self.executable = str(executable)
        self.runner = runner or subprocess.run

    def run(self, arguments, *, text=False):
        return self.runner([self.executable, *map(str, arguments)], capture_output=True,
                           text=text, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def duration(self, path):
        result = self.run(['-hide_banner', '-i', path], text=True)
        match = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', result.stderr)
        if not match:
            raise ValueError('Medya süresi okunamadı.')
        return int(match.group(1))*3600 + int(match.group(2))*60 + float(match.group(3))

    def has_audio(self, path):
        result = self.run(['-hide_banner', '-i', path], text=True)
        return bool(re.search(r'Stream #\S+.*Audio:', result.stderr))

    def extract_frame(self, source, seconds, destination):
        return self.run(['-y', '-ss', str(seconds), '-i', source, '-frames:v', '1',
                         '-vf', 'scale=640:-2', '-q:v', '3', destination])

    def extract_audio(self, source, destination):
        return self.run(['-y', '-i', source, '-vn', '-ac', '1', '-ar', '16000',
                         '-b:a', '64k', destination])
