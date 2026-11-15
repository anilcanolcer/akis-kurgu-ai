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

    def test_gallery_chips_cards_and_detail(self):
        from PySide6.QtWidgets import QLabel
        d = InspirationDialog()
        self.assertEqual(len(d.filter_buttons), len(svc.categories()) + 1)
        self.assertEqual(d.filter_buttons[0].text(), f'Tümü  {len(svc.IDEAS)}')
        d.filter_buttons[2].click()                                   # a category chip filters like the combo
        self.assertEqual(d.category.currentIndex(), 2)
        self.assertEqual(d.list.count(), len(svc.ideas(svc.categories()[1])))
        self.assertFalse(d.list.item(0).icon().isNull())             # every idea has its card picture
        idea = d.current_idea()
        rows = [w for w in d.findChildren(QLabel) if w.objectName() == 'ideaStep' and w.parent().parent() is not None]
        self.assertEqual([r.text() for r in rows], list(idea.shots))
        self.assertEqual(d.hook.text(), idea.hook)
        self.assertEqual(d.prompt.text(), idea.prompt)
        d.category.setCurrentIndex(0)
        self.assertTrue(d.filter_buttons[0].isChecked())              # and the combo moves the chips
        row = next(i for i, x in enumerate(svc.IDEAS) if not x.template)
        d.list.setCurrentRow(row)
        self.assertTrue(d.template_title.isHidden())
        d.template_button.click()                                     # no template: nothing happens
        self.assertIsNone(d.selection()[1])

    def test_english_headings(self):
        d = InspirationDialog(language='en')
        self.assertEqual(d.windowTitle(), 'Inspiration')
        self.assertEqual(d.template_button.text(), 'Write idea and apply its template')
        self.assertEqual(d.findChild(type(d.hook), None) is not None, True)

    def test_english_ideas_cards_chips_search_and_choice(self):
        import re
        from akis import inspiration_en
        turkish = re.compile('[ğüşıöçĞÜŞİÖÇ]')
        self.assertEqual(set(inspiration_en.IDEAS), {i.key for i in svc.IDEAS})        # every idea is translated
        self.assertEqual(set(inspiration_en.CATEGORIES), set(svc.categories()))
        for idea in svc.IDEAS:
            english = svc.localized(idea, 'en')
            self.assertEqual(len(english.shots), len(idea.shots), idea.key)              # one step for each step
            self.assertEqual((english.key, english.category, english.template), (idea.key, idea.category, idea.template))
            words = ' '.join((english.title, english.hook, english.description, english.prompt, *english.shots))
            self.assertIsNone(turkish.search(words), idea.key)
        self.assertIs(svc.localized(svc.IDEAS[0], 'tr'), svc.IDEAS[0])
        self.assertTrue(any(i.key == 'yagmur-sehir' for i in svc.ideas(query='rainy')))    # English words find it
        self.assertTrue(any(i.key == 'yagmur-sehir' for i in svc.ideas(query='yağmurlu', language='en')))
        d = InspirationDialog(language='en')
        self.assertEqual([b.text().rsplit('  ', 1)[0] for b in d.filter_buttons][:2], ['All', 'Storytelling'])
        d.filter_buttons[2].click()                                                       # "Product / promo"
        self.assertEqual(d.list.count(), len(svc.ideas(svc.categories()[1])))
        self.assertEqual(d.category_chip.text(), 'Product / promo')
        self.assertIsNone(turkish.search(d.list.item(0).text()))
        idea = d.current_idea()
        d.prompt_button.click()
        chosen, action = d.selection()
        self.assertEqual((chosen.key, action), (idea.key, 'prompt'))
        self.assertEqual(chosen.prompt, inspiration_en.IDEAS[idea.key][4])               # the English request is written
        d.search.setText('rainy')
        self.assertEqual([d.list.item(i).text().split('\n')[0] for i in range(d.list.count())], [])  # other category
        d.filter_buttons[0].click()
        self.assertEqual(d.list.item(0).text().split('\n')[0], 'Rainy city')

    def test_template_dialog_title(self):
        self.assertEqual(TemplateDialog().windowTitle(), 'Şablonlar')


if __name__ == '__main__':
    unittest.main()
