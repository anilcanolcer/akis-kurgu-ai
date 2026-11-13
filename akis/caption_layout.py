"""Where a caption goes and how long it may be.

A caption belongs to the picture, not to the canvas: a landscape video on a vertical canvas is a band in
the middle with black above and below, and a caption sized and placed by the canvas lands in the black
or hangs over the picture's edge. Everything here works from the rectangle the picture really occupies.
Long recognised sentences are also cut into short captions shown one after another, instead of one block
of many lines covering the picture.
"""
import math

MAX_CHARS = 64          # about two lines on a landscape picture, three on a vertical one
BREAK_AFTER = '.,;:!?…'


def picture_rect(canvas, source_size, fill=False):
    """(x, y, width, height) the picture covers on the canvas: fitted inside it, or all of it when filled."""
    width, height = canvas
    try:
        source_w, source_h = source_size
        if fill or source_w <= 0 or source_h <= 0:
            return 0, 0, width, height
    except (TypeError, ValueError):
        return 0, 0, width, height
    scale = min(width / source_w, height / source_h)
    picture_w, picture_h = min(width, round(source_w * scale)), min(height, round(source_h * scale))
    return (width - picture_w) // 2, (height - picture_h) // 2, picture_w, picture_h


def font_px(rect, canvas):
    """Caption size from the picture it sits on, never so small that it cannot be read on the canvas."""
    _, _, picture_w, picture_h = rect
    readable = min(canvas) / 24
    return max(12, round(max(min(picture_h / 18, picture_w / 15), readable)))


def split_caption(text, start, end, limit=MAX_CHARS):
    """[(start, end, text)]: the text in pieces of about `limit` characters, cut between words (after
    punctuation where one is near), each given a share of the time in proportion to its length."""
    text = ' '.join(str(text).split())
    words = text.split(' ')
    if len(text) <= limit or len(words) < 2 or end <= start:
        return [(start, end, text)]
    count = math.ceil(len(text) / limit)
    target = len(text) / count
    pieces, current = [], []
    for index, word in enumerate(words):
        current.append(word)
        length = len(' '.join(current))
        words_left = len(words) - index - 1
        pieces_left = count - len(pieces) - 1
        natural = length >= target * 0.6 and word[-1] in BREAK_AFTER
        if pieces_left and words_left >= pieces_left and (length >= target or natural):
            pieces.append(' '.join(current))
            current = []
    if current:
        pieces.append(' '.join(current))
    total = sum(len(piece) for piece in pieces)
    result, cursor, used = [], start, 0
    for index, piece in enumerate(pieces):
        used += len(piece)
        stop = end if index == len(pieces) - 1 else start + (end - start) * used / total
        result.append((cursor, stop, piece))
        cursor = stop
    return result
