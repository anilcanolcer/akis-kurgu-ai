"""Export progress: read ffmpeg's -progress output, estimate the time left, check the free space first.

Pure helpers; the media service feeds parse() with ffmpeg's lines, the main window shows text().
"""
import shutil
import time
from pathlib import Path

PROGRESS_ARGS = ('-progress', 'pipe:1', '-nostats')
MIN_FRACTION_FOR_ESTIMATE = 0.03   # before this the speed is mostly start-up cost and the guess jumps around
BITS_PER_PIXEL = 0.12              # generous for libx264 at its default quality; real files are usually smaller
AUDIO_BITS_PER_SECOND = 192_000
SPACE_MARGIN = 1.25
MIN_FREE_BYTES = 50 * 1024 * 1024


def parse(line):
    """Seconds of output written so far from one -progress line, or None for any other line."""
    if isinstance(line, bytes):
        line = line.decode('ascii', 'replace')
    key, _, value = line.strip().partition('=')
    # out_time_us is microseconds; out_time_ms is too, despite its name (a long-standing ffmpeg quirk).
    if key in ('out_time_us', 'out_time_ms'):
        try:
            return max(0.0, int(value) / 1_000_000)
        except ValueError:  # "N/A" before the first frame
            return None
    return None


class Estimator:
    """Turns "this fraction is done" into a percentage and the seconds left."""

    def __init__(self, now=time.monotonic):
        self.now = now
        self.started = now()

    def update(self, fraction):
        fraction = min(1.0, max(0.0, fraction))
        elapsed = self.now() - self.started
        remaining = None
        if fraction >= MIN_FRACTION_FOR_ESTIMATE and elapsed > 0:
            remaining = elapsed * (1 - fraction) / fraction
        return round(fraction * 100), remaining


def clock(seconds):
    seconds = max(0, round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f'{hours}:{minutes:02d}:{secs:02d}' if hours else f'{minutes}:{secs:02d}'


def text(percent, remaining):
    """Status line: "Dışa aktarılıyor… %42 · yaklaşık 1:10 kaldı"."""
    line = f'Dışa aktarılıyor… %{percent}'
    if remaining is None:
        return line
    if remaining < 5:
        return f'{line} · bitmek üzere'
    return f'{line} · yaklaşık {clock(remaining)} kaldı'


def estimated_bytes(size, fps, seconds):
    """A deliberately high guess of the export's file size."""
    width, height = size
    return int((width * height * fps * BITS_PER_PIXEL + AUDIO_BITS_PER_SECOND) * max(0.0, seconds) / 8)


def space_problem(target, needed, usage=None):
    """A Turkish warning when the target's drive probably cannot hold the export, else ''.

    The export is first written next to its target, so that drive is the one that matters.
    A drive that cannot be measured is not treated as a problem.
    """
    folder = Path(target).resolve().parent
    try:
        free = (usage or shutil.disk_usage)(folder).free
    except OSError:
        return ''
    if free >= max(MIN_FREE_BYTES, needed * SPACE_MARGIN):
        return ''
    megabytes = lambda value: f'{value / 1024 / 1024:,.0f} MB'.replace(',', '.')
    return (f'Hedef sürücüde yaklaşık {megabytes(free)} boş yer var; bu video en çok {megabytes(needed)} '
            'yer tutabilir. Yer biterse dışa aktarma yarıda kesilir.')
