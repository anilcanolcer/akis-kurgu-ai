"""İlham and Şablonlar open different dialogs, and suggestions are shown as readable text."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QPushButton

import main
from akis import inspiration_service


class InspirationFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch('akis.ai_providers.load_key', return_value=''):
            self.window = main.MainWindow()
        self.addCleanup(self.window.deleteLater)

    def nav_button(self, word):
        return next(b for b in self.window.findChildren(QPushButton) if b.property('nav') and word in b.text())

    def test_sidebar_entries_open_different_dialogs(self):
        with patch.object(main.InspirationDialog, 'exec', return_value=0) as inspiration, \
                patch.object(main.TemplateDialog, 'exec', return_value=0) as templates:
            self.nav_button('İlham').click()
            self.assertEqual((inspiration.call_count, templates.call_count), (1, 0))
            self.nav_button('Şablon').click()
            self.assertEqual((inspiration.call_count, templates.call_count), (1, 1))

    def test_idea_fills_the_edit_request_without_touching_the_timeline(self):
        idea = inspiration_service.IDEAS[0]
        before = self.window.multitrack.to_dict()
        with patch.object(main.InspirationDialog, 'exec', return_value=1), \
                patch.object(main.InspirationDialog, 'selection', return_value=(idea, 'prompt')):
            self.window.show_inspiration()
        self.assertEqual(self.window.ai_prompt.toPlainText(), idea.prompt)
        self.assertEqual(self.window.multitrack.to_dict(), before)

    def test_idea_with_template_applies_it_as_one_undo_step(self):
        idea = next(i for i in inspiration_service.IDEAS if i.template)
        template = inspiration_service.template_for(idea)
        with patch.object(main.InspirationDialog, 'exec', return_value=1), \
                patch.object(main.InspirationDialog, 'selection', return_value=(idea, 'prompt+template')):
            self.window.show_inspiration()
        names = {track.name for track in self.window.multitrack.tracks}
        self.assertTrue({name for _, name in template.tracks} <= names)
        self.assertEqual(len(self.window._undo_stack), 1)

    def test_suggestions_are_shown_as_text_and_applied(self):
        plan = {'title': 'Kanca', 'summary': 'Özet', 'caption': 'Açıklama', 'hashtags': ['bir', '#iki'], 'notes': [],
                'pacing': 'hızlı', 'filter': 'vivid', 'trim_start': 3.0, 'trim_end': 27.0}
        self.window.on_ai_plan([plan])
        shown = self.window.ai_result.toPlainText()
        self.assertIn('Kanca', shown)
        self.assertIn('0:03', shown)
        self.assertNotIn('{', shown)  # no raw JSON
        self.window.apply_ai_suggestion()
        self.assertEqual(self.window.publish_tags.toPlainText(), '#bir #iki')
        self.assertEqual(len(self.window.multitrack.markers), 2)


if __name__ == '__main__':
    unittest.main()
