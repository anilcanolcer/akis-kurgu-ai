"""Word-by-word captions: chunks, placement through the edit, splitting, drawing, rendering and the selector."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from akis import ai_providers, word_captions
from akis.caption_service import caption_track
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer
from akis.timeline_slice import slice_timeline

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')
FONT = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf'


def words(*items):
    return [{'text': t, 'start': a, 'end': b} for t, a, b in items]


SPOKEN = words(('Bugün', 1.0, 1.4), ('size', 1.5, 1.8), ('çok', 1.9, 2.1), ('güzel', 2.2, 2.6),
               ('bir', 2.7, 2.9), ('şey', 3.0, 3.3), ('göstereceğim.', 3.4, 4.2), ('Hazır', 5.5, 5.9), ('mısınız?', 6.0, 6.6))


class ChunkTests(unittest.TestCase):
    def test_short_chunks_cut_at_pauses_and_sentence_ends(self):
        found = [[t for _, _, t in chunk] for chunk in word_captions.chunks(SPOKEN)]
        self.assertEqual(found, [['Bugün', 'size', 'çok'], ['güzel', 'bir', 'şey'], ['göstereceğim.'],
                                 ['Hazır', 'mısınız?']])
        long = words(('uzuuuuuun', 0, 1), ('kelimeler', 1, 2), ('burada', 2, 3))
        self.assertEqual([len(c) for c in word_captions.chunks(long)], [1, 2])   # too many letters for one chunk
        self.assertEqual(word_captions.chunks([{'text': ''}, {'start': 1}, 'x']), [])

    def test_cloud_words_keep_their_timings(self):
        segments = ai_providers.group_words(SPOKEN)
        self.assertEqual(segments[0]['words'][0], {'text': 'Bugün', 'start': 1.0, 'end': 1.4})
        self.assertEqual(sum(len(s['words']) for s in segments), len(SPOKEN))


class PlacementTests(unittest.TestCase):
    def timeline(self, **clip):
        video = Clip('a.mp4', 0, 100, **clip)
        return Timeline(fps_num=10, tracks=[Track('video', 'V', [video])])

    def test_word_track_follows_the_clip(self):
        timeline = self.timeline(source_in=10)          # the edit starts 1 s into the source
        count = caption_track(timeline, 'a.mp4', [{'start': 1, 'end': 7, 'text': 'x', 'words': SPOKEN}], 'kutu')
        track = timeline.tracks[-1]
        self.assertEqual((count, track.name), (4, 'Altyazı / Captions'))
        first = track.clips[0]
        self.assertEqual((first.start, first.text, first.style['look']), (0, 'Bugün size çok', 'kutu'))
        self.assertEqual(first.style['words'][1], [5, 8, 'size'])
        self.assertEqual(track.clips[-1].start, 45)

    def test_fast_clip_and_classic_look(self):
        timeline = self.timeline(style={'speed': 2.0})
        caption_track(timeline, 'a.mp4', [{'start': 1, 'end': 7, 'text': 'x', 'words': SPOKEN}], 'vurgu')
        self.assertEqual(timeline.tracks[-1].clips[0].start, 5)            # source 1.0 s at 2× = timeline 0.5 s
        classic = self.timeline()
        caption_track(classic, 'a.mp4', [{'start': 1, 'end': 7, 'text': 'Bir cümle.', 'words': SPOKEN}], 'klasik')
        self.assertEqual([c.text for c in classic.tracks[-1].clips], ['Bir cümle.'])
        self.assertFalse(classic.tracks[-1].clips[0].style)

    def test_states_light_each_word_until_the_next(self):
        clip = Clip('', 0, 20, text='a b', style={'words': [[3, 6, 'a'], [9, 12, 'b']], 'look': 'vurgu'})
        self.assertEqual(word_captions.states(clip), [(0, 3, None), (3, 9, 0), (9, 20, 1)])

    def test_split_trim_and_slice_rebase_the_words(self):
        clip = Clip('', 0, 30, text='a b c', style={'words': [[0, 8, 'a'], [10, 18, 'b'], [20, 28, 'c']], 'look': 'vurgu'})
        track = Track('text', 'T', [clip])
        right = track.split(clip.id, 15)
        self.assertEqual(clip.style['words'], [[0, 8, 'a'], [10, 15, 'b']])
        self.assertEqual(right.style['words'], [[0, 3, 'b'], [5, 13, 'c']])
        track.trim_start(right.id, 19)
        self.assertEqual(right.style['words'], [[1, 9, 'c']])
        whole = Clip('', 0, 30, text='a b c', style={'words': [[0, 8, 'a'], [10, 18, 'b'], [20, 28, 'c']]})
        part = slice_timeline(Timeline(fps_num=10, tracks=[Track('text', 'T', [whole])]), 12, 30)
        self.assertEqual(part.tracks[0].clips[0].style['words'], [[0, 6, 'b'], [8, 16, 'c']])


@unittest.skipUnless(FONT.is_file(), 'Arial gerekli')
class DrawTests(unittest.TestCase):
    def test_lit_word_is_coloured_and_stays_inside_the_picture(self):
        items = [[0, 5, 'Merhaba'], [5, 9, 'dünya']]
        canvas, rect = (360, 640), (0, 218, 360, 203)
        for look in word_captions.LOOKS:
            image = word_captions.draw(items, 1, look, canvas, rect, FONT, 40)
            box = image.getbbox()
            self.assertIsNotNone(box, look)
            self.assertTrue(rect[1] <= box[1] and box[3] <= rect[1] + rect[3], (look, box))
        lit = word_captions.draw(items, 1, 'vurgu', canvas, rect, FONT, 40).convert('RGB')
        colours = set(lit.getdata())
        self.assertIn(word_captions.HIGHLIGHT, colours)
        none = word_captions.draw(items, None, 'vurgu', canvas, rect, FONT, 40).convert('RGB')
        self.assertNotIn(word_captions.HIGHLIGHT, set(none.getdata()))
        self.assertIn(word_captions.BOX, set(word_captions.draw(items, 0, 'kutu', canvas, rect, FONT, 40).convert('RGB').getdata()))


@unittest.skipUnless(FFMPEG and FONT.is_file(), 'ffmpeg ve Arial gerekli')
class RenderTests(unittest.TestCase):
    def test_export_and_preview_show_the_lit_word_and_use_one_input(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        clips = [Clip('', 0, 20, text='Bir iki', style={'words': [[0, 10, 'Bir'], [10, 20, 'iki']], 'look': 'vurgu'}),
                 Clip('', 30, 20, text='üç dört', style={'words': [[0, 10, 'üç'], [10, 20, 'dört']], 'look': 'vurgu'})]
        timeline = Timeline(fps_num=10, tracks=[Track('text', 'Altyazı / Captions', clips)])
        media = MediaService(FFMPEG)
        renderer = TimelineRenderer(media, (640, 360), font=str(FONT))
        seen = []
        original = media.run
        with patch.object(media, 'run', side_effect=lambda args, **kw: seen.append(args) or original(args, **kw)):
            renderer.export(timeline, root / 'out.mp4')
        self.assertEqual(sum(1 for args in seen for a in args if a == 'concat'), 1)
        self.assertAlmostEqual(media.duration(root / 'out.mp4'), 5.0, delta=0.15)

        def yellow_at(second):
            raw = subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{second}', '-i', str(root / 'out.mp4'), '-frames:v', '1',
                                  '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
            pixels = [raw[i:i + 3] for i in range(0, len(raw), 3)]
            return sum(1 for p in pixels if p[0] > 200 and p[1] > 180 and p[2] < 90)

        self.assertGreater(yellow_at(0.5), 20)        # "Bir" lit
        self.assertGreater(yellow_at(1.5), 20)        # "iki" lit
        self.assertEqual(yellow_at(2.5), 0)           # the gap between captions is empty
        renderer.preview(timeline, 35, root / 'frame.png')
        self.assertTrue((root / 'frame.png').is_file())


class WindowTests(unittest.TestCase):
    def setUp(self):
        from main import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch('main.recovery_dir', return_value=Path(self.tmp.name) / 'recovery').start()
        self.addCleanup(patch.stopall)
        self.window = MainWindow()
        self.window.apply_language('tr')
        patch.object(self.window.preview, 'request').start()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.settings.remove('captions/look')
        self.window._close_confirmed = True
        self.window.close()

    def test_chosen_look_makes_word_captions_and_is_remembered(self):
        w = self.window
        w.show_timeline(Timeline(fps_num=10, tracks=[Track('video', 'V', [Clip('a.mp4', 0, 100)])]))
        w.caption_look.setCurrentIndex(word_captions.CHOICES.index('karaoke'))
        self.assertEqual(w.settings.value('captions/look'), 'karaoke')
        w.caption_source, w.caption_segments = 'a.mp4', [{'start': 1, 'end': 7, 'text': 'x', 'words': SPOKEN}]
        w.apply_local_captions()
        captions = w.multitrack.tracks[-1]
        self.assertEqual(captions.clips[0].style['look'], 'karaoke')
        w.apply_language('en')
        self.assertEqual(w.caption_look.itemText(3), 'Word by word: karaoke')


if __name__ == '__main__':
    unittest.main()
