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
    ('bg',                '#0d0e12', '#f3f4f7'),   # the window
    ('surface',           '#111218', '#ffffff'),   # sidebar, editor, tab pages, timeline
    ('panel',             '#171921', '#f4f5f8'),   # cards inside a surface
    ('field',             '#171920', '#ffffff'),   # text boxes, combo boxes, filter buttons
    ('raised',            '#1d1f29', '#eceef3'),   # chips, secondary buttons, timeline track rows
    ('button',            '#20222c', '#e7e9ef'),
    ('button_hover',      '#292c38', '#dcdfe7'),
    ('border',            '#252733', '#dddfe6'),
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
    ('tooltip',           '#232631', '#ffffff'),
    ('video_bg',          '#08090c', '#1c1d24'),   # behind the picture: dark in both, videos read better
    ('video_text',        '#9195a7', '#a3a7b8'),
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
