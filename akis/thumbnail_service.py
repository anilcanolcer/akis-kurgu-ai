"""Small frames along a video, drawn inside its clips on the timeline (a film strip).

One ffmpeg call per file makes one strip image: a frame every `step` seconds, scaled to the clip height
and laid side by side. The timeline cuts the tile it needs out of it. Made in the background, once per
file; a file that cannot be read simply has no strip.
"""
import math
import os
import subprocess

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from akis.media_service import MediaService

HEIGHT = 32         # pixels: the clip box is 34 high
MAX_TILES = 120     # one long video still makes one reasonably small image
MIN_STEP = 1.0      # seconds between frames for short videos


def layout(duration):
    """(number of tiles, seconds between them) for a video of `duration` seconds; (0, 0) for none."""
    if not duration or duration <= 0 or not math.isfinite(duration):
        return 0, 0.0
    step = max(MIN_STEP, duration / MAX_TILES)
    return max(1, min(MAX_TILES, math.ceil(duration / step))), step


class Strip:
    """A strip image with what is needed to find the frame for a moment in the video."""

    def __init__(self, image, count, step):
        self.image, self.count, self.step = image, count, step
        self.tile_width = image.width() // count if count else 0

    def tile_for(self, seconds):
        """Index of the tile that shows the video at `seconds`."""
        if not self.count or self.step <= 0:
            return None
        return max(0, min(self.count - 1, int(seconds / self.step)))


def make_strip(executable, source, duration, runner=subprocess.run):
    """The Strip for a video file, or None when it cannot be made."""
    count, step = layout(duration)
    if not count:
        return None
    command = [executable, '-v', 'error', '-i', str(source), '-an',
               '-vf', f'fps=1/{step:.6f},scale=-2:{HEIGHT},tile={count}x1',
               '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1']
    try:
        result = runner(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode or not result.stdout:
        return None
    image = QImage.fromData(result.stdout, 'PNG')
    if image.isNull() or image.width() < count:
        return None
    return Strip(image, count, step)


class ThumbnailWorker(QThread):
    ready = Signal(str, object)     # source, Strip or None

    def __init__(self, executable, source):
        super().__init__()
        self.executable, self.source = executable, source

    def run(self):
        try:
            duration = MediaService(self.executable).duration(self.source)
        except Exception:
            duration = 0
        self.ready.emit(self.source, make_strip(self.executable, self.source, duration))
