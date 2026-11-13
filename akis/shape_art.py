"""Hand-drawn style annotation marks (circle, arrow) rendered as transparent canvas images.

Coordinates in a style dict are fractions of the canvas: x/y is the circle centre or
the arrow tip, x2/y2 the arrow tail, size the circle diameter relative to canvas width.
"""
from __future__ import annotations

import math
import random

COLORS = {'red': (255, 45, 45), 'yellow': (255, 221, 0), 'white': (255, 255, 255),
          'green': (57, 255, 90), 'blue': (60, 160, 255), 'pink': (255, 80, 200)}
SHAPES = ('circle', 'arrow', 'card')
SCALE = 2  # supersampling for smooth strokes


def _stroke(draw, points, width, colour):
    draw.line(points, fill=colour, width=width, joint='curve')
    radius = width / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)


def _circle_points(cx, cy, radius, rng):
    """A slightly squashed loop that overshoots its start, like a quick marker circle."""
    start = rng.uniform(-2.4, -1.9)
    squash = rng.uniform(0.82, 0.92)
    phase = rng.uniform(0, math.tau)
    points = []
    steps = 90
    for i in range(steps + 1):
        progress = i / steps
        angle = start + progress * math.tau * 1.1
        wobble = 1 + 0.035 * math.sin(3 * angle + phase) + 0.05 * (progress - 0.5)
        points.append((cx + radius * wobble * math.cos(angle), cy + radius * squash * wobble * math.sin(angle)))
    return points


def _arrow_strokes(tail, tip, rng):
    (x0, y0), (x1, y1) = tail, tip
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    bend = rng.choice((-1, 1)) * rng.uniform(0.12, 0.2) * length
    mx, my = (x0 + x1) / 2 - (y1 - y0) / length * bend, (y0 + y1) / 2 + (x1 - x0) / length * bend
    shaft = [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t * t * x1,
              (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t * t * y1) for t in (i / 40 for i in range(41))]
    heading = math.atan2(y1 - my, x1 - mx)
    head = min(0.34 * length, 220 * SCALE)
    wings = [[(x1 + head * math.cos(heading + math.pi - spread), y1 + head * math.sin(heading + math.pi - spread)), (x1, y1)]
             for spread in (rng.uniform(0.42, 0.55), -rng.uniform(0.42, 0.55))]
    return [shaft, *wings]


def default_tail(x, y):
    """Start the arrow from the roomier side of the frame."""
    return (min(0.92, x + 0.26) if x < 0.5 else max(0.08, x - 0.26),
            max(0.06, y - 0.16) if y > 0.3 else min(0.94, y + 0.16))


def _font(bold, px):
    from pathlib import Path
    import os
    from PIL import ImageFont
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    for name in (('segoeuib.ttf', 'arialbd.ttf') if bold else ('segoeui.ttf', 'arial.ttf')):
        try:
            return ImageFont.truetype(str(folder / name), px)
        except OSError:
            continue
    return ImageFont.load_default(px)


def _wrap(draw, text, font, width, lines=2):
    words, out, line = str(text).split(), [], ''
    for word in words:
        candidate = f'{line} {word}' if line else word
        if draw.textlength(candidate, font=font) <= width or not line:
            line = candidate
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    if len(out) > lines:
        out = out[:lines]
        while out[-1] and draw.textlength(out[-1] + '…', font=font) > width:
            out[-1] = out[-1][:-1]
        out[-1] = out[-1].rstrip() + '…'
    return out


def draw_card(style, size):
    """A rounded, see-through dark card near the top: a small counter ("4 / 7") over a title."""
    from PIL import Image, ImageDraw
    width, height = size
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box_w = round(width * 0.74)
    pad = round(width * 0.03)
    title_font = _font(True, max(14, round(width * 0.042)))
    counter_font = _font(False, max(10, round(width * 0.026)))
    counter, title = str(style.get('counter', '')).strip(), str(style.get('title', '')).strip()
    lines = _wrap(draw, title, title_font, box_w - 2 * pad) if title else []
    title_h = title_font.getbbox('Ğg')[3]
    counter_h = counter_font.getbbox('0')[3] if counter else 0
    gap = round(pad * 0.4) if counter and lines else 0
    box_h = 2 * pad + counter_h + gap + len(lines) * round(title_h * 1.15)
    left, top = (width - box_w) // 2, round(height * float(style.get('y', 0.05)))
    draw.rounded_rectangle((left, top, left + box_w, top + box_h), radius=round(width * 0.025), fill=(28, 26, 24, 190))
    y = top + pad
    if counter:
        draw.text((width / 2, y), counter, font=counter_font, fill=(225, 212, 190, 255), anchor='mt')
        y += counter_h + gap
    for line in lines:
        draw.text((width / 2, y), line, font=title_font, fill=(245, 242, 236, 255), anchor='mt')
        y += round(title_h * 1.15)
    return image


def draw_shape(style, size, seed=0):
    """Return an RGBA PIL image of the whole canvas containing one mark."""
    from PIL import Image, ImageDraw
    width, height = size
    shape = style.get('shape')
    if shape not in SHAPES:
        raise ValueError('Unknown shape')
    if shape == 'card':
        return draw_card(style, size)
    rng = random.Random(seed)
    colour = COLORS.get(style.get('color'), COLORS['red']) + (255,)
    big = (width * SCALE, height * SCALE)
    image = Image.new('RGBA', big, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x, y = float(style.get('x', 0.5)) * big[0], float(style.get('y', 0.5)) * big[1]
    thickness = max(4, round(big[0] * 0.011))
    if shape == 'circle':
        radius = max(0.04, float(style.get('size', 0.3))) * big[0] / 2
        strokes = [_circle_points(x, y, radius, rng)]
    else:
        tail = default_tail(float(style.get('x', 0.5)), float(style.get('y', 0.5)))
        x2 = float(style.get('x2', tail[0])) * big[0]
        y2 = float(style.get('y2', tail[1])) * big[1]
        strokes = _arrow_strokes((x2, y2), (x, y), rng)
    for stroke in strokes:  # dark edge keeps the mark readable on any footage
        _stroke(draw, stroke, thickness + round(thickness * 0.7), (0, 0, 0, 200))
    for stroke in strokes:
        _stroke(draw, stroke, thickness, colour)
    return image.resize(size, Image.LANCZOS)
