"""Şablonlar dialog: filtering, what it reports about the open project, language, and track order."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtWidgets import QApplication

from akis import i18n
from akis.template_dialog import TemplateDialog
from akis.template_service import TEMPLATES, STYLES, TEMPOS, apply_template
from akis.timeline_model import Clip, Timeline, Track

app = QApplication.instance() or QApplication([])


class TemplateDialogTests(unittest.TestCase):
    def test_opens_with_first_template_and_its_defaults(self):
        d = TemplateDialog()
        template, style, tempo = d.selection()
        self.assertIs(template, TEMPLATES[0])
        self.assertEqual((style, tempo), (template.style, template.tempo))
        self.assertEqual(d.list.count(), len(TEMPLATES))
        self.assertTrue(d.apply_button.isDefault() and d.apply_button.isEnabled())

    def test_filter_shows_only_that_ratio_and_selection_stays_valid(self):
        d = TemplateDialog()
        for button in d.filter_buttons:
            ratio = button.property('ratio')
            button.click()
            shown = [TEMPLATES[d.list.item(i).data(0x0100)] for i in range(d.list.count())]  # Qt.UserRole
            self.assertEqual(shown, [t for t in TEMPLATES if ratio in (None, t.ratio)])
            self.assertIn(d.selection()[0], shown)

    def test_selection_keeps_adjusted_style_and_tempo_as_keys(self):
        d = TemplateDialog(language='en')
        d.style.setCurrentIndex(d.style.findData('Siyah-Beyaz'))
        d.tempo.setCurrentIndex(d.tempo.findData('Yavaş'))
        _template, style, tempo = d.selection()
        self.assertIn(style, STYLES)
        self.assertIn(tempo, TEMPOS)
        self.assertEqual((style, tempo), ('Siyah-Beyaz', 'Yavaş'))

    def test_says_what_changes_in_the_open_project(self):
        timeline = Timeline(tracks=[Track('video', 'Ana video'), Track('text', 'Text')])
        d = TemplateDialog(current_aspect='16:9', timeline=timeline)
        self.assertFalse(d.notice.isHidden())  # the first template is 9:16
        self.assertIn('16:9', d.notice.text())
        self.assertIn('projede var', d.contents.text())
        same = TemplateDialog(current_aspect=TEMPLATES[0].ratio, timeline=timeline)
        self.assertTrue(same.notice.isHidden())

    def test_english_dialog_has_no_untranslated_template_text(self):
        d = TemplateDialog(language='en')
        self.assertEqual(d.windowTitle(), 'Templates')
        self.assertEqual(d.apply_button.text(), 'Apply template')
        for template in TEMPLATES:
            for text in (template.summary, template.title):
                self.assertIn(text, i18n.EN_UI)

    def test_every_template_has_a_summary_and_platforms(self):
        for template in TEMPLATES:
            self.assertTrue(template.summary and template.platforms, template.name)


class TrackOrderTests(unittest.TestCase):
    def test_new_video_tracks_go_below_existing_text_tracks(self):
        title = Clip(source='', start=0, length=30, text='Merhaba')
        timeline = Timeline(tracks=[Track('video', 'Video'), Track('audio', 'Audio'), Track('text', 'Text', [title])])
        apply_template(timeline, TEMPLATES[0])
        kinds = [t.kind for t in timeline.tracks]
        first_text = kinds.index('text')
        self.assertTrue(all(kind == 'text' for kind in kinds[first_text:]), kinds)
        self.assertIs(timeline.tracks[first_text].clips[0], title)

    def test_applying_twice_adds_no_duplicate_tracks(self):
        timeline = Timeline(tracks=[Track('video', 'Video')])
        apply_template(timeline, TEMPLATES[0])
        count = len(timeline.tracks)
        apply_template(timeline, TEMPLATES[0])
        self.assertEqual(len(timeline.tracks), count)


if __name__ == '__main__':
    unittest.main()
