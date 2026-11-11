import os
import random
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from akis import inspiration_service as svc
from akis.template_service import TEMPLATES
from akis.inspiration_dialog import InspirationDialog
from akis.template_dialog import TemplateDialog

app = QApplication.instance() or QApplication([])


class InspirationServiceTests(unittest.TestCase):
    def test_catalog(self):
        self.assertGreaterEqual(len(svc.IDEAS), 18)
        self.assertEqual(len({i.key for i in svc.IDEAS}), len(svc.IDEAS))
        self.assertEqual(len({i.title for i in svc.IDEAS}), len(svc.IDEAS))
        names = {t.name for t in TEMPLATES}
        for idea in svc.IDEAS:
            self.assertIn(idea.template, names | {''})
            self.assertNotIn(idea.title, names)
            self.assertTrue(4 <= len(idea.shots) <= 6, idea.key)
            self.assertTrue(idea.hook and idea.description and idea.prompt)
        self.assertGreaterEqual(len(svc.categories()), 6)

    def test_filter_and_search(self):
        cat = svc.categories()[0]
        self.assertTrue(svc.ideas(cat))
        self.assertTrue(all(i.category == cat for i in svc.ideas(cat)))
        self.assertEqual(len(svc.ideas()), len(svc.IDEAS))
        self.assertTrue(svc.ideas(query='yağmurlu'))
        self.assertTrue(any(i.key == 'sonu-basa' for i in svc.ideas(query='SONU BAŞA')))
        self.assertEqual(svc.ideas(query='zzzqqq'), [])
        self.assertEqual(svc._fold('İLHAM'), svc._fold('ilham'))

    def test_random_and_template_for(self):
        self.assertEqual(svc.random_idea(rng=random.Random(3)), svc.random_idea(rng=random.Random(3)))
        self.assertIsNone(svc.random_idea('yok'))
        with_t = next(i for i in svc.IDEAS if i.template)
        self.assertEqual(svc.template_for(with_t).name, with_t.template)
        self.assertIsNone(svc.template_for(next(i for i in svc.IDEAS if not i.template)))


class InspirationDialogTests(unittest.TestCase):
    def test_lists_and_filters(self):
        d = InspirationDialog()
        self.assertEqual(d.windowTitle(), 'İlham')
        self.assertEqual(d.list.count(), len(svc.IDEAS))
        d.category.setCurrentText(svc.categories()[1])
        self.assertEqual(d.list.count(), len(svc.ideas(svc.categories()[1])))
        d.category.setCurrentIndex(0)
        d.search.setText('zzzqqq')
        self.assertEqual(d.list.count(), 0)
        self.assertFalse(d.prompt_button.isEnabled())
        d.search.setText('')
        self.assertEqual(d.list.count(), len(svc.IDEAS))

    def test_selection_actions(self):
        d = InspirationDialog()
        d.list.setCurrentRow(0)
        d.prompt_button.click()
        self.assertEqual(d.selection(), (svc.IDEAS[0], 'prompt'))
        d = InspirationDialog()
        d.list.setCurrentRow(0)
        self.assertTrue(d.template_button.isEnabled())
        d.template_button.click()
        self.assertEqual(d.selection(), (svc.IDEAS[0], 'prompt+template'))
        d = InspirationDialog()
        d.close_button.click()
        self.assertEqual(d.result(), 0)

    def test_template_button_disabled_without_template(self):
        d = InspirationDialog()
        row = next(i for i, idea in enumerate(svc.IDEAS) if not idea.template)
        d.list.setCurrentRow(row)
        self.assertFalse(d.template_button.isEnabled())
        self.assertTrue(d.prompt_button.isEnabled())

    def test_random_button_selects_an_idea(self):
        d = InspirationDialog()
        d.random_button.click()
        self.assertIsNotNone(d.selection()[0])

    def test_template_dialog_title(self):
        self.assertEqual(TemplateDialog().windowTitle(), 'Şablonlar')


if __name__ == '__main__':
    unittest.main()
