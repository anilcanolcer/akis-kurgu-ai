"""The speaker model: features, a checked download, and (when the model is on this computer) real voices."""
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from akis import speaker_model


class FeatureTests(unittest.TestCase):
    def test_fbank_shape_mean_and_where_a_tone_lands(self):
        t = np.arange(16000) / 16000
        feats = speaker_model.fbank((0.3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32))
        self.assertEqual(feats.shape, (98, 80))                     # 1 + (16000 - 400) // 160
        self.assertTrue(np.allclose(feats.mean(axis=0), 0, atol=1e-3))
        raw = np.log(np.maximum((np.abs(np.fft.rfft(np.hamming(400) * np.sin(2 * np.pi * 1000 * t[:400]), 512)) ** 2)
                                @ speaker_model._BANK.T, 1e-9))
        mel = lambda f: 1127 * np.log(1 + f / 700)
        expected = int(round((mel(1000) - mel(20)) / ((mel(8000) - mel(20)) / 81))) - 1
        self.assertLessEqual(abs(int(np.argmax(raw)) - expected), 1)
        self.assertEqual(speaker_model.fbank(np.zeros(100, dtype=np.float32)).shape, (0, 80))

    def test_mel_bank_ignores_the_nyquist_bin_and_covers_the_band(self):
        bank = speaker_model._BANK
        self.assertEqual(bank.shape, (80, 257))
        self.assertTrue(np.all(bank[:, 256] == 0))
        # The lowest filters are narrower than one FFT bin and may catch none, as in Kaldi itself.
        self.assertGreaterEqual(int((bank.max(axis=1) > 0).sum()), 75)
        self.assertTrue(np.all(bank[40:].max(axis=1) > 0.5))


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class DownloadTests(unittest.TestCase):
    def test_a_good_download_is_kept_and_a_bad_one_never_left(self):
        with tempfile.TemporaryDirectory() as folder:
            good = b'model bytes'
            with patch.object(speaker_model, 'SHA256', hashlib.sha256(good).hexdigest()):
                seen = []
                path = speaker_model.download(folder, opener=lambda url, timeout: Response(good), on_progress=seen.append)
                self.assertEqual(path.read_bytes(), good)
                self.assertTrue(speaker_model.available(folder))
                self.assertEqual(seen[-1], 1.0)
                again = speaker_model.download(folder, opener=lambda *a, **k: self.fail('downloaded twice'))
                self.assertEqual(again, path)
            with tempfile.TemporaryDirectory() as other:
                with self.assertRaises(RuntimeError):
                    speaker_model.download(other, opener=lambda url, timeout: Response(b'tampered'))
                self.assertEqual(list(Path(other, 'models').iterdir()), [])
                self.assertFalse(speaker_model.available(other))


MODEL = Path(os.environ.get('LOCALAPPDATA', '')) / 'AkisStudio' / 'Akış Kurgu AI' / 'models' / speaker_model.FILE_NAME


@unittest.skipUnless(MODEL.is_file(), 'konuşmacı modeli bu bilgisayarda yok')
class RealModelTests(unittest.TestCase):
    def test_prints_are_unit_length_and_steady_for_one_signal(self):
        embedder = speaker_model.Embedder(MODEL)
        t = np.arange(3 * 16000) / 16000
        buzz = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in range(1, 10)).astype(np.float32) * 0.1
        a, b = embedder.print_of(buzz[:24000]), embedder.print_of(buzz[24000:])
        self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0, places=4)
        self.assertGreater(float(a @ b), 0.8)
        self.assertIsNone(embedder.print_of(buzz[:4000]))


if __name__ == '__main__':
    unittest.main()
