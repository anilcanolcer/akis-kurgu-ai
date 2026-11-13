"""Find retakes in a transcript: a sentence said again a moment later, so only the last try is kept.

Works on the timed transcript the local speech recogniser makes ([{'start', 'end', 'text'}], seconds in
the source). Two kinds are found:
  - the same sentence said twice (or three times) in a row, worded nearly the same;
  - a false start: a few words that the next sentence begins with again ("Bugün size… Bugün size yeni…").
For each, the earlier try and anything between it and the next try is cut; the last try stays.
"""
import re
from difflib import SequenceMatcher

LOOK_AHEAD = 3          # a retake comes within the next few sentences
MAX_GAP = 20.0          # seconds from the end of one try to the start of the next
SIMILAR = 0.72          # share of words that must match for "the same sentence again"
MIN_WORDS = 3           # shorter bits ("evet", "tamam") repeat naturally and are left alone
STEM = 3                # letters of each word compared, so a different ending is still the same word


def words(text):
    """Lower-case words without punctuation; Turkish dotted and dotless i treated alike."""
    text = str(text).replace('İ', 'i').replace('I', 'i').replace('ı', 'i').lower()
    return re.findall(r'\w+', text)


def _is_retake(first, second):
    a, b = words(first), words(second)
    if len(a) < MIN_WORDS or len(b) < MIN_WORDS:
        return False
    if b[:len(a)] == a or (len(a) < len(b) and SequenceMatcher(None, a, b[:len(a)]).ratio() >= 0.85):
        return True                                     # a false start the next sentence repeats
    # Turkish endings change between tries (size / sizlere): compare the start of each word.
    return SequenceMatcher(None, [w[:STEM] for w in a], [w[:STEM] for w in b]).ratio() >= SIMILAR


def find(segments):
    """[(cut start, cut end, removed text, kept text)] in source seconds, in order, never overlapping."""
    items = sorted((float(s['start']), float(s['end']), str(s['text']).strip()) for s in segments
                   if str(s.get('text', '')).strip() and float(s['end']) > float(s['start']))
    found, index = [], 0
    while index < len(items):
        start, end, text = items[index]
        later = None
        for other in range(index + 1, min(len(items), index + 1 + LOOK_AHEAD)):
            if items[other][0] - end > MAX_GAP:
                break
            if _is_retake(text, items[other][2]):
                later = other
                break
        if later is None:
            index += 1
            continue
        found.append((start, items[later][0], text, items[later][2]))
        index = later           # the later try may itself be tried again
    merged = []
    for cut in found:
        if merged and cut[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], cut[1]), merged[-1][2], cut[3])
        else:
            merged.append(cut)
    return merged


def summary(cuts, say=str, limit=6):
    """The confirmation question: what goes and what stays, for the first few."""
    lines = [say('{count} tekrar çekim bulundu; her birinin yalnızca son denemesi kalacak:').format(count=len(cuts)), '']
    for _, _, removed, kept in cuts[:limit]:
        lines.append(f'✕ {_short(removed)}')
        lines.append(f'✓ {_short(kept)}')
    if len(cuts) > limit:
        lines.append(say('… ve {count} tane daha.').format(count=len(cuts) - limit))
    lines += ['', say('Kesilsin mi? Beğenmezseniz tek adımda geri alabilirsiniz.')]
    return '\n'.join(lines)


def _short(text, limit=70):
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'
