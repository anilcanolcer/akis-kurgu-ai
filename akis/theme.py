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
    ('bg',                '#0d0e12', '#eceef2'),   # the window
    ('surface',           '#111218', '#f6f7f9'),   # sidebar, editor, tab pages, timeline
    ('panel',             '#171921', '#eef0f4'),   # cards inside a surface
    ('field',             '#171920', '#fbfbfc'),   # text boxes, combo boxes, filter buttons
    ('raised',            '#1d1f29', '#e5e8ee'),   # chips, secondary buttons, timeline track rows
    ('button',            '#20222c', '#e3e6ed'),
    ('button_hover',      '#292c38', '#d8dce5'),
    ('border',            '#252733', '#d9dce4'),
    ('border_strong',     '#303340', '#c9ccd7'),
    ('border_hover',      '#3a3e4e', '#b2b6c4'),
    ('text',              '#f3f4f8', '#1b1d26'),
    ('text_strong',       '#ffffff', '#0d0e12'),   # selected tab, active nav item
    ('text_soft',         '#b8bbca', '#454959'),
    ('muted',             '#9195a7', '#626678'),
    ('faint',             '#7d8194', '#8a8ea0'),
    ('accent',            '#7357f5', '#7357f5'),   # primary buttons: white text in both themes
    ('accent_hover',      '#876eff', '#6447ea'),
    ('accent_line',       '#8f78ff', '#6a4ff0'),   # selection borders, slider, progress
    ('accent_text',       '#b4a6ff', '#5b3fe0'),   # accent coloured text and focus rings
    ('accent_bg',         '#241f3d', '#e9e4ff'),   # selected list item, checked filter, active nav
    ('disabled',          '#2a2c38', '#e3e5eb'),
    ('disabled_text',     '#777b8c', '#9a9eae'),
    ('success',           '#74d9ac', '#1d8a5b'),
    ('notice_bg',         '#1f1b12', '#fff6df'),
    ('notice_border',     '#4a3c1c', '#ecd394'),
    ('notice_text',       '#f0cf8e', '#7a5810'),
    ('tooltip',           '#232631', '#fbfbfc'),
    ('video_bg',          '#08090c', '#d7dae1'),   # behind the picture: a soft grey stage in the light theme
    ('video_text',        '#9195a7', '#5b6072'),
    ('video_caption',     '#e8e9f0', '#e8e9f0'),
    ('track_video',       '#5a49a8', '#7d6ad6'),
    ('track_audio',       '#257e77', '#3ea59c'),
    ('track_text',        '#a55a83', '#c2709d'),
    ('track_overlay',     '#9c703c', '#c08d4f'),
    ('clip_text',         '#ffffff', '#ffffff'),
    ('clip_edge',         '#282a37', '#9ea2b3'),
    ('clip_selected',     '#ffffff', '#1b1d26'),
    ('waveform',          '#a4e3db', '#e6fbf8'),
    ('marker',            '#ffcd5a', '#d99a00'),
    ('playhead',          '#ff4fa3', '#e8247f'),
    ('kept',              '#2f9e6e', '#2f9e6e'),
    ('cut',               '#d6453d', '#d6453d'),
    ('empty',             '#2a2f37', '#d6d9e1'),
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


def css(template, name=None) -> str:
    """A stylesheet with its `$role` names filled in. Unknown names fail loudly instead of painting black."""
    return Template(template).substitute(palette(name))


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
