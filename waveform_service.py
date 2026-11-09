"""Small, bounded waveform thumbnails decoded in a background worker."""
import array
import os
import subprocess
import sys
from PySide6.QtCore import QThread, Signal

SAMPLE_RATE = 1000
WINDOW = 50
MAX_SECONDS = 3600

def peaks_from_pcm(data):
    samples = array.array('h')
    samples.frombytes(data[:len(data) - len(data) % 2])
    if sys.byteorder != 'little': samples.byteswap()
    return [max(abs(n) for n in samples[i:i+WINDOW]) / 32768 for i in range(0, len(samples), WINDOW)]

class WaveformWorker(QThread):
    ready = Signal(str, object)
    def __init__(self, executable, source):
        super().__init__()
        self.executable, self.source = executable, source
    def run(self):
        try:
            result = subprocess.run([self.executable, '-v', 'error', '-i', self.source, '-t', str(MAX_SECONDS), '-vn', '-ac', '1', '-ar', str(SAMPLE_RATE), '-f', 's16le', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, timeout=180)
            self.ready.emit(self.source, peaks_from_pcm(result.stdout) if result.returncode == 0 else [])
        except (OSError, subprocess.TimeoutExpired):
            self.ready.emit(self.source, [])
