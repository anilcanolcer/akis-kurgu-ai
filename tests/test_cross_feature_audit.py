"""Regression checks at the boundaries between editing, rendering and project portability."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from akis import project_service, shorts_split
from akis.caption_service import caption_track
from akis.timeline_model import Clip, Timeline, Track
from akis.window.project import ProjectMixin


class TimelineInteractions(unittest.TestCase):
    def test_caption_uses_the_fractional_source_bounds(self):
        # 13.5 .. 16.5 source frames. At 30 fps both sentences and words
        # should lie entirely inside this two-frame clip.
        for look in ('klasik', 'vurgu'):
            with self.subTest(look=look):
                clip = Clip('a.mp4', 20, 2, source_in=13, style={'speed': 1.5, 'source_phase': 0.5})
                timeline = Timeline(tracks=[Track('video', 'V', [clip])])
                segment = {'start': 15.8 / 30, 'end': 16.45 / 30, 'text': 'son'}
                self.assertEqual(caption_track(timeline, clip.source, [dict(segment, words=[segment])], look), 1)
                made, = timeline.tracks[-1].clips
                self.assertEqual((made.start, made.end), (21, 22))

    def test_word_start_stays_anchored_when_extending_left(self):
        clip = Clip('', 10, 10, text='a', style={'words': [[2, 7, 'a']]})
        track = Track('text', 'T', [clip])
        track.trim_start(clip.id, 6)
        self.assertEqual(clip.style['words'], [[6, 11, 'a']])

    def test_shorts_transcript_time_matches_fractional_clip(self):
        clip = Clip('a.mp4', 20, 2, source_in=13, style={'speed': 1.5, 'source_phase': 0.5})
        timeline = Timeline(tracks=[Track('video', 'V', [clip])])
        segments = [{'start': 13.2 / 30, 'text': 'kesildi'}, {'start': 16.2 / 30, 'text': 'kaldi'}]
        (when, words), = shorts_split.spoken_on_timeline(timeline, clip.source, segments)
        self.assertEqual(words, 'kaldi')
        self.assertAlmostEqual(when, 21.8 / 30)

    def test_shape_split_keeps_its_drawing_and_entrance(self):
        clip = Clip('', 0, 20, id='original', style={'shape': 'circle'})
        track = Track('text', 'T', [clip])
        right = track.split(clip.id, 8)
        self.assertEqual(right.style['_shape_seed_id'], 'original')
        self.assertEqual(right.style['_shape_offset'], 8)
        self.assertEqual(clip.style['_shape_length'], 20)


class ProjectInteractions(unittest.TestCase):
    def test_manually_relinked_photo_survives_another_cache_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / 'project.akis.json'
            original_photo = str(root / 'old.png')
            original_clip = str(root / 'old-cache.mp4')
            photo = root / 'renamed.png'
            photo.touch()
            rendered = root / 'new-cache.mp4'
            rendered.touch()
            clip = Clip(original_clip, 0, 150, style={'still_image': original_photo})
            timeline = Timeline(tracks=[Track('video', 'V', [clip])])
            project_service.save(project, project_service.make_document({}, timeline, {}, ''))

            class Window:
                def isVisible(self):
                    return True

                def ui_text(self, message, **fields):
                    return message.format(**fields)

                def rebuild_still(self, image):
                    return str(rendered)

            with patch('akis.window.project.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
                    patch('akis.window.project.QFileDialog.getOpenFileName', return_value=(str(photo), '')):
                media = ProjectMixin.locate_missing_media(Window(), str(project))
            loaded, _, missing = project_service.load_project(project, media)
            self.assertEqual(missing, [])
            self.assertEqual(project_service.still_images(loaded), {str(rendered): str(photo)})
            project_service.save(project, loaded)
            rendered.unlink()
            self.assertEqual(project_service.still_images(project_service.load(project))[str(rendered)], str(photo))
