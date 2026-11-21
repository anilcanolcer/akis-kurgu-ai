"""Test media for the real-UI flows: every frame shows its own number, every second of sound has its own pitch.

make(path)          an 8 s, 30 fps, 640x360 MP4 with AAC sound
frames(path)        the source frame number shown in each output frame (None for black)
seconds(path)       for each half second of output sound, which source second is heard (None for silence)
info(path)          duration, frame count, size and whether there is sound (ffprobe-free: ffmpeg only)
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

FFMPEG = shutil.which('ffmpeg')
W, H, FPS, SECONDS, RATE = 64, 36, 30, 8, 48000


def ff(args, **kw):
    done = subprocess.run([FFMPEG, '-v', 'error', *args], capture_output=True, timeout=300, **kw)
    if done.returncode:
        raise RuntimeError(done.stderr.decode('utf-8', 'replace'))
    return done.stdout


def pitch(second):
    return 400 + 150 * second


def make(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = bytearray()
    for i in range(FPS * SECONDS):
        frame = np.zeros((H, W), dtype=np.uint8)
        for k, digit in enumerate(((i // 64) % 8, (i // 8) % 8, i % 8)):
            frame[:, k * 16:(k + 1) * 16] = 20 + digit * 30
        frame[:, 48:] = 235
        raw += frame.tobytes()
    t = np.arange(SECONDS * RATE) / RATE
    tone = (0.3 * np.sin(2 * np.pi * np.cumsum(pitch(np.floor(t))) / RATE)).astype(np.float32)
    gray, pcm = path.with_suffix('.gray'), path.with_suffix('.f32')
    gray.write_bytes(bytes(raw))
    pcm.write_bytes(tone.tobytes())
    ff(['-y', '-f', 'rawvideo', '-pixel_format', 'gray', '-video_size', f'{W}x{H}', '-framerate', str(FPS), '-i', str(gray),
        '-f', 'f32le', '-ar', str(RATE), '-ac', '1', '-i', str(pcm),
        '-vf', 'scale=640:360:flags=neighbor', '-c:v', 'libx264', '-crf', '4', '-g', '15', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k', '-shortest', str(path)])
    gray.unlink()
    pcm.unlink()
    return path


def decode(frame):
    if frame[4:-4, 52:60].mean() < 120:
        return None
    digits = [int(round((frame[4:-4, k * 16 + 4:k * 16 + 12].mean() - 20) / 30)) for k in range(3)]
    return digits[0] * 64 + digits[1] * 8 + digits[2]


def frames(path):
    """Source frame numbers, read from the picture's centre (letterboxing around it is cut away first)."""
    probe = info(path)
    width, height = probe['width'], probe['height']
    # the 16:9 picture inside the output frame (the export may pad it into another shape)
    box_w = min(width, height * 16 // 9)
    box_h = box_w * 9 // 16
    x, y = (width - box_w) // 2, (height - box_h) // 2
    raw = ff(['-i', str(path), '-vf', f'crop={box_w}:{box_h}:{x}:{y},scale={W}:{H}:flags=area', '-f', 'rawvideo',
              '-pix_fmt', 'gray', '-'])
    pictures = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W).astype(int)
    return [decode(p) for p in pictures]


def seconds(path, step=0.5):
    raw = ff(['-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-'])
    sound = np.frombuffer(raw, dtype=np.float32)
    size = int(step * RATE)
    heard = []
    for start in range(0, len(sound) - size + 1, size):
        part = sound[start + size // 8:start + size - size // 8]       # away from cut edges
        if np.sqrt(np.mean(part ** 2)) < 0.02:
            heard.append(None)
            continue
        spectrum = np.abs(np.fft.rfft(part * np.hanning(len(part))))
        freq = np.argmax(spectrum) * RATE / len(part)
        second = int(round((freq - 400) / 150))
        heard.append(second if 0 <= second < SECONDS and abs(freq - pitch(second)) < 40 else f'?{freq:.0f}Hz')
    return heard


def info(path):
    text = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path)], capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stderr
    duration = re.search(r'Duration: (\d+):(\d+):([\d.]+)', text)
    size = re.search(r'Video: .*?(\d{2,5})x(\d{2,5})', text)
    count = subprocess.run([FFMPEG, '-v', 'error', '-i', str(path), '-map', '0:v:0', '-f', 'framemd5', '-'],
                           capture_output=True, text=True).stdout
    return {'seconds': (int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])) if duration else None,
            'width': int(size[1]) if size else 0, 'height': int(size[2]) if size else 0,
            'frames': sum(1 for line in count.splitlines() if line and not line.startswith('#')),
            'sound': 'Audio:' in text}


if __name__ == '__main__':
    import sys
    target = make(sys.argv[1])
    print(json.dumps({'made': str(target), **info(target), 'first': frames(target)[:5], 'sound_map': seconds(target)}))
