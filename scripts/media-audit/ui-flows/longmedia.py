"""Long test media for the real-UI flows: like uitest_media, but up to 136 s, with speech-like pauses.

make(path, seconds)   a 30 fps 640x360 MP4: every frame shows its own number (four grey blocks, base 8),
                      every second has its own pitch (150 + 10 * second Hz). Each 4 s cycle is 3 s of
                      sound and 1 s of silence (a pause); LOUD seconds are much louder (for highlights).
frames(path)          the source frame number in each output frame (None where it cannot be read)
seconds(path)         per half second of output sound: the source second heard, or None for silence
silent(frame)         whether the source is silent at that frame
"""
import shutil
import subprocess
from pathlib import Path

import numpy as np

FFMPEG = shutil.which('ffmpeg')
W, H, FPS, RATE, DIGITS = 80, 36, 30, 48000, 4
CYCLE, PAUSE = 4.0, 1.0
LOUD = [(20, 27), (44, 50)]


def ff(args):
    done = subprocess.run([FFMPEG, '-v', 'error', *args], capture_output=True, timeout=600)
    if done.returncode:
        raise RuntimeError(done.stderr.decode('utf-8', 'replace'))
    return done.stdout


def pitch(second):
    # Below 1 kHz throughout: the silence cut listens to speech frequencies only (akis.silence_cut reads the
    # sound at 2 kHz), so a higher tone would rightly count as "not speech" and be cut.
    return 150 + 10 * second


def silent_at(t):
    return (t % CYCLE) >= CYCLE - PAUSE


def silent(frame):
    return silent_at(frame / FPS)


def make(path, seconds=70):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = bytearray()
    for i in range(FPS * seconds):
        frame = np.zeros((H, W), dtype=np.uint8)
        for k in range(DIGITS):
            digit = (i // 8 ** (DIGITS - 1 - k)) % 8
            frame[:, k * 16:(k + 1) * 16] = 20 + digit * 30
        frame[:, DIGITS * 16:] = 235
        raw += frame.tobytes()
    t = np.arange(seconds * RATE) / RATE
    level = np.where([any(a <= s < b for a, b in LOUD) for s in np.floor(t)], 0.6, 0.12)
    level = np.where(silent_at(t), 0.0, level)
    tone = (level * np.sin(2 * np.pi * np.cumsum(pitch(np.floor(t))) / RATE)).astype(np.float32)
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
    if frame[4:-4, DIGITS * 16 + 4:W - 4].mean() < 120:
        return None
    value = 0
    for k in range(DIGITS):
        value = value * 8 + int(round((frame[4:-4, k * 16 + 4:k * 16 + 12].mean() - 20) / 30))
    return value


def size(path):
    import re
    text = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path)], capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stderr
    found = re.search(r'Video: .*?(\d{2,5})x(\d{2,5})', text)
    duration = re.search(r'Duration: (\d+):(\d+):([\d.]+)', text)
    return (int(found[1]), int(found[2])) if found else (0, 0), \
        (int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])) if duration else None


def frames(path):
    (width, height), _ = size(path)
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
    part_size = int(step * RATE)
    heard = []
    for start in range(0, len(sound) - part_size + 1, part_size):
        part = sound[start + part_size // 8:start + part_size - part_size // 8]
        if np.sqrt(np.mean(part ** 2)) < 0.01:
            heard.append(None)
            continue
        spectrum = np.abs(np.fft.rfft(part * np.hanning(len(part))))
        freq = np.argmax(spectrum) * RATE / len(part)
        second = int(round((freq - 150) / 10))
        heard.append(second if second >= 0 and abs(freq - pitch(second)) < 4 else f'?{freq:.0f}Hz')
    return heard


def runs(numbers):
    """[(first, last)] of consecutive ascending numbers (None breaks a run and is reported as (None, count))."""
    out = []
    for value in numbers:
        if out and value is not None and out[-1][0] is not None and value == out[-1][1] + 1:
            out[-1][1] = value
        elif out and value is None and out[-1][0] is None:
            out[-1][1] += 1
        else:
            out.append([value, value] if value is not None else [None, 1])
    return [tuple(r) for r in out]


if __name__ == '__main__':
    import json
    import sys
    target = make(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 70)
    shown = frames(target)
    print(json.dumps({'made': str(target), 'size': size(target), 'runs': runs(shown)[:5], 'heard': seconds(target)[:12]}))
