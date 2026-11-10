"""Hand-drawn style annotation marks (circle, arrow) rendered as transparent canvas images.

Coordinates in a style dict are fractions of the canvas: x/y is the circle centre or
the arrow tip, x2/y2 the arrow tail, size the circle diameter relative to canvas width.
"""
from __future__ import annotations

import math
import random

COLORS = {'red': (255, 45, 45), 'yellow': (255, 221, 0), 'white': (255, 255, 255),
          'green': (57, 255, 90), 'blue': (60, 160, 255), 'pink': (255, 80, 200)}
SHAPES = ('circle', 'arrow')
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


def draw_shape(style, size, seed=0):
    """Return an RGBA PIL image of the whole canvas containing one mark."""
    from PIL import Image, ImageDraw
    width, height = size
    shape = style.get('shape')
    if shape not in SHAPES:
        raise ValueError('Unknown shape')
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
