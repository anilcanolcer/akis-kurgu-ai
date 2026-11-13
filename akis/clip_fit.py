"""How a video clip sits on the canvas: fitted inside it (bars where the shapes differ), filling it (cropped),
or fitted over a blurred, enlarged copy of itself (no bars and nothing cut off: the usual Shorts look).

The choice lives in the clip's style: {'fit': 'fill', 'focus': 0.0..1.0}. `focus` says which part survives
the crop along the axis that overflows: 0 keeps the left/top edge, 0.5 the middle, 1 the right/bottom edge.
A clip without these keys is fitted, exactly as every clip was before this option existed.
"""
FIT, FILL, BLUR = 'fit', 'fill', 'blur'
# (label shown to the user, fit, focus)
CHOICES = (('Sığdır (boşluk kalabilir)', FIT, 0.5),
           ('Doldur · ortayı tut', FILL, 0.5),
           ('Doldur · solu / üstü tut', FILL, 0.0),
           ('Doldur · sağı / altı tut', FILL, 1.0),
           ('Bulanık arka plan (kırpmadan doldur)', BLUR, 0.5))


def focus_of(style):
    try:
        return min(1.0, max(0.0, float(style.get('focus', 0.5))))
    except (TypeError, ValueError):
        return 0.5


def is_fill(style):
    return style.get('fit') == FILL


def is_blur(style):
    return style.get('fit') == BLUR


def filters(style, width, height, tag='c'):
    """(scale filter, placement filter) for a clip on a width x height canvas.

    `tag` makes the labels of the blurred-background branch unique within one filter graph."""
    if is_blur(style):
        # The background is made small, blurred and enlarged again: as soft as a large blur, far cheaper.
        small_w, small_h = max(32, width // 8 // 2 * 2), max(32, height // 8 // 2 * 2)
        # boxblur refuses a radius over half a plane's size, and the colour planes are half the picture.
        radius = max(1, min(6, min(small_w, small_h) // 4 - 1))
        scale = (f'split=2[{tag}b][{tag}f];'
                 f'[{tag}b]scale={small_w}:{small_h}:force_original_aspect_ratio=increase,crop={small_w}:{small_h},'
                 f'boxblur={radius}:2,scale={width}:{height},eq=brightness=-0.06[{tag}bb];'
                 f'[{tag}f]scale={width}:{height}:force_original_aspect_ratio=decrease[{tag}ff];'
                 f'[{tag}bb][{tag}ff]overlay=(W-w)/2:(H-h)/2')
        return scale, 'null'
    if not is_fill(style):
        return (f'scale={width}:{height}:force_original_aspect_ratio=decrease',
                f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black')
    focus = focus_of(style)
    return (f'scale={width}:{height}:force_original_aspect_ratio=increase',
            f'crop={width}:{height}:(iw-{width})*{focus:.4f}:(ih-{height})*{focus:.4f}')


def choice_index(style):
    """Which of CHOICES describes the clip now (the nearest focus when it was set by hand)."""
    if is_blur(style):
        return next(i for i, choice in enumerate(CHOICES) if choice[1] == BLUR)
    if not is_fill(style):
        return 0
    focus = focus_of(style)
    return min((i for i in range(1, len(CHOICES)) if CHOICES[i][1] == FILL), key=lambda i: abs(CHOICES[i][2] - focus))


def apply(clip, fit, focus=0.5):
    """Set the clip's framing; a fitted clip carries no framing keys at all."""
    if fit not in (FIT, FILL, BLUR):
        raise ValueError('Geçersiz kadraj seçimi.')
    style = {key: value for key, value in clip.style.items() if key not in ('fit', 'focus')}
    if fit == FILL:
        style.update(fit=FILL, focus=min(1.0, max(0.0, float(focus))))
    elif fit == BLUR:
        style['fit'] = BLUR
    clip.style = style
