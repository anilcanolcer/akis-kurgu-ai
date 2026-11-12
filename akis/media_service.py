"""FFmpeg process boundary, injectable for tests and reusable by media workers."""
from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path


_PROBES = {}  # (executable, path, size, mtime) -> ffmpeg's stream report; files are probed once
PROBE_TIMEOUT = 30  # seconds; a stalled network share must not hang a probe forever
_FILTERS = {}  # executable -> names of the filters that build has
# Timeline rates a source is snapped to; the NTSC ones are exact fractions.
FRAME_RATES = ((24000, 1001), (24, 1), (25, 1), (30000, 1001), (30, 1), (50, 1), (60000, 1001), (60, 1))


class RenderCancelled(RuntimeError):
    """FFmpeg was stopped on request (MediaService.cancel); not a failure."""


class MediaService:
    def __init__(self, executable, runner=None, *, low_priority=False):
        self.executable = str(executable)
        self.runner = runner or subprocess.run
        self.low_priority = low_priority  # background work (playback proxy) yields to still previews
        self._lock = threading.Lock()
        self._process = None
        self._cancelled = False

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        """Stop the running FFmpeg (if any) and refuse further runs. Safe from any thread."""
        with self._lock:
            self._cancelled = True
            process = self._process
        if process is not None:
            try:
                process.kill()
            except OSError:  # already exited
                pass

    def run(self, arguments, *, text=False, timeout=None):
        # FFmpeg prints UTF-8; the locale codec (cp1254 on Turkish Windows) cannot decode every file name.
        decoding = {'text': True, 'encoding': 'utf-8', 'errors': 'replace'} if text else {}
        command = [self.executable, *map(str, arguments)]
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        if self._cancelled:
            raise RenderCancelled('İşlem iptal edildi.')
        if self.runner is not subprocess.run:  # injected fake: called exactly as before
            return self.runner(command, capture_output=True, **decoding, creationflags=flags)
        if self.low_priority and os.name == 'nt':
            flags |= subprocess.BELOW_NORMAL_PRIORITY_CLASS
        with self._lock:
            if self._cancelled:
                raise RenderCancelled('İşlem iptal edildi.')
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, creationflags=flags, **decoding)
            self._process = process
        try:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(command, timeout, stdout, stderr) from None
            except BaseException:
                process.kill()
                process.wait()
                raise
        finally:
            with self._lock:
                self._process = None
        if self._cancelled:
            raise RenderCancelled('İşlem iptal edildi.')
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    def probe(self, path):
        """FFmpeg's description of a file. Real files are cached by size and modification time,
        because the editor asks for the same facts on every seek and render."""
        key = None
        if self.runner is subprocess.run:
            try:
                stat = os.stat(path)
                key = (self.executable, os.path.normcase(os.path.abspath(path)), stat.st_size, stat.st_mtime_ns)
            except OSError:
                pass
        if key in _PROBES:
            return _PROBES[key]
        try:
            report = self.run(['-hide_banner', '-i', path], text=True, timeout=PROBE_TIMEOUT).stderr or ''
        except subprocess.TimeoutExpired:
            return ''  # unreadable in time: callers treat it as "no duration / no audio"
        if key is not None and 'Duration:' in report:
            if len(_PROBES) > 256:
                _PROBES.clear()
            _PROBES[key] = report
        return report

    def duration(self, path):
        match = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', self.probe(path))
        if not match:
            raise ValueError('Medya süresi okunamadı.')
        return int(match.group(1))*3600 + int(match.group(2))*60 + float(match.group(3))

    def frame_rate(self, path):
        """(numerator, denominator) for a timeline showing this video at its own pace, or None if unknown.

        Snapped to the nearest standard rate (phones record slightly uneven rates such as 29.83) and
        kept between 10 and 60: slow-motion footage flagged 120/240 fps plays back at 60.
        """
        match = re.search(r'Stream #[^\n]*Video:[^\n]*?\b(\d+(?:\.\d+)?) (?:fps|tbr)\b', self.probe(path))
        rate = float(match.group(1)) if match else 0.0
        if rate <= 0:
            return None
        numerator, denominator = min(FRAME_RATES, key=lambda r: abs(rate - r[0] / r[1]))
        if abs(rate - numerator / denominator) <= 0.012 * rate:
            return numerator, denominator
        return max(10, min(60, round(rate))), 1

    def is_hdr(self, path):
        """The picture uses an HDR transfer curve (PQ or HLG), which looks washed out unless tone-mapped."""
        match = re.search(r'Stream #[^\n]*Video:[^\n]*', self.probe(path))
        return bool(match and re.search(r'smpte2084|arib-std-b67', match.group(0)))

    def has_filter(self, name):
        """This FFmpeg build has the named filter (asked once per executable)."""
        if self.executable in _FILTERS:
            return name in _FILTERS[self.executable]
        try:
            listing = self.run(['-hide_banner', '-filters'], text=True, timeout=PROBE_TIMEOUT).stdout
        except (subprocess.TimeoutExpired, OSError):
            return False
        names = set(re.findall(r'^ [A-Z.|]{2,3} (\w+)', listing or '', re.MULTILINE))
        if self.runner is subprocess.run and names:  # an injected fake must not answer for the real program
            _FILTERS[self.executable] = names
        return name in names

    def has_audio(self, path):
        return bool(re.search(r'Stream #\S+.*Audio:', self.probe(path)))

    def dimensions(self, path):
        """Displayed picture size. Phone footage is often stored landscape with a rotation flag;
        FFmpeg turns it upright when decoding, so the reported size must be turned the same way."""
        report = self.probe(path)
        match = re.search(r'Stream #.*Video:.*?\b(\d{2,5})x(\d{2,5})\b', report)
        if not match:
            raise ValueError('Video boyutları okunamadı.')
        width, height = int(match.group(1)), int(match.group(2))
        after = report[match.end():]
        following = re.search(r'\n\s*Stream #', after)
        rotation = re.search(r'rotation of (-?\d+(?:\.\d+)?) degrees', after[:following.start()] if following else after,
                             re.IGNORECASE)
        if rotation and round(abs(float(rotation.group(1)))) % 180 == 90:
            width, height = height, width
        return width - width % 2, height - height % 2

    def silences(self, path, *, noise_db=-35, minimum=0.35):
        """Silent spans as (start, end) seconds; cheap cut-point evidence for AI editing."""
        result = self.run(['-hide_banner', '-nostats', '-i', path, '-vn', '-af',
                           f'silencedetect=noise={noise_db}dB:d={minimum}', '-f', 'null', '-'], text=True)
        starts = [float(v) for v in re.findall(r'silence_start: (-?\d+(?:\.\d+)?)', result.stderr)]
        ends = [float(v) for v in re.findall(r'silence_end: (-?\d+(?:\.\d+)?)', result.stderr)]
        return [(max(0.0, a), b) for a, b in zip(starts, ends) if b > a]

    def scene_changes(self, path, *, threshold=0.3):
        """Timestamps (seconds) where the picture changes abruptly."""
        result = self.run(['-hide_banner', '-nostats', '-i', path, '-an', '-vf',
                           f"scale=320:-2,select='gt(scene,{threshold})',showinfo", '-f', 'null', '-'], text=True)
        return [float(v) for v in re.findall(r'pts_time:(\d+(?:\.\d+)?)', result.stderr)]

    def extract_frame(self, source, seconds, destination):
        return self.run(['-y', '-ss', str(seconds), '-i', source, '-frames:v', '1',
                         '-vf', 'scale=640:-2', '-q:v', '3', destination])

    def extract_audio(self, source, destination):
        return self.run(['-y', '-i', source, '-vn', '-ac', '1', '-ar', '16000',
                         '-b:a', '64k', destination])
