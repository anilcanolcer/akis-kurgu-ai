"""Every colour the interface uses, in one place, for a dark and a light theme.

Stylesheets name colours as `$role` (see css()); painted widgets ask color('role') while painting, so a
theme switch only has to set the stylesheets again and repaint. Colours that belong to the video itself
(caption and shape colours) are not here: they look the same whatever the window looks like.
"""
from string import Template

from PySide6.QtGui import QColor

DEFAULT = 'dark'
LABELS = {'dark': 'Koyu tema', 'light': 'Açık tema'}

#            role               dark       light
_ROLES = (
    ('bg',                '#0d0e12', '#e4e6ea'),   # the window
    ('surface',           '#111218', '#f7f8fa'),   # sidebar, editor, tab pages, timeline
    ('panel',             '#171921', '#eef0f3'),   # cards inside a surface
    ('field',             '#171920', '#fcfcfd'),   # text boxes, combo boxes, filter buttons
    ('raised',            '#1d1f29', '#eceef2'),   # chips, secondary buttons, timeline track rows
    ('button',            '#20222c', '#fcfcfd'),
    ('button_border',     '#20222c', '#cbcfd7'),   # plain buttons: invisible in dark, a frame in light
    ('button_hover',      '#292c38', '#f1f3f6'),
    ('border',            '#252733', '#dcdfe5'),
    ('border_strong',     '#303340', '#cbcfd7'),
    ('border_hover',      '#3a3e4e', '#a9afbc'),
    ('text',              '#f3f4f8', '#252830'),
    ('text_strong',       '#ffffff', '#111318'),   # selected tab, active nav item
    ('text_soft',         '#b8bbca', '#434856'),
    ('muted',             '#9195a7', '#626875'),
    ('faint',             '#7d8194', '#878c98'),
    ('accent',            '#7357f5', '#6a4ff0'),   # primary buttons: white text in both themes
    ('accent_hover',      '#876eff', '#5a3fe2'),
    ('accent_line',       '#8f78ff', '#6a4ff0'),   # selection borders, slider, progress
    ('accent_text',       '#b4a6ff', '#4e33d0'),   # accent coloured text and focus rings
    ('accent_bg',         '#241f3d', '#e9e5fc'),   # selected list item, checked filter, active nav
    ('disabled',          '#2a2c38', '#eceef1'),
    ('disabled_text',     '#777b8c', '#9da2ad'),
    ('success',           '#74d9ac', '#1d8a5b'),
    ('notice_bg',         '#1f1b12', '#fff6df'),
    ('notice_border',     '#4a3c1c', '#ecd394'),
    ('notice_text',       '#f0cf8e', '#7a5810'),
    ('tooltip',           '#232631', '#fcfcfd'),
    ('video_bg',          '#08090c', '#1f2127'),   # behind the picture: dark in both, as in video editors
    ('video_text',        '#9195a7', '#b5b9c5'),
    ('video_caption',     '#e8e9f0', '#e8e9f0'),
    ('track_video',       '#5a49a8', '#7462cc'),
    ('track_audio',       '#257e77', '#33958c'),
    ('track_text',        '#a55a83', '#b56891'),
    ('track_overlay',     '#9c703c', '#b18143'),
    ('clip_text',         '#ffffff', '#ffffff'),
    ('clip_edge',         '#282a37', '#f7f8fa'),
    ('clip_selected',     '#ffffff', '#1b1d26'),
    ('waveform',          '#a4e3db', '#e6f9f6'),
    ('marker',            '#ffcd5a', '#d99a00'),
    ('playhead',          '#ff4fa3', '#e8247f'),
    ('kept',              '#2f9e6e', '#2f9e6e'),
    ('cut',               '#d6453d', '#d6453d'),
    ('empty',             '#2a2f37', '#e0e3e8'),
    ('kind_video',        '#8f78ff', '#6a4ff0'),
    ('kind_audio',        '#4fc79a', '#1f9a6c'),
    ('kind_text',         '#f0b657', '#b77c12'),
)
PALETTES = {'dark': {role: dark for role, dark, _ in _ROLES},
            'light': {role: light for role, _, light in _ROLES}}

_current = DEFAULT


def normalize(name) -> str:
    return name if name in PALETTES else DEFAULT


def current() -> str:
    return _current


def set_current(name) -> str:
    global _current
    _current = normalize(name)
    return _current


def palette(name=None) -> dict:
    return PALETTES[normalize(name or _current)]


def hex_(role, name=None) -> str:
    return palette(name)[role]


def color(role, name=None) -> QColor:
    return QColor(hex_(role, name))


def _mark(kind, colour) -> str:
    """Path of a small PNG drawn for stylesheets: 'check', 'down' or 'up' in `colour` (made once, then reused).

    Check boxes, combo arrows and spin buttons are drawn from these instead of the style's own, which a
    stylesheet leaves without a frame or an arrow."""
    import tempfile
    from pathlib import Path
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QPen
    folder = Path(tempfile.gettempdir()) / 'akis-ui-marks'
    path = folder / f'{kind}-{colour.lstrip("#")}.png'
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        image = QImage(32, 32, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(colour), 4.2 if kind == 'check' else 3.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        points = {'check': ((7, 16.5), (13.5, 23), (25, 9.5)), 'down': ((9, 12), (16, 20), (23, 12)),
                  'up': ((9, 20), (16, 12), (23, 20))}[kind]
        p.drawPolyline([QPointF(x, y) for x, y in points])
        p.end()
        image.save(str(path))
    return path.as_posix()


def css(template, name=None) -> str:
    """A stylesheet with its `$role` names filled in. Unknown names fail loudly instead of painting black.

    Besides the colour roles, $check_mark, $down_mark and $up_mark name the drawn marks (see _mark)."""
    colours = palette(name)
    return Template(template).substitute(colours, check_mark=_mark('check', '#ffffff'),
                                         down_mark=_mark('down', colours['muted']), up_mark=_mark('up', colours['muted']))


def qt_palette(name=None):
    """Qt's own palette for the theme, for what the style draws itself (check boxes, spin-box arrows,
    menus, the selection in lists), so those match the stylesheet instead of staying dark or light."""
    from PySide6.QtGui import QPalette
    p = palette(name)
    q = QPalette()
    roles = {QPalette.ColorRole.Window: 'bg', QPalette.ColorRole.WindowText: 'text', QPalette.ColorRole.Base: 'field',
             QPalette.ColorRole.AlternateBase: 'panel', QPalette.ColorRole.Text: 'text', QPalette.ColorRole.Button: 'button',
             QPalette.ColorRole.ButtonText: 'text', QPalette.ColorRole.ToolTipBase: 'tooltip',
             QPalette.ColorRole.ToolTipText: 'text_strong', QPalette.ColorRole.Highlight: 'accent',
             QPalette.ColorRole.PlaceholderText: 'faint', QPalette.ColorRole.Light: 'border_hover',
             QPalette.ColorRole.Midlight: 'border_strong', QPalette.ColorRole.Mid: 'border',
             QPalette.ColorRole.Dark: 'border_strong', QPalette.ColorRole.Shadow: 'border'}
    for role, name_ in roles.items():
        q.setColor(role, QColor(p[name_]))
    q.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        q.setColor(QPalette.ColorGroup.Disabled, role, QColor(p['disabled_text']))
    return q
