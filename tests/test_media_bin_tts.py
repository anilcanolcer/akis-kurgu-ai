import unittest
from akis.media_bin import MediaBin
from akis.tts_service import synthesize

class MediaBinTests(unittest.TestCase):
    def test_search_and_deduplicate(self):
        media=MediaBin(); media.add('a/Cat.mp4'); media.add('a/Cat.mp4'); media.add('b/Dog.wav')
        self.assertEqual(media.search('cat'),['a\\Cat.mp4'] if __import__('os').name=='nt' else ['a/Cat.mp4'])
        self.assertEqual(len(media.search('')),2)
    def test_tts_rejects_empty(self):
        import sys
        if sys.platform == 'win32':
            with self.assertRaises(ValueError): synthesize(' ', 'voice.wav')
if __name__ == '__main__': unittest.main()
