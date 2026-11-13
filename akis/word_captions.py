"""Word-by-word captions: short chunks of two or three words, the word being spoken highlighted.

A caption clip of this kind is an ordinary text clip whose style carries its words,
    style['words'] = [[start, end, text], ...]   frames from the clip's start
    style['look']  = one of LOOKS
and whose text is the words joined (so the timeline, plans and exports read it like any caption).

Drawing: every moment of a chunk (no word yet, word 1 lit, word 2 lit, ...) is one transparent canvas-sized
picture. The renderer feeds all of a track's pictures to ffmpeg as ONE input (a concat list with each
picture's duration), so a ten-minute video with a thousand words still costs one input and one overlay.
"""
from __future__ import annotations

from pathlib import Path

LOOKS = ('vurgu', 'kutu', 'karaoke')
LOOK_NAMES = {'vurgu': 'Kelime kelime: sarı vurgu', 'kutu': 'Kelime kelime: renkli kutu',
              'karaoke': 'Kelime kelime: karaoke'}
CLASSIC = 'klasik'
CHOICES = (CLASSIC,) + LOOKS
CHOICE_NAMES = dict(LOOK_NAMES, **{CLASSIC: 'Klasik altyazı (cümle cümle)'})

MAX_WORDS = 3          # a chunk: at most this many words...
MAX_CHARS = 18         # ...and about this many letters, so it stays one or two lines on a phone
GAP = 0.6              # a pause this long (seconds) starts a new chunk
SENTENCE_END = '.?!…'

HIGHLIGHT = (255, 221, 0)
BOX = (115, 87, 245)
UPCOMING = (170, 170, 170)
WHITE = (255, 255, 255)


def chunks(words, *, max_words=MAX_WORDS, max_chars=MAX_CHARS, gap=GAP):
    """[[(start s, end s, text), ...]]: timed words grouped into short chunks, cut at pauses and sentence ends."""
    result, current = [], []
    for word in words or ():
        try:
            text, start = str(word['text']).strip(), float(word['start'])
            end = max(start, float(word.get('end', start)))
        except (KeyError, TypeError, ValueError):
            continue
        if not text:
            continue
        if current:
            letters = sum(len(w[2]) + 1 for w in current) + len(text)
            if (start - current[-1][1] > gap or current[-1][2][-1:] in SENTENCE_END
                    or len(current) >= max_words or letters > max_chars):
                result.append(current)
                current = []
        current.append((start, end, text))
    if current:
        result.append(current)
    return result


def caption_clips(source_clip, words, fps, look):
    """[(timeline start, length, text, style)] for the chunks of `words` (seconds in the source) that the
    video clip `source_clip` shows, placed through its in-point and its own speed."""
    made = []
    for chunk in chunks(words):
        inside = [(a, b, t) for a, b, t in chunk
                  if source_clip.source_in <= round(a * fps) < source_clip.source_end]
        if not inside:
            continue
        at = [source_clip.timeline_frame(round(a * fps)) for a, _, _ in inside]
        until = [source_clip.timeline_frame(min(round(b * fps), source_clip.source_end)) for _, b, _ in inside]
        start = round(at[0])
        end = min(source_clip.end, max(round(until[-1]), start + 1))
        timed = [[max(0, round(a) - start), max(1, round(b) - start), t] for a, b, (_, _, t) in zip(at, until, inside)]
        made.append((start, end - start, ' '.join(t for _, _, t in inside), {'words': timed, 'look': look}))
    return made


def states(clip):
    """[(first frame, end frame, lit word index or None)] covering the clip, frames from its start. A word
    stays lit until the next one starts, so the highlight never flickers off between words."""
    words = clip.style.get('words') or []
    starts = sorted({max(0, min(clip.length - 1, int(w[0]))) for w in words})
    if not words:
        return [(0, clip.length, None)]
    result, cursor = [], 0
    if starts[0] > 0:
        result.append((0, starts[0], None))
        cursor = starts[0]
    for index, word in enumerate(words):
        begin = max(cursor, min(clip.length - 1, int(word[0])))
        stop = clip.length if index == len(words) - 1 else max(begin, min(clip.length, int(words[index + 1][0])))
        if stop > begin:
            result.append((begin, stop, index))
            cursor = stop
    return result


def _font(path, px):
    from PIL import ImageFont
    for candidate in (Path(path).with_name('arialbd.ttf'), Path(path)):
        try:
            return ImageFont.truetype(str(candidate), px)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(words, lit, look, canvas, rect, font_path, px):
    """The canvas-sized transparent picture of one chunk with word `lit` (or none) highlighted."""
    from PIL import Image, ImageDraw
    width, height = canvas
    left, top, across, down = rect
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    if not words:
        return image
    paint = ImageDraw.Draw(image)
    font = _font(font_path, px)
    stroke = max(2, round(px / 9))
    space = paint.textlength(' ', font=font)
    texts = [str(w[2]) for w in words]
    sizes = [paint.textlength(t, font=font) for t in texts]
    # Lines no wider than 90 % of the picture; a word wider than that sits alone on its line.
    lines, line, used = [], [], 0.0
    for index, size in enumerate(sizes):
        extra = size if not line else used + space + size
        if line and extra > across * 0.9:
            lines.append(line)
            line, used = [index], size
        else:
            line.append(index)
            used = extra
    lines.append(line)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + round(px * 0.15)
    block = line_h * len(lines)
    middle = top + down * 0.74
    y = max(stroke + 4, min(height - block - stroke - 4, round(middle - block / 2)))
    pad = round(px * 0.18)
    for row in lines:
        row_w = sum(sizes[i] for i in row) + space * (len(row) - 1)
        x = left + (across - row_w) / 2
        for i in row:
            colour = WHITE
            if look == 'vurgu' and i == lit:
                colour = HIGHLIGHT
            elif look == 'karaoke' and (lit is None or i > lit):
                colour = UPCOMING
            elif look == 'kutu' and i == lit:
                paint.rounded_rectangle((x - pad, y - pad * 0.4, x + sizes[i] + pad, y + ascent + descent + pad * 0.4),
                                        radius=round(px * 0.22), fill=BOX + (255,))
            paint.text((x, y), texts[i], font=font, fill=colour + (255,), stroke_width=stroke,
                       stroke_fill=(0, 0, 0, 255))
            x += sizes[i] + space
        y += line_h
    return image
