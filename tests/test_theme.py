"""Colours live in akis.theme: every stylesheet fills from it, both themes are complete and readable,
and the window switches between them, remembering the choice."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from akis import start_panel, template_dialog, theme

app = QApplication.instance() or QApplication([])


def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def stylesheets():
    import main
    return {'main': main.STYLE, 'start': start_panel.STYLE, 'templates': template_dialog.DIALOG_STYLE}


class PaletteTests(unittest.TestCase):
    def test_both_themes_name_the_same_roles(self):
        self.assertEqual(set(theme.PALETTES['dark']), set(theme.PALETTES['light']))
        for name in theme.PALETTES:
            for role, value in theme.PALETTES[name].items():
                self.assertRegex(value, r'^#[0-9a-f]{6}$', (name, role))

    def test_stylesheets_take_every_colour_from_the_theme(self):
        for key, sheet in stylesheets().items():
            self.assertEqual(re.findall(r'#[0-9a-fA-F]{6}\b', sheet), [], key)
            for name in theme.PALETTES:
                filled = theme.css(sheet, name)              # an unknown $role raises KeyError
                self.assertNotIn('$', filled, key)
        self.assertIn(theme.PALETTES['light']['bg'], theme.css(stylesheets()['main'], 'light'))

    def test_text_is_readable_on_every_background(self):
        for name in theme.PALETTES:
            p = theme.PALETTES[name]
            for back in ('bg', 'surface', 'panel', 'field', 'raised', 'button'):
                self.assertGreaterEqual(contrast(p['text'], p[back]), 7.0, (name, back))
                self.assertGreaterEqual(contrast(p['muted'], p[back]), 3.0, (name, back))
            self.assertGreaterEqual(contrast('#ffffff', p['accent']), 4.5, name)        # primary buttons
            self.assertGreaterEqual(contrast(p['notice_text'], p['notice_bg']), 4.5, name)
            self.assertGreaterEqual(contrast(p['clip_text'], p['track_video']), 3.0, name)

    def test_unknown_names_fall_back_to_dark(self):
        self.assertEqual(theme.normalize('purple'), 'dark')
        self.assertEqual(theme.normalize(None), 'dark')
        try:
            self.assertEqual(theme.set_current('light'), 'light')
            self.assertEqual(theme.color('surface').name(), theme.PALETTES['light']['surface'])
        finally:
            theme.set_current('dark')


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        # Earlier test modules leave closed windows behind. Restyling the application restyles every one
        # of them, which took many minutes in a full local run; only this test's window is needed.
        for widget in app.topLevelWidgets():
            widget.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch('akis.app_support.recovery_dir', return_value=Path(self.tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.settings.remove('theme')
        self.addCleanup(self.close_window)
        self.old_sheet = app.styleSheet()
        self.addCleanup(lambda: app.setStyleSheet(self.old_sheet))

    def close_window(self):
        theme.set_current('dark')
        self.window.settings.remove('theme')
        self.window._close_confirmed = True
        self.window.close()

    def test_switching_restyles_repaints_and_remembers(self):
        w = self.window
        w.theme_box.setCurrentIndex(1)
        self.assertEqual(theme.current(), 'light')
        self.assertEqual(w.settings.value('theme'), 'light')
        self.assertIn('background: ' + theme.PALETTES['light']['bg'], app.styleSheet())
        self.assertIn(theme.hex_('surface'), w.start_panel.styleSheet() + app.styleSheet())
        self.assertIn(theme.PALETTES['light']['accent_text'], w.brand.text())
        image = w.multitrack_view.grab().toImage()
        self.assertEqual(image.pixelColor(image.width() - 3, image.height() - 3).name(), theme.PALETTES['light']['surface'])
        w.theme_box.setCurrentIndex(0)
        self.assertEqual((theme.current(), w.settings.value('theme')), ('dark', 'dark'))
        self.assertIn(theme.PALETTES['dark']['accent_text'], w.brand.text())

    def test_names_follow_the_language(self):
        w = self.window
        w.apply_language('en')
        self.assertEqual([w.theme_box.itemText(i) for i in range(2)], ['Dark theme', 'Light theme'])
        self.assertEqual(w.brand.text().count('KURGU'), 1)         # the brand is never translated
        w.apply_language('tr')
        self.assertEqual(w.theme_box.itemText(1), 'Açık tema')

    def test_sidebar_switches_choose_theme_and_language_and_follow_code(self):
        w = self.window
        # Clicking below saves choices: they must land in the tests' scratch file, not the user's settings.
        self.assertEqual(Path(w.settings.fileName()), Path(os.environ['AKIS_SETTINGS_FILE']))
        self.assertTrue(w.theme_box.isHidden() and w.language.isHidden())           # the switches replace the combos
        dark, light = w.theme_switch.group.buttons()
        turkish, english = w.language_switch.group.buttons()
        self.assertEqual([b.text() for b in (dark, light)], ['Koyu', 'Açık'])
        self.assertFalse(dark.icon().isNull() or light.icon().isNull())
        light.click()
        self.assertEqual((theme.current(), w.settings.value('theme'), w.theme_box.currentIndex()), ('light', 'light', 1))
        self.assertTrue(light.isChecked() and not dark.isChecked())
        w.apply_theme('dark')                                    # code changing the theme moves the switch too
        self.assertTrue(dark.isChecked())
        english.click()
        self.assertEqual((w.ui_language(), w.language.currentData()), ('en', 'en'))
        self.assertEqual([b.text() for b in (dark, light)], ['Dark', 'Light'])
        self.assertEqual([b.text() for b in (turkish, english)], ['Türkçe', 'English'])   # names stay in their language
        w.apply_language('tr')
        self.assertTrue(turkish.isChecked())
        w.set_status(w.ui_text('Görünüm değiştirildi.'))
        w.apply_language('en')
        self.assertEqual(w.status_label.text(), 'Appearance changed.')            # a fixed message follows the switch
        w.apply_language('tr')
        self.assertEqual(w.status_label.text(), 'Görünüm değiştirildi.')
        self.assertEqual(w.language.currentData(), 'tr')
        w.settings.remove('language')


if __name__ == '__main__':
    unittest.main()
