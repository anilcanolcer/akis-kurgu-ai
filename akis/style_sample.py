"""Take a look from a sample video: "make mine like this one".

From a finished video the user likes (their own earlier Short, say) this reads what can be measured
without AI and turned into editor settings:
  - the canvas shape (9:16, 16:9, 1:1, 4:5),
  - how the picture sits in it: filled, fitted with black bars, or on a blurred copy of itself,
  - how loud it is (near -14 LUFS means it was evened out: the "ses eşitleme" switch),
  - its colour compared with the user's own video (so the colour sliders move it toward the sample),
  - how often it cuts (shown as advice: the pace is the edit, not a setting).
The result is a saved template of the user's own (akis.user_templates) plus a few lines that say what was
found. Everything runs locally with ffmpeg.
"""
from __future__ import annotations

import re
import subprocess

from akis import clip_fit

RATIOS = {'9:16': 9 / 16, '16:9': 16 / 9, '1:1': 1.0, '4:5': 4 / 5}
SAMPLES = 6            # frames looked at
TARGET_LUFS = -14.0
LEVELLED = 2.5         # within this many LU of the target: the sample was evened out
SCENE = 0.35           # ffmpeg scene score that counts as a cut


def nearest_ratio(width, height):
    """The editor's aspect closest to width:height, or '' when none is close (the source's own then)."""
    if width <= 0 or height <= 0:
        return ''
    value = width / height
    key = min(RATIOS, key=lambda name: abs(RATIOS[name] - value))
    return key if abs(RATIOS[key] - value) / RATIOS[key] < 0.04 else ''


def _frames(media, path, seconds, width=180):
    """[(width, height, rgb bytes)] for SAMPLES moments spread over the video (10 % … 90 %)."""
    from PIL import Image
    import io
    frames = []
    for index in range(SAMPLES):
        at = seconds * (0.1 + 0.8 * index / max(1, SAMPLES - 1))
        result = media.run(['-v', 'error', '-ss', f'{at:.3f}', '-i', str(path), '-frames:v', '1',
                            '-vf', f'scale={width}:-2', '-f', 'image2pipe', '-c:v', 'png', '-'], text=False)
        if result.returncode or not result.stdout:
            continue
        image = Image.open(io.BytesIO(result.stdout)).convert('RGB')
        frames.append(image)
    return frames


def framing_of(images):
    """'blur', 'fit' or 'fill': how the picture sits on the canvas, from its top and bottom bands."""
    from PIL import ImageFilter, ImageStat
    votes = {clip_fit.FIT: 0, clip_fit.BLUR: 0, clip_fit.FILL: 0}
    for image in images:
        width, height = image.size
        band = max(4, height // 10)
        gray = image.convert('L')
        edges = gray.filter(ImageFilter.FIND_EDGES)
        # Below where a title card sits (the top ~15 %) and above the bottom edge: where bars or the
        # blurred copy show when the picture is a band in the middle.
        top = (0, round(height * 0.2), width, round(height * 0.2) + band)
        bottom = (0, round(height * 0.82), width, round(height * 0.82) + band)
        middle = (0, height // 2 - band // 2, width, height // 2 + band // 2)
        dark = all(ImageStat.Stat(gray.crop(box)).mean[0] < 18 and ImageStat.Stat(gray.crop(box)).stddev[0] < 8
                   for box in (top, bottom))
        sharp_middle = ImageStat.Stat(edges.crop(middle)).mean[0]
        sharp_edges = max(ImageStat.Stat(edges.crop(box)).mean[0] for box in (top, bottom))
        if dark:
            votes[clip_fit.FIT] += 1
        elif sharp_middle > 4 and sharp_edges < sharp_middle * 0.3:
            votes[clip_fit.BLUR] += 1
        else:
            votes[clip_fit.FILL] += 1
    return max(votes, key=votes.get) if images else clip_fit.FILL


def colour_of(images):
    """(brightness 0..1, contrast 0..1, saturation 0..1) averaged over the frames."""
    from PIL import ImageStat
    if not images:
        return None
    values = []
    for image in images:
        hsv = image.convert('HSV')
        v = ImageStat.Stat(hsv.getchannel('V'))
        s = ImageStat.Stat(hsv.getchannel('S'))
        values.append((v.mean[0] / 255, v.stddev[0] / 255, s.mean[0] / 255))
    return tuple(sum(item[i] for item in values) / len(values) for i in range(3))


def colour_shift(sample, own):
    """Slider values (-50..50, steps of 5) that move `own` toward `sample`; (0, 0, 0) without both."""
    if not sample or not own:
        return (0, 0, 0)
    step = lambda value, limit: int(max(-limit, min(limit, round(value / 5) * 5)))
    return (step((sample[0] - own[0]) * 100, 20), step((sample[1] - own[1]) * 150, 20), step((sample[2] - own[2]) * 120, 25))


def loudness(media, path):
    """Integrated loudness in LUFS, or None when it has no sound."""
    result = media.run(['-hide_banner', '-nostats', '-i', str(path), '-map', '0:a:0', '-af', 'ebur128', '-f', 'null', '-'],
                       text=True)
    found = re.findall(r'I:\s+(-?\d+(?:\.\d+)?) LUFS', result.stderr or '')
    return float(found[-1]) if found and not result.returncode else None


def cuts_per_minute(media, path, seconds):
    result = media.run(['-hide_banner', '-nostats', '-i', str(path), '-map', '0:v:0', '-vf',
                        f"scale=160:-2,select='gt(scene,{SCENE})',metadata=print", '-f', 'null', '-'], text=True)
    cuts = len(re.findall(r'lavfi\.scene_score=', result.stderr or ''))
    return cuts * 60 / seconds if seconds > 0 else 0.0


def measure(media, sample, own=None):
    """Everything read from `sample` (and the colour of `own`, the user's video, when given)."""
    seconds = media.duration(sample)
    width, height = media.dimensions(sample)
    images = _frames(media, sample, seconds)
    own_colour = None
    if own:
        try:
            own_colour = colour_of(_frames(media, own, media.duration(own)))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            own_colour = None
    level = loudness(media, sample) if media.has_audio(sample) else None
    return {'name': str(sample), 'size': (int(width), int(height)), 'seconds': seconds,
            'aspect': nearest_ratio(int(width), int(height)), 'framing': framing_of(images),
            'colour': colour_of(images), 'own_colour': own_colour, 'lufs': level,
            'pace': cuts_per_minute(media, sample, seconds)}


def to_template(found, name):
    """A template of the user's own (akis.user_templates) from what was measured."""
    levelled = found['lufs'] is not None and abs(found['lufs'] - TARGET_LUFS) <= LEVELLED
    return {'name': name, 'aspect': found['aspect'], 'tracks': [['video', 'Video'], ['text', 'Altyazı / Captions']],
            'title': '', 'color': list(colour_shift(found['colour'], found['own_colour'])), 'speed': 1.0,
            'audio': ['level'] if levelled else [], 'framing': found['framing']}


FRAMING_NAMES = {clip_fit.FIT: 'sığdırılmış (boşluklu)', clip_fit.FILL: 'kadrajı dolduruyor',
                 clip_fit.BLUR: 'bulanık arka plan üstünde'}


def describe(found, item, say=str):
    """Lines that say what was found and what the template will set."""
    width, height = found['size']
    lines = [say('Oran: {ratio} ({width}×{height})').format(ratio=found['aspect'] or say('kendine özgü'), width=width, height=height),
             say('Görüntü: {framing}').format(framing=say(FRAMING_NAMES[found['framing']]))]
    if found['lufs'] is None:
        lines.append(say('Ses: yok'))
    else:
        lines.append(say('Ses düzeyi: {lufs} LUFS{levelled}').format(
            lufs=f"{found['lufs']:.1f}".replace('.', ','),
            levelled=say(' (eşitlenmiş: ses eşitleme açılacak)') if 'level' in item['audio'] else ''))
    if any(item['color']):
        b, c, s = item['color']
        lines.append(say('Renk: parlaklık {b:+d}, kontrast {c:+d}, doygunluk {s:+d} (sizin videonuza göre)').format(b=b, c=c, s=s))
    elif found['own_colour'] is None:
        lines.append(say('Renk: karşılaştırmak için önce kendi videonuzu ekleyin'))
    else:
        lines.append(say('Renk: sizin videonuza yakın, değişmeyecek'))
    pace = found['pace']
    if pace > 0:
        shot = 60 / pace
        lines.append(say('Tempo: dakikada {cuts} kesim (ortalama çekim {shot} sn)').format(
            cuts=round(pace), shot=f'{shot:.1f}'.replace('.', ',')))
        if shot < 4:
            lines.append(say('Hızlı bir kurgu: “Sessizlikleri çıkar” ve “Dolgu sözcüklerini kes” temposuna yaklaştırır.'))
    else:
        lines.append(say('Tempo: kesim yok, tek çekim'))
    return lines
