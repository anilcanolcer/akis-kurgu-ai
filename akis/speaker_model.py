"""Voice prints from a small speaker-recognition model, so similar voices (two men) can be told apart.

The model is WeSpeaker's ResNet34 trained on VoxCeleb (26.5 MB ONNX, CC BY 4.0; see THIRD_PARTY_NOTICES.txt).
It is downloaded once, on first use, into the per-user data folder and checked against its SHA-256 before
it is ever loaded; onnxruntime (already installed with local speech recognition) runs it. Without it,
akis.speakers falls back to telling voices apart by pitch.

Input: 80 log mel filterbank values per 10 ms (Kaldi's fbank: 25 ms Hamming frames, pre-emphasis 0.97, DC
removed, 512-point FFT, 20 Hz to Nyquist), mean removed over the utterance. Output: a 256-number voice
print; two prints of the same voice point the same way (cosine similarity).
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

import numpy as np

URL = 'https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/voxceleb_resnet34_LM.onnx?download=true'
FILE_NAME = 'voxceleb_resnet34_LM.onnx'
SHA256 = '7bb2f06e9df17cdf1ef14ee8a15ab08ed28e8d0ef5054ee135741560df2ec068'
SIZE_MB = 26.5
RATE = 16000


def path_in(folder):
    return Path(folder) / 'models' / FILE_NAME


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def available(folder):
    """The model file is there and is the expected one."""
    path = path_in(folder)
    return path.is_file() and _sha256(path) == SHA256


def download(folder, opener=urllib.request.urlopen, on_progress=None):
    """Fetch the model into `folder`/models; returns its path. A wrong or partial download is deleted and
    raises, never left where it could be loaded."""
    target = path_in(folder)
    if available(folder):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix('.part')
    digest, got = hashlib.sha256(), 0
    try:
        with opener(URL, timeout=60) as response, open(partial, 'wb') as out:
            total = int(response.headers.get('Content-Length') or 0)
            for block in iter(lambda: response.read(1 << 16), b''):
                out.write(block)
                digest.update(block)
                got += len(block)
                if on_progress and total:
                    on_progress(got / total)
        if digest.hexdigest() != SHA256:
            raise RuntimeError('İndirilen konuşmacı modeli doğrulanamadı (SHA-256 uyuşmuyor).')
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def _mel_bank(bins=80, fft=512, rate=RATE, low=20.0):
    """Kaldi's triangular mel filters over the first fft/2 FFT bins (the Nyquist bin gets no weight)."""
    mel = lambda f: 1127.0 * np.log(1.0 + f / 700.0)
    high = rate / 2
    lo, hi = mel(low), mel(high)
    step = (hi - lo) / (bins + 1)
    freqs = np.arange(fft // 2) * rate / fft
    m = mel(freqs)
    bank = np.zeros((bins, fft // 2 + 1), dtype=np.float32)
    for b in range(bins):
        left, centre, right = lo + b * step, lo + (b + 1) * step, lo + (b + 2) * step
        up = (m - left) / (centre - left)
        down = (right - m) / (right - centre)
        bank[b, :fft // 2] = np.maximum(0.0, np.minimum(up, down))
    return bank


_BANK = _mel_bank()


def fbank(samples):
    """[frames, 80] log mel features of 16 kHz float samples (-1..1), mean removed."""
    wave = samples.astype(np.float64) * 32768.0
    frame, hop = 400, 160
    if len(wave) < frame:
        return np.zeros((0, 80), dtype=np.float32)
    count = 1 + (len(wave) - frame) // hop
    frames = np.lib.stride_tricks.as_strided(wave, (count, frame), (wave.strides[0] * hop, wave.strides[0])).copy()
    frames -= frames.mean(axis=1, keepdims=True)
    frames[:, 1:] -= 0.97 * frames[:, :-1]
    frames[:, 0] -= 0.97 * frames[:, 0]
    frames *= 0.54 - 0.46 * np.cos(2 * np.pi * np.arange(frame) / (frame - 1))      # Kaldi's Hamming window
    power = np.abs(np.fft.rfft(frames, 512)) ** 2
    feats = np.log(np.maximum(power @ _BANK.T, np.finfo(np.float32).eps)).astype(np.float32)
    return feats - feats.mean(axis=0, keepdims=True)


class Embedder:
    """Loads the model once; `print_of(samples)` gives a unit-length voice print."""

    def __init__(self, path):
        import onnxruntime
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
        self.session = onnxruntime.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])

    def print_of(self, samples):
        feats = fbank(samples)
        if len(feats) < 50:          # under half a second of speech says little about the voice
            return None
        vector = self.session.run(['embs'], {'feats': feats[None, :, :]})[0][0]
        return vector / (np.linalg.norm(vector) + 1e-9)
