"""Fast export only for codecs MP4 can carry, FFmpeg lists that survive a quote in the temp folder, and
FCPXML assets that describe sound files as sound."""
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from akis import fast_export, fcpxml_export
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer, concat_entry

FFMPEG = shutil.which('ffmpeg')
FONT = Path(r'C:\Windows\Fonts\arial.ttf')


def ff(*args):
    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', *args], check=True)


def cut_timeline(path, seconds, cut=30):
    """One video track: the start and the end of `path`, the part in between cut out."""
    frames = round(seconds * 30)
    return Timeline(tracks=[Track('video', 'Video', [
        Clip(str(path), 0, cut, source_length=frames),
        Clip(str(path), cut, frames - 2 * cut, source_in=2 * cut, source_length=frames)])])


class ConcatEntryTests(unittest.TestCase):
    def test_a_single_quote_is_escaped_the_way_ffmpeg_reads_it(self):
        self.assertEqual(concat_entry(r"C:\Users\Ali'nin\a.mp4"), r"file 'C:/Users/Ali'\''nin/a.mp4'")
        self.assertEqual(concat_entry('C:/x y/b.png'), "file 'C:/x y/b.png'")


@unittest.skipUnless(FFMPEG, 'ffmpeg gerekli')
class MediaFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = cls.root = Path(cls.tmp.name)
        ff('-f', 'lavfi', '-i', 'sine=d=1', '-ac', '1', str(root / 'mono.wav'))
        ff('-f', 'lavfi', '-i', 'sine=d=1', '-ac', '2', str(root / 'stereo.wav'))
        ff('-f', 'lavfi', '-i', 'sine=d=1', '-ac', '6', str(root / 'surround.wav'))
        ff('-f', 'lavfi', '-i', 'color=c=red:size=64x64:d=1', '-frames:v', '1', str(root / 'cover.png'))
        ff('-f', 'lavfi', '-i', 'sine=d=1', '-i', str(root / 'cover.png'), '-map', '0:a', '-map', '1:v',
           '-c:a', 'libmp3lame', '-c:v', 'png', '-disposition:v', 'attached_pic', str(root / 'kapakli.mp3'))
        ff('-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=4', '-f', 'lavfi', '-i', 'sine=d=4',
           '-c:v', 'prores_ks', '-profile:v', '0', '-c:a', 'pcm_s16le', '-shortest', str(root / 'kamera.mov'))
        ff('-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=4', '-f', 'lavfi', '-i', 'sine=d=4',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', '-shortest', str(root / 'h264_pcm.mov'))
        ff('-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=4', '-f', 'lavfi', '-i', 'sine=d=4', '-ac', '2',
           '-c:v', 'libx264', '-g', '30', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest',  # a keyframe a second
           str(root / 'telefon.mov'))
        cls.media = MediaService(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_streams_channels_and_cover_art(self):
        m, root = self.media, self.root
        self.assertEqual([m.audio_channels(root / n) for n in ('mono.wav', 'stereo.wav', 'surround.wav')], [1, 2, 6])
        self.assertFalse(m.has_video(root / 'mono.wav'))
        self.assertFalse(m.has_video(root / 'kapakli.mp3'))          # an album cover is not a video
        self.assertTrue(m.has_video(root / 'kamera.mov'))
        self.assertEqual([(k, c) for k, c, _ in m.streams(root / 'kamera.mov')], [('video', 'prores'), ('audio', 'pcm_s16le')])
        self.assertEqual(m.audio_channels(root / 'telefon.mov'), 2)

    def test_fast_export_is_offered_only_for_codecs_mp4_can_carry(self):
        m, root = self.media, self.root
        for name, offered in (('kamera.mov', False), ('h264_pcm.mov', False), ('telefon.mov', True)):
            pieces = fast_export.plan(cut_timeline(root / name, 4), {}, (320, 240), m)
            self.assertEqual(bool(pieces), offered, name)

    def test_fast_export_works_in_a_temp_folder_with_a_quote(self):
        quoted = self.root / "Ali'nin geçici"
        quoted.mkdir(exist_ok=True)
        pieces = fast_export.plan(cut_timeline(self.root / 'telefon.mov', 4), {}, (320, 240), self.media)
        out = self.root / 'hizli.mp4'
        with patch.object(tempfile, 'tempdir', str(quoted)):
            fast_export.export(pieces, out, self.media)
        self.assertAlmostEqual(self.media.duration(out), 3.0, delta=0.3)   # 0–1 s and 2–4 s of the source

    def test_source_does_not_inherit_an_unrelated_sequence_format(self):
        timeline = Timeline(fps_num=25, tracks=[
            Track('video', 'Video', [Clip(str(self.root / 'telefon.mov'), 0, 25)])])
        text, _ = fcpxml_export.build(timeline, (1080, 1920), self.media)
        root = ET.fromstring(text)
        asset = root.find('resources/asset')
        fmt = root.find(f"resources/format[@id='{asset.get('format')}']")
        self.assertEqual((fmt.get('width'), fmt.get('height'), fmt.get('frameDuration')), ('320', '240', '1/30s'))
        self.assertEqual(asset.find('media-rep').get('src'), (self.root / 'telefon.mov').resolve().as_uri())

    def test_fcpxml_describes_sound_files_as_sound(self):
        m, root = self.media, self.root
        timeline = Timeline(tracks=[
            Track('video', 'Video', [Clip(str(root / 'telefon.mov'), 0, 120, source_length=120)]),
            Track('audio', 'Audio', [Clip(str(root / 'mono.wav'), 0, 30, source_length=30),
                                     Clip(str(root / 'kapakli.mp3'), 30, 30, source_length=30)])])
        text, _ = fcpxml_export.build(timeline, (320, 240), m)
        assets = {a.get('name'): a for a in ET.fromstring(text.split('\n', 2)[2]).iter('asset')}
        wav, mp3, video = assets['mono.wav'], assets['kapakli.mp3'], assets['telefon.mov']
        self.assertEqual((wav.get('hasVideo'), wav.get('hasAudio'), wav.get('audioChannels')), ('0', '1', '1'))
        self.assertIsNone(wav.get('format'))                         # no picture format for a sound file
        self.assertEqual(mp3.get('hasVideo'), '0')
        self.assertEqual((video.get('hasVideo'), video.get('format'), video.get('audioChannels')), ('1', 'r1', '2'))


@unittest.skipUnless(FFMPEG and FONT.is_file(), 'ffmpeg ve Arial gerekli')
class QuotedTempRenderTests(unittest.TestCase):
    def test_word_captions_export_in_a_temp_folder_with_a_quote(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        quoted = Path(tmp.name) / "Ayşe'nin"
        quoted.mkdir()
        clips = [Clip('', 0, 20, text='Bir iki', style={'words': [[0, 10, 'Bir'], [10, 20, 'iki']], 'look': 'vurgu'})]
        timeline = Timeline(fps_num=10, tracks=[Track('text', 'Altyazı / Captions', clips)])
        media = MediaService(FFMPEG)
        with patch.object(tempfile, 'tempdir', str(quoted)):
            TimelineRenderer(media, (320, 180), font=str(FONT)).export(timeline, Path(tmp.name) / 'out.mp4')
        self.assertAlmostEqual(media.duration(Path(tmp.name) / 'out.mp4'), 2.0, delta=0.15)


if __name__ == '__main__':
    unittest.main()
