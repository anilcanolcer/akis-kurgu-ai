import struct
import unittest
from waveform_service import peaks_from_pcm

class WaveformTests(unittest.TestCase):
    def test_peaks_and_trailing_byte(self):
        pcm = struct.pack('<100h', *([0]*50 + [16384]*50)) + b'\x00'
        self.assertEqual(peaks_from_pcm(pcm), [0.0, 0.5])
    def test_empty(self):
        self.assertEqual(peaks_from_pcm(b''), [])

if __name__ == '__main__': unittest.main()
