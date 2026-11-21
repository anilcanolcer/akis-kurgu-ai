"""Record a screen with the bundled ffmpeg (Windows' gdigrab), with a microphone through DirectShow.

Qt's own screen capture is not available in this build ("CapturingNotSupported" on both media backends),
so the screen is recorded by ffmpeg in a background process: start() launches it, stop() asks it to finish
(the 'q' key on its input, so the MP4 is closed properly) and waits. Nothing is sent anywhere.
"""
from __future__ import annotations

import os
import re
import subprocess


def even(value):
    return max(2, int(value) // 2 * 2)


def screen_area(screen):
    """(x, y, width, height) of a QScreen in the physical pixels gdigrab uses (scaled displays included)."""
    geometry, ratio = screen.geometry(), screen.devicePixelRatio()
    return (round(geometry.x() * ratio), round(geometry.y() * ratio),
            even(geometry.width() * ratio), even(geometry.height() * ratio))


def audio_devices(executable, run=subprocess.run):
    """Names of the DirectShow microphones ffmpeg sees, in its own order."""
    try:
        result = run([executable, '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
                     capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r'"([^"]+)"\s*\(audio\)', result.stderr or '')


def command(executable, area, output, microphone=None, fps=30):
    x, y, width, height = area
    args = [executable, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'gdigrab', '-framerate', str(fps), '-draw_mouse', '1',
            '-offset_x', str(x), '-offset_y', str(y), '-video_size', f'{width}x{height}', '-i', 'desktop']
    if microphone:
        args += ['-f', 'dshow', '-i', f'audio={microphone}']
    args += ['-map', '0:v'] + (['-map', '1:a', '-c:a', 'aac', '-b:a', '160k'] if microphone else [])
    args += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
             '-movflags', '+faststart', str(output)]
    return args


class ScreenRecorder:
    def __init__(self, executable, popen=subprocess.Popen):
        self.executable = executable
        self.popen = popen
        self.process = None
        self.output = None

    @property
    def recording(self):
        return self.process is not None and self.process.poll() is None

    def start(self, area, output, microphone=None):
        if self.recording:
            raise RuntimeError('Kayıt zaten sürüyor.')
        self.output = str(output)
        self.process = self.popen(command(self.executable, area, output, microphone), stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def stop(self, timeout=20):
        """Finish the file; returns its path, or raises RuntimeError with ffmpeg's last words."""
        process, self.process = self.process, None
        if process is None:
            raise RuntimeError('Kayıt başlamadı.')
        timed_out = False
        try:
            _, message = process.communicate(input=b'q', timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            _, message = process.communicate()
        if timed_out or process.returncode != 0 or not self.output or not os.path.isfile(self.output) or os.path.getsize(self.output) == 0:
            message = message or b''
            raise RuntimeError(message.decode('utf-8', 'replace').strip()[-400:] or 'Kayıt dosyası oluşmadı.')
        return self.output

    def failed(self):
        """Why ffmpeg stopped by itself (a busy device, say): its error text, or its exit code when it said
        nothing; '' while it is still recording or when nothing was started. An ffmpeg that ended without a
        word used to give '' here too, so the dialog kept counting a recording that no longer ran."""
        if self.process is None or self.process.poll() is None:
            return ''
        process, self.process = self.process, None
        try:
            text = (process.stderr.read() or b'').decode('utf-8', 'replace').strip()[-400:]
        except (OSError, ValueError, AttributeError):
            text = ''
        return text or f'FFmpeg kaydı beklenmedik şekilde durdurdu (çıkış kodu {process.returncode}).'

    def discard(self):
        """Stop recording and delete whatever was written (the user chose not to keep it)."""
        if self.recording:
            try:
                self.stop()
            except RuntimeError:
                pass
        self.process = None
        if self.output:
            try:
                os.remove(self.output)
            except OSError:
                pass


def exclude_from_capture(widget):
    """Keep a window out of screen recordings and screenshots (Windows 10 2004 and later): the recording
    bar stays on screen for the person recording but never appears in the video. False where unsupported."""
    if os.name != 'nt':
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), 0x11))  # WDA_EXCLUDEFROMCAPTURE
    except (AttributeError, OSError, ValueError):
        return False
