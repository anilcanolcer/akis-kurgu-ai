"""Turn a whole video into a run of vertical Shorts: every second used, in order, nothing left out.

The edit is divided into parts of about equal length, each at most `limit` seconds. A part ends in a pause
near its planned end where there is one, so sentences are not cut in the middle. Each part is the
timeline's own content between two moments (every track: captions, music, texts follow), shifted to start
at 0, on a vertical canvas. By default a landscape picture sits whole over a blurred, enlarged copy of
itself, and a card at the top shows "4 / 7" and the part's title for the whole part; files are named
"04-title-as-slug.mp4" in one folder.
"""
import math
import re

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from akis import clip_fit, silence_cut
from akis.media_service import MediaService, RenderCancelled
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer, duration_frames, output_overwrites_source
from akis.timeline_slice import slice_timeline

DEFAULT_LIMIT = 60
MIN_LIMIT, MAX_LIMIT = 15, 180
CANVAS = (1080, 1920)
SEARCH = 0.15          # look for a pause within this share of the planned length before the planned end
LABEL_TRACK = 'Shorts bölüm'
TITLE_CHARS = 48
SLUG_CHARS = 40
FRAMINGS = (clip_fit.BLUR, clip_fit.FILL, clip_fit.FIT)


def plan_parts(total, limit, pauses=()):
    """[(start, end)] in seconds covering 0..total with no gap, each at most `limit` long.

    pauses: seconds (on the timeline) where a cut would fall between words."""
    if total <= 0:
        return []
    limit = max(1.0, float(limit))
    count = max(1, math.ceil(total / limit - 1e-9))
    pauses = sorted(p for p in pauses if 0 < p < total)
    parts, cursor = [], 0.0
    for index in range(count - 1):
        remaining = count - index
        target = cursor + (total - cursor) / remaining
        latest = min(cursor + limit, total - (remaining - 1) * 1.0)
        # The rest must still fit in the parts left, each at most `limit` long.
        earliest = max(cursor + 1.0, total - (remaining - 1) * limit)
        window = [p for p in pauses if max(earliest, target - SEARCH * limit) <= p <= min(latest, target + SEARCH * limit)]
        end = min(window, key=lambda p: abs(p - target)) if window else min(max(target, earliest), latest)
        parts.append((cursor, end))
        cursor = end
    parts.append((cursor, total))
    return parts


def timeline_pauses(timeline, levels_for):
    """Pause midpoints in timeline seconds, from the main video's own sound.

    levels_for(source) -> loudness curve (akis.silence_cut.measure); read once per source file."""
    fps = timeline.fps_num / timeline.fps_den
    main = next((track for track in timeline.tracks if track.kind == 'video'), None)
    found, cache = [], {}
    for clip in main.clips if main else ():
        if not clip.source:
            continue
        if clip.source not in cache:
            cache[clip.source] = silence_cut.silent_spans(levels_for(clip.source), min_silence=0.25)
        first, last = clip.source_in / fps, clip.source_end / fps
        for a, b in cache[clip.source]:
            middle = (a + b) / 2
            if first <= middle < last:
                found.append(clip.start / fps + (middle - first) / clip.speed)
    return sorted(found)


def prepare(part, number, count, *, framing=clip_fit.BLUR, card=True, title=''):
    """Make a sliced part ready for a vertical export: frame the picture, add the "4 / 7" + title card.

    framing: clip_fit.BLUR, FILL or FIT; clips the user framed by hand keep their own framing."""
    if framing in (clip_fit.BLUR, clip_fit.FILL):
        for track in part.tracks:
            if track.kind in ('video', 'overlay'):
                for clip in track.clips:
                    if 'fit' not in clip.style:
                        clip_fit.apply(clip, framing, 0.5)
    title = ' '.join(str(title or '').split())
    if card and (count > 1 or title):
        length = duration_frames(part)
        if length > 0:
            counter = f'{number} / {count}' if count > 1 else ''
            part.tracks.append(Track('text', LABEL_TRACK, [Clip('', 0, length, text=title or counter,
                                                                style={'shape': 'card', 'counter': counter, 'title': title,
                                                                       'y': 0.05})]))
    return part


def slug(text):
    """A file-name-safe, ASCII form of a title: "Dağ o ayetten beri ağlıyor" -> "dag-o-ayetten-beri-agliyor"."""
    text = str(text).translate(str.maketrans('çğıöşüÇĞİÖŞÜâîûÂÎÛ', 'cgiosuCGIOSUaiuAIU')).lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:SLUG_CHARS].rstrip('-')


def outputs_for(folder, titles, fallback):
    """One path per part: "01-title.mp4" in `folder` (the fallback name where a part has no title)."""
    width = max(2, len(str(len(titles))))
    names, used = [], set()
    for number, title in enumerate(titles, 1):
        name = f'{number:0{width}d}-{slug(title) or slug(fallback) or "short"}.mp4'
        while name.lower() in used:
            name = name[:-4] + '-2.mp4'
        used.add(name.lower())
        names.append(str(Path(folder) / name))
    return names


def suggest_titles(parts, said):
    """A starting title per part: the first sentence said in it, shortened; '' where nothing is said.

    said: [(timeline second, text)] (see spoken_on_timeline)."""
    titles = []
    for start, end in parts:
        first = next((text for second, text in said if start <= second < end and text.strip()), '')
        first = ' '.join(first.split()).rstrip('.,;:')
        if len(first) > TITLE_CHARS:
            first = first[:TITLE_CHARS].rsplit(' ', 1)[0].rstrip('.,;:') + '…'
        titles.append(first)
    return titles


def spoken_on_timeline(timeline, source, segments):
    """[(timeline second, text)] for a transcript of `source` (seconds in the source) as the edit shows it."""
    fps = timeline.fps_num / timeline.fps_den
    main = next((track for track in timeline.tracks if track.kind == 'video'), None)
    found = []
    for clip in main.clips if main else ():
        if clip.source != source:
            continue
        first, last = clip.source_in / fps, clip.source_end / fps
        for segment in segments:
            start = float(segment.get('start', 0))
            if first <= start < last:
                found.append((clip.start / fps + (start - first) / clip.speed, str(segment.get('text', ''))))
    return sorted(found)


def clock(seconds):
    seconds = max(0, round(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


class ShortsExportWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)

    def __init__(self, timeline, parts, outputs, executable, *, adjustments=None, framing=clip_fit.BLUR, card=True,
                 titles=None, say=str, canvas=CANVAS, numbered=True):
        super().__init__()
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.parts = list(parts)
        self.outputs = list(outputs)
        self.titles = list(titles or [''] * len(self.parts))
        self.adjustments = dict(adjustments or {})
        self.framing, self.card, self.say = framing, card, say
        self.canvas = canvas
        self.numbered = numbered   # "4 / 7" on the card; off for parts that are not a series
        self.media = MediaService(executable)
        self._percent = None

    def cancel(self):
        self.media.cancel()

    def _report(self, index, fraction):
        percent = int((index + fraction) / len(self.parts) * 100)
        if percent != self._percent:
            self._percent = percent
            self.progress.emit(percent)

    def run(self):
        try:
            fps = self.timeline.fps_num / self.timeline.fps_den
            for index, ((start, end), output) in enumerate(zip(self.parts, self.outputs)):
                part = slice_timeline(self.timeline, round(start * fps), round(end * fps))
                prepare(part, index + 1, len(self.parts) if self.numbered else 1, framing=self.framing, card=self.card,
                        title=self.titles[index])
                if output_overwrites_source(part, output):
                    raise ValueError(self.say('Çıktı dosyası kaynak medyayla aynı olamaz.'))
                renderer = TimelineRenderer(self.media, self.canvas, **self.adjustments)
                renderer.export(part, output, on_progress=lambda f, index=index: self._report(index, f))
            self.completed.emit('\n'.join(self.outputs))
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.media.cancelled:
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
