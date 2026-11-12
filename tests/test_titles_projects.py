"""Long titles fit the frame, trims snap to the playhead, the Edit tab title field, and the Projects dialog."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from akis.caption_service import snap_frame
from akis.media_service import MediaService
from akis.multitrack_widget import MultitrackWidget
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer, fit_text
from tests.test_language_keys import WindowCase

app = QApplication.instance() or QApplication([])
FONT = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arialbd.ttf'


class FitTextTests(unittest.TestCase):
    @unittest.skipUnless(FONT.is_file(), 'Windows font required')
    def test_long_titles_wrap_shrink_and_break(self):
        from PIL import ImageFont
        width = lambda line, size: ImageFont.truetype(str(FONT), size).getlength(line)
        title = 'Bu çok uzun bir başlık ekranın iki yanından taşmamalı ve okunabilir kalmalı'
        lines, size = fit_text(title, FONT, 160, 1000, 900)
        self.assertGreater(len(lines), 2)
        self.assertEqual(' '.join(lines), title)
        self.assertTrue(all(width(line, size) <= 1000 for line in lines))
        word = 'Süperkalifrajilistikekspiyalidosyus'
        lines, size = fit_text(word, FONT, 160, 2000, 900)  # one long word: smaller, still whole
        self.assertEqual(lines, [word])
        self.assertLess(size, 160)
        lines, size = fit_text(word * 2, FONT, 160, 400, 900)  # too wide even when small: broken up
        self.assertEqual(''.join(lines), word * 2)
        self.assertTrue(all(width(line, size) <= 400 for line in lines))
        self.assertEqual(fit_text('Kısa', FONT, 100, 1000, 900), (['Kısa'], 100))
        self.assertEqual(fit_text('iki\r\nsatır', FONT, 100, 1000, 900)[0], ['iki', 'satır'])  # user breaks kept

    @unittest.skipUnless(shutil.which('ffmpeg') and FONT.is_file(), 'FFmpeg and Windows fonts required')
    def test_rendered_long_title_stays_inside_the_frame(self):
        media = MediaService(shutil.which('ffmpeg'))
        with tempfile.TemporaryDirectory() as tmp:
            video = str(Path(tmp) / 'in.mp4')
            media.run(['-y', '-f', 'lavfi', '-i', 'color=c=0x2060c0:s=180x320:r=30:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', video])
            long = 'Bu başlık çok uzun ve kenarlardan taşmamalı ama hepsi okunmalı'
            for style in ({'x': 0.5, 'y': 0.2, 'size': 'large', 'color': 'yellow'}, {}):
                timeline = Timeline(tracks=[Track('video', 'V', [Clip(video, 0, 30, source_length=30)]),
                                            Track('text', 'T', [Clip('', 0, 30, text=long, style=style)])])
                frame = str(Path(tmp) / 'title.png')
                TimelineRenderer(media, (180, 320)).preview(timeline, 10, frame)
                image = QImage(frame)
                background = image.pixelColor(4, 4)
                edges = [image.pixelColor(x, y) for y in range(0, 320, 2) for x in (0, 1, 178, 179)]
                self.assertTrue(all(abs(c.red() - background.red()) + abs(c.blue() - background.blue()) < 60 for c in edges), style)


class SnapTests(unittest.TestCase):
    def test_snap_includes_the_playhead(self):
        clip = Clip('x', 0, 20)
        timeline = Timeline(tracks=[Track('video', 'v', [clip])])
        self.assertEqual(snap_frame(timeline, 47, 4, (0, clip.id), (50,)), 50)
        self.assertEqual(snap_frame(timeline, 40, 4, (0, clip.id), (50,)), 40)

    def test_trimming_a_clip_end_snaps_to_the_playhead(self):
        clip = Clip('x', 0, 30, source_length=300)
        widget = MultitrackWidget(Timeline(tracks=[Track('video', 'v', [clip])]))
        widget.resize(900, 120)
        widget.show()
        widget.playhead = 60
        y = 30 + 20
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(widget.x_for(clip.end)) - 2, y))
        QTest.mouseMove(widget, QPoint(int(widget.x_for(58)), y))  # two frames short of the playhead
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(widget.x_for(58)), y))
        self.assertEqual(clip.end, 60)
        widget.close()


class TitleFieldTests(WindowCase):
    def test_title_field_adds_edits_and_removes_a_title_as_undo_steps(self):
        window = self.window
        window.load_video(str(self.video()))
        window.seek_timeline(15)
        window.overlay.setText('İlk başlık')
        window.title_position.setCurrentIndex(0)
        window.apply_title()
        titles = [c for t in window.multitrack.tracks if t.kind == 'text' for c in t.clips if c.text]
        self.assertEqual([(c.text, c.start, c.style['y'], c.style['size']) for c in titles], [('İlk başlık', 15, 0.15, 'large')])
        window.multitrack_view.selected = None
        window.seek_timeline(20)  # the field follows the title under the playhead
        self.assertEqual(window.overlay.text(), 'İlk başlık')
        window.overlay.setText('Değişti')
        window.apply_title()
        self.assertEqual(titles[0].text, 'Değişti')
        window.overlay.setText('')
        window.apply_title()
        self.assertFalse(any(c.text for t in window.multitrack.tracks for c in t.clips))
        self.assertEqual(len(window._undo_stack), 3)
        window.undo()
        self.assertEqual([c.text for t in window.multitrack.tracks for c in t.clips if c.text], ['Değişti'])


class ProjectsTests(WindowCase):
    def test_delete_open_project_moves_it_to_trash_and_resets_without_restart(self):
        window = self.window
        video = self.video()
        window.load_video(str(video))
        project = self.root / 'demo.akis.json'
        self.save_as(window, project)
        self.assertTrue(project.is_file())
        self.assertEqual(window.recent_projects()[0], str(project))
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(window.delete_project(str(project)))
        self.assertFalse(project.exists())
        self.assertTrue(video.exists())  # media is never deleted
        self.assertNotIn(str(project), window.recent_projects())
        self.assertEqual((window.state.source, window.project_path), ('', ''))
        self.assertFalse(any(t.clips for t in window.multitrack.tracks))
        self.assertEqual(window.project_title.text(), 'Yeni proje')
        window.load_video(str(video))  # the same window keeps working
        self.assertTrue(any(t.clips for t in window.multitrack.tracks))

    def test_new_project_asks_about_unsaved_work_and_starts_empty(self):
        window = self.window
        window.load_video(str(self.video()))
        window.seek_timeline(5)
        window.overlay.setText('Kaydedilmedi')
        window.apply_title()
        window.show()  # confirm_close only asks a visible window
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(window.new_project())
        self.assertTrue(window.state.source)
        with patch('main.QMessageBox.question', return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(window.new_project())
        self.assertEqual(window.state.source, '')
        self.assertEqual((window._undo_stack, window._redo_stack), ([], []))

    def test_settings_used_by_tests_are_not_the_users(self):
        self.assertTrue(self.window.settings.fileName().endswith('settings.ini'))


if __name__ == '__main__':
    unittest.main()
