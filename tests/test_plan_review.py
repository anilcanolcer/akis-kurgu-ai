"""Reviewing an AI edit plan: its parts, keeping only the ticked ones, and the window's review step."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import i18n
from akis.plan_review import PlanReviewDialog, keep, parts

app = QApplication.instance() or QApplication([])
EN = lambda text: i18n.translate(text, 'en')
PLAN = {
    'summary': 'Sessizlikler atıldı, başa yazı kondu.',
    'segments': [{'source': 0, 'start': 0.0, 'end': 4.0}, {'source': 0, 'start': 6.0, 'end': 9.5, 'transition': 'fade'}],
    'remove': ['captions'], 'captions': True,
    'texts': [{'start': 0, 'end': 2, 'text': 'Dikkat! Bu videoyu sonuna kadar izleyin lütfen'}],
    'marks': [{'type': 'circle'}], 'color': {'brightness': 5, 'saturation': -10}, 'speed': 1.25, 'aspect': '9:16',
    'volume': 0.8, 'music_volume': 0.3, 'title': 'Başlık', 'hashtags': ['#a'], 'warnings': ['bir uyarı'],
}


class PartsTests(unittest.TestCase):
    def test_every_change_is_one_line(self):
        found = dict(parts(PLAN))
        self.assertEqual(list(found), ['segments', 'transitions', 'remove:captions', 'captions', 'texts', 'marks', 'color',
                                       'speed', 'aspect', 'volume', 'music_volume', 'publish'])
        self.assertEqual(found['segments'], 'Yeni kesim: 2 parça, yaklaşık 7.5 sn')
        self.assertEqual(found['transitions'], '1 geçiş: fade')
        self.assertTrue(found['texts'].startswith('1 ekran yazısı: Dikkat! Bu videoyu sonuna'))
        self.assertEqual(found['color'], 'Renk: parlaklık +5, doygunluk -10')
        self.assertEqual(found['volume'], 'Video sesi: %80')

    def test_english(self):
        found = dict(parts(PLAN, EN))
        self.assertEqual(found['segments'], 'New cut: 2 pieces, about 7.5 s')
        self.assertEqual(found['color'], 'Colour: brightness +5, saturation -10')
        self.assertEqual(found['remove:captions'], 'Remove the captions')
        self.assertEqual(found['music_volume'], 'Music volume: 30%')

    def test_empty_plan_has_no_parts(self):
        self.assertEqual(parts({'summary': 'x'}), [])


class KeepTests(unittest.TestCase):
    def test_everything_ticked_is_the_same_plan(self):
        self.assertEqual(keep(PLAN, [key for key, _ in parts(PLAN)]), PLAN)

    def test_unticked_parts_are_gone_and_summary_and_warnings_stay(self):
        kept = keep(PLAN, ['segments', 'color'])
        self.assertEqual(set(kept), {'summary', 'warnings', 'segments', 'color'})
        self.assertNotIn('transition', kept['segments'][1])               # transitions were not ticked
        self.assertIn('transition', PLAN['segments'][1])                  # the original is untouched

    def test_publish_and_removals(self):
        kept = keep(PLAN, ['publish', 'remove:captions'])
        self.assertEqual((kept['title'], kept['hashtags'], kept['remove']), ('Başlık', ['#a'], ['captions']))
        self.assertNotIn('caption', kept)


class DialogTests(unittest.TestCase):
    def test_all_ticked_at_first_and_unticking_changes_the_result(self):
        dialog = PlanReviewDialog(PLAN)
        self.assertTrue(all(box.isChecked() for box in dialog.boxes.values()))
        self.assertEqual(dialog.result_plan(), PLAN)
        dialog.boxes['texts'].setChecked(False)
        dialog.boxes['segments'].setChecked(False)
        self.assertFalse(dialog.boxes['transitions'].isEnabled())           # transitions need the new cut
        result = dialog.result_plan()
        self.assertNotIn('texts', result)
        self.assertNotIn('segments', result)
        self.assertIn('color', result)

    def test_nothing_ticked_cannot_be_applied(self):
        dialog = PlanReviewDialog(PLAN)
        for box in dialog.boxes.values():
            box.setChecked(False)
        self.assertFalse(dialog.apply_button.isEnabled())

    def test_english_dialog(self):
        dialog = PlanReviewDialog(PLAN, language='en')
        self.assertEqual(dialog.windowTitle(), 'Review the AI plan')
        self.assertEqual(dialog.apply_button.text(), 'Apply the ticked ones')
        self.assertEqual(dialog.boxes['speed'].text(), 'Speed: 1.25×')


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch('akis.app_support.recovery_dir', return_value=self.root / 'recovery').start()
        patch('akis.media_service.MediaService.duration', return_value=10.0).start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)
        self.video = self.root / 'a.mp4'
        self.video.touch()
        self.assertTrue(self.window.load_video(str(self.video)))
        self.sources = [{'path': str(self.video), 'duration': 10.0}]
        self.plan = {'summary': 'Renk ve hız', 'color': {'brightness': 9}, 'speed': 1.5}

    def close_window(self):
        self.window._close_confirmed = True
        self.window.close()

    def run_plan(self, answer, untick=()):
        def exec_(dialog):
            for key in untick:
                dialog.boxes[key].setChecked(False)
            return answer
        with patch.object(self.window, 'isVisible', return_value=True), \
             patch('akis.plan_review.PlanReviewDialog.exec', new=exec_), \
             patch('main.timeline_service.canvas_size', return_value=(1080, 1920)):
            self.window.on_prompt_edit(dict(self.plan), self.sources)

    def test_only_the_ticked_parts_are_applied(self):
        self.run_plan(1, untick=['speed'])
        self.assertEqual(self.window.brightness.value(), 9)
        self.assertEqual(self.window.speed_value(), 1.0)

    def test_cancelled_review_applies_nothing(self):
        self.run_plan(0)
        self.assertEqual(self.window.brightness.value(), 0)
        self.assertEqual(self.window.status_label.text(), 'AI planı uygulanmadı.')
        self.assertFalse(self.window.undo())

    def test_review_can_be_switched_off_and_is_remembered(self):
        w = self.window
        stored = {}
        with patch.object(w.settings, 'setValue', side_effect=stored.__setitem__):
            w.review_plan.setChecked(False)
        self.assertEqual(stored, {'ai/review_plan': False})
        with patch.object(w, 'isVisible', return_value=True), \
             patch('akis.plan_review.PlanReviewDialog.exec') as shown, \
             patch('main.timeline_service.canvas_size', return_value=(1080, 1920)):
            w.on_prompt_edit(dict(self.plan), self.sources)
        shown.assert_not_called()
        self.assertEqual(w.speed_value(), 1.5)


if __name__ == '__main__':
    unittest.main()
