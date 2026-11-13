"""Who speaks when: group the utterances of a recording by voice, without an AI service or a model download.

With the speaker model (akis.speaker_model, downloaded once) each utterance gets a voice print and similar
prints are grouped: this tells apart even similar voices (two men). Without the model it falls back to pitch:

For each utterance (a run of words between pauses, from the local transcript's word timings) the typical
pitch of the voice is measured, and the utterances are split into two voices only when their pitches fall
into two clearly separate groups (GAP semitones apart): a man and a woman, an adult and a child. Measured
on real recordings, spectrum shape (MFCC) varied as much within one speaker as between two, so it is not
used to decide. Two similar voices (two men) stay one speaker: one speaker is the safe answer, a recording
is never split into voices that are not clearly there.
"""
from __future__ import annotations

import numpy as np

RATE = 16000
PAUSE = 0.45            # a pause this long ends an utterance
MIN_UTTERANCE = 0.8     # shorter utterances get their speaker from their neighbours
SAME = 0.32             # model voice prints: average cosine similarity above which two groups are one voice
GAP = 5.0               # semitones between two voices' typical pitch before they count as two
MIN_SHARE = 0.06        # a "speaker" with less of the talking than this is folded into the nearest one


def decode(media, path):
    """The recording as 16 kHz mono float samples (ffmpeg)."""
    result = media.run(['-v', 'error', '-i', str(path), '-map', '0:a:0', '-ac', '1', '-ar', str(RATE),
                        '-f', 'f32le', '-'], text=False)
    if result.returncode or not result.stdout:
        raise RuntimeError('Ses okunamadı.')
    return np.frombuffer(result.stdout, dtype=np.float32)


def utterances(words, pause=PAUSE):
    """[(start, end, text)] seconds: words joined until a pause."""
    items = []
    for word in words or ():
        try:
            items.append((float(word['start']), float(word['end']), str(word['text']).strip()))
        except (KeyError, TypeError, ValueError):
            continue
    items.sort()
    result = []
    for start, end, text in items:
        if result and start - result[-1][1] < pause:
            a, _, t = result[-1]
            result[-1] = (a, max(end, result[-1][1]), (t + ' ' + text).strip())
        else:
            result.append((start, end, text))
    return result


def _mel_bank(bins, filters=26, rate=RATE):
    top = 2595 * np.log10(1 + (rate / 2) / 700)
    points = 700 * (10 ** (np.linspace(0, top, filters + 2) / 2595) - 1)
    index = np.floor((bins - 1) * 2 * points / rate).astype(int)
    bank = np.zeros((filters, bins))
    for i in range(1, filters + 1):
        a, b, c = index[i - 1], index[i], index[i + 1]
        if b > a:
            bank[i - 1, a:b] = (np.arange(a, b) - a) / (b - a)
        if c > b:
            bank[i - 1, b:c] = (c - np.arange(b, c)) / (c - b)
    return bank


_BANK = _mel_bank(257)
_DCT = np.cos(np.pi / 26 * (np.arange(26)[None, :] + 0.5) * np.arange(1, 14)[:, None])   # MFCC 1-13


def voice_print(samples):
    """A vector for a stretch of speech: MFCC means and spreads, and the median pitch (log)."""
    frame, hop = 400, 160
    if len(samples) < frame * 4:
        return None
    count = 1 + (len(samples) - frame) // hop
    frames = np.lib.stride_tricks.as_strided(samples, (count, frame), (samples.strides[0] * hop, samples.strides[0]))
    energy = (frames ** 2).mean(axis=1)
    voiced = frames[energy > max(1e-7, np.percentile(energy, 40))]
    if len(voiced) < 10:
        return None
    window = voiced * np.hamming(frame)
    power = np.abs(np.fft.rfft(window, 512)) ** 2
    mfcc = np.log(power @ _BANK.T + 1e-10) @ _DCT.T
    pitch = []
    for block in voiced[:: max(1, len(voiced) // 40)]:
        lagged = np.correlate(block, block, 'full')[frame - 1:]
        low, high = RATE // 400, RATE // 70           # 70-400 Hz
        peak = low + int(np.argmax(lagged[low:high]))
        if lagged[0] > 0 and lagged[peak] > 0.3 * lagged[0]:
            pitch.append(RATE / peak)
    pitch_value = np.log(np.median(pitch)) if pitch else np.log(150.0)
    return np.concatenate([mfcc.mean(axis=0), mfcc.std(axis=0), [pitch_value * 4]])


def _pitch_semitones(vector):
    return float(vector[-1] / 4 / np.log(2) * 12)          # log pitch -> semitones


def cluster(prints, weights, gap=GAP, min_share=MIN_SHARE):
    """A speaker number (0 = who speaks first, 1 = the other) for each print.

    Two voices are told apart only by a clear difference in pitch: the utterances' pitches are split into
    a lower and a higher group (two-means), and the split is kept when the groups are at least `gap`
    semitones apart and each holds at least `min_share` of the talking. Otherwise everything is one
    speaker: one voice's own rises and falls (a few semitones) never make a second speaker.
    """
    if not prints:
        return []
    pitches = np.array([_pitch_semitones(p) for p in prints])
    w = np.array(weights, dtype=float)
    low, high = np.percentile(pitches, 10), np.percentile(pitches, 90)
    for _ in range(20):
        upper = np.abs(pitches - high) < np.abs(pitches - low)
        if upper.all() or not upper.any():
            return [0] * len(prints)
        low, high = np.average(pitches[~upper], weights=w[~upper]), np.average(pitches[upper], weights=w[upper])
    share = w[upper].sum() / w.sum()
    if high - low < gap or min(share, 1 - share) < min_share:
        return [0] * len(prints)
    first = bool(upper[0])
    return [0 if bool(u) == first else 1 for u in upper]


def cluster_model(prints, weights, same=SAME, min_share=MIN_SHARE):
    """Speaker numbers for model voice prints (akis.speaker_model): groups are joined, closest first,
    while their prints point the same way on average (cosine above `same`); measured on real recordings,
    one person's utterances scored 0.37-0.95 and two different people's at most 0.21. A group with less
    than `min_share` of the talking joins the group it is most like."""
    if not prints:
        return []
    matrix = np.array(prints, dtype=float)
    similar = matrix @ matrix.T
    groups = [[i] for i in range(len(prints))]

    def link(a, b):
        return float(similar[np.ix_(a, b)].mean())

    while len(groups) > 1:
        best, pair = None, None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                value = link(groups[i], groups[j])
                if best is None or value > best:
                    best, pair = value, (i, j)
        if best < same:
            break
        i, j = pair
        groups[i] += groups.pop(j)
    total = sum(weights)
    while len(groups) > 1:
        shares = [sum(weights[i] for i in g) / total for g in groups]
        smallest = int(np.argmin(shares))
        if shares[smallest] >= min_share:
            break
        nearest = max((k for k in range(len(groups)) if k != smallest), key=lambda k: link(groups[smallest], groups[k]))
        groups[nearest] += groups.pop(smallest)
    labels = [0] * len(prints)
    for number, group in enumerate(sorted(groups, key=min)):
        for i in group:
            labels[i] = number
    return labels


def find(samples, words, embedder=None):
    """[(start, end, speaker, text)]: the utterances with a speaker number each (0 = who speaks first).
    With `embedder` (akis.speaker_model.Embedder) voices are told apart by the model, else by pitch."""
    spans = utterances(words)
    prints, weights, keep = [], [], []
    for index, (start, end, _) in enumerate(spans):
        if end - start < MIN_UTTERANCE:
            continue
        piece = samples[int(start * RATE):int(end * RATE)]
        vector = embedder.print_of(piece) if embedder is not None else voice_print(piece)
        if vector is not None:
            prints.append(vector)
            weights.append(end - start)
            keep.append(index)
    labels = dict(zip(keep, (cluster_model if embedder is not None else cluster)(prints, weights)))
    result, last = [], 0
    for index, (start, end, text) in enumerate(spans):
        if index in labels:
            last = labels[index]
        else:   # too short to judge: the speaker of the nearest judged neighbour
            later = next((labels[k] for k in range(index + 1, len(spans)) if k in labels), last)
            last = last if result and spans[index][0] - result[-1][1] < 1.0 else later
        result.append((start, end, labels.get(index, last), text))
    return result


def markers(found, clips, fps):
    """[{'frame', 'label'}]: where on the timeline a different speaker starts, through the video clips
    (`clips`: the main track's clips of this recording)."""
    result, last = [], None
    for start, _, speaker, _ in found:
        if speaker == last:
            continue
        last = speaker
        source_frame = round(start * fps)
        clip = next((c for c in clips if c.source_in <= source_frame < c.source_end), None)
        if clip is not None:
            result.append({'frame': round(clip.timeline_frame(source_frame)), 'label': f'Konuşmacı {speaker + 1}'})
    return result


def summary(found):
    """{speaker: (seconds spoken, first words)}"""
    totals = {}
    for start, end, speaker, text in found:
        seconds, sample = totals.get(speaker, (0.0, ''))
        totals[speaker] = (seconds + end - start, sample or text)
    return totals
