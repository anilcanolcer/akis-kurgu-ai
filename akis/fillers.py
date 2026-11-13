"""Find filler words ("ııı", "eee", "hmm", and "şey"/"yani"/"işte"/"hani" used as a pause) to cut.

Whisper normally leaves hesitations out of a transcript, so these are found by a separate local recognition
run whose prompt is itself full of fillers ("Iıı, eee, şey…"): with that example Whisper writes them down
too, with each word's timing. That run is used only for this; captions keep their clean transcript.

Hesitations are always fillers. "şey", "yani", "işte", "hani" are ordinary words as well ("bir şey", "yani
şu"), so they count only when the speaker stops right after them (PAUSE), and not after "bir"/"her"/
"hiçbir" ("bir şey"). Each cut stays clear of the neighbouring words.
"""
import re

PROMPT = 'Iıı, eee, şey, hmm. Yani, ıı, işte, eee, şey…'
HESITATION = re.compile(r'^(?:ı+|i{2,}|e+h?|a{2,}h?|o{2,}|ö+|u{2,}|ü{2,}|e?h+m+|h[ıiu]m+|m{2,}|ı+h|ee+m|\w?m{3,})$')   # 'tmmm': Whisper's spelling of a long hmm
SPOKEN = {'şey', 'yani', 'işte', 'hani'}
NOT_AFTER = {'bir', 'her', 'hiçbir', 'o', 'bu', 'şu', 'öyle', 'böyle'}   # "bir şey", "o şey" mean something
PAUSE = 0.25           # seconds of quiet around a spoken filler
EDGE = 0.04            # cut a little around the filler, never into a neighbouring word
MIN_CUT = 0.12         # shorter cuts are not worth the jump


def normal(text):
    text = str(text).strip().replace('İ', 'i').replace('I', 'ı').lower()
    return re.sub(r'[^\wçğıöşü]', '', text)


def _timed(words):
    found = []
    for word in words or ():
        try:
            text, start = str(word['text']).strip(), float(word['start'])
            end = max(start, float(word.get('end', start)))
        except (KeyError, TypeError, ValueError):
            continue
        if text:
            found.append((start, end, text))
    return sorted(found)


def find(words):
    """[(cut start, cut end, word)] in source seconds, in order and not overlapping."""
    items = _timed(words)
    cuts = []
    for index, (start, end, text) in enumerate(items):
        word = normal(text)
        if not word:
            continue
        before = items[index - 1] if index else None
        after = items[index + 1] if index + 1 < len(items) else None
        if HESITATION.match(word):
            pass
        elif word in SPOKEN:
            # Used as a pause only when the speaker stops after it ("şey… bilgisayar"); "İşte şu ayet"
            # runs straight on and keeps its meaning.
            # A comma or an ellipsis Whisper put after it is a pause too.
            quiet_after = after is not None and (after[0] - end >= PAUSE or text.rstrip()[-1:] in ',…' or text.endswith('...'))
            if not quiet_after or (before and normal(before[2]) in NOT_AFTER):
                continue
        else:
            continue
        left = max(before[1] if before else 0.0, start - EDGE)
        right = min(after[0] if after else end + EDGE, end + EDGE)
        if right - left < MIN_CUT:
            continue
        if cuts and left <= cuts[-1][1]:
            cuts[-1] = (cuts[-1][0], max(cuts[-1][1], right), cuts[-1][2] + ' ' + text)
        else:
            cuts.append((left, right, text))
    return cuts


def words_of(segments):
    return [w for segment in segments or () if isinstance(segment, dict) for w in (segment.get('words') or ())]


def summary(cuts, say=str):
    """The confirmation question: how many, which words, how much time."""
    counts = {}
    for _, _, text in cuts:
        for word in text.split():
            key = normal(word)
            key = 'ııı / eee' if HESITATION.match(key) else key
            counts[key] = counts.get(key, 0) + 1
    seconds = sum(b - a for a, b, _ in cuts)
    listed = ', '.join(f'{word} ×{count}' for word, count in sorted(counts.items(), key=lambda kv: -kv[1]))
    return '\n'.join([say('{count} dolgu sözcüğü bulundu (toplam {seconds} sn):').format(
                          count=len(cuts), seconds=f'{seconds:.1f}'.replace('.', ',')),
                      listed, '', say('Kesilsin mi? Beğenmezseniz tek adımda geri alabilirsiniz.')])
