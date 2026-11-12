"""How a video clip sits on the canvas: fitted inside it (bars where the shapes differ) or filling it (cropped).

The choice lives in the clip's style: {'fit': 'fill', 'focus': 0.0..1.0}. `focus` says which part survives
the crop along the axis that overflows: 0 keeps the left/top edge, 0.5 the middle, 1 the right/bottom edge.
A clip without these keys is fitted, exactly as every clip was before this option existed.
"""
FIT, FILL = 'fit', 'fill'
# (label shown to the user, fit, focus)
CHOICES = (('Sığdır (boşluk kalabilir)', FIT, 0.5),
           ('Doldur · ortayı tut', FILL, 0.5),
           ('Doldur · solu / üstü tut', FILL, 0.0),
           ('Doldur · sağı / altı tut', FILL, 1.0))


def focus_of(style):
    try:
        return min(1.0, max(0.0, float(style.get('focus', 0.5))))
    except (TypeError, ValueError):
        return 0.5


def is_fill(style):
    return style.get('fit') == FILL


def filters(style, width, height):
    """(scale filter, placement filter) for a clip on a width x height canvas."""
    if not is_fill(style):
        return (f'scale={width}:{height}:force_original_aspect_ratio=decrease',
                f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black')
    focus = focus_of(style)
    return (f'scale={width}:{height}:force_original_aspect_ratio=increase',
            f'crop={width}:{height}:(iw-{width})*{focus:.4f}:(ih-{height})*{focus:.4f}')


def choice_index(style):
    """Which of CHOICES describes the clip now (the nearest focus when it was set by hand)."""
    if not is_fill(style):
        return 0
    focus = focus_of(style)
    return min(range(1, len(CHOICES)), key=lambda i: abs(CHOICES[i][2] - focus))


def apply(clip, fit, focus=0.5):
    """Set the clip's framing; a fitted clip carries no framing keys at all."""
    if fit not in (FIT, FILL):
        raise ValueError('Geçersiz kadraj seçimi.')
    style = {key: value for key, value in clip.style.items() if key not in ('fit', 'focus')}
    if fit == FILL:
        style.update(fit=FILL, focus=min(1.0, max(0.0, float(focus))))
    clip.style = style
