"""Turn a whole video into a run of vertical Shorts: every second used, in order, nothing left out.

The edit is divided into parts of about equal length, each at most `limit` seconds. A part ends in a pause
near its planned end where there is one, so sentences are not cut in the middle. Each part is the
timeline's own content between two moments (every track: captions, music, texts follow), shifted to start
at 0, on a vertical canvas, optionally with the picture filling the frame and a "Bölüm 1/7" label.
"""
import math
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from akis import clip_fit, silence_cut
from akis.media_service import MediaService, RenderCancelled
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer, duration_frames, output_overwrites_source

DEFAULT_LIMIT = 60
MIN_LIMIT, MAX_LIMIT = 15, 180
CANVAS = (1080, 1920)
SEARCH = 0.15          # look for a pause within this share of the planned length before the planned end
LABEL_SECONDS = 3
LABEL_TRACK = 'Shorts bölüm'


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
        first, last = clip.source_in / fps, (clip.source_in + clip.length) / fps
        for a, b in cache[clip.source]:
            middle = (a + b) / 2
            if first <= middle < last:
                found.append(clip.start / fps + middle - first)
    return sorted(found)


def slice_timeline(timeline, start, end):
    """A new timeline with what lies between frames `start` and `end`, moved to begin at 0."""
    part = Timeline(fps_num=timeline.fps_num, fps_den=timeline.fps_den)
    for track in timeline.tracks:
        kept = Track(track.kind, track.name, muted=track.muted)
        for clip in track.clips:
            a, b = max(clip.start, start), min(clip.end, end)
            if b <= a:
                continue
            piece = deepcopy(clip)
            offset = a - clip.start
            piece.start, piece.length = a - start, b - a
            if piece.source:
                piece.source_in = clip.source_in + offset
            if offset and piece.keyframes:
                piece.keyframes = {k: [dict(p, frame=p['frame'] - offset) for p in v if p['frame'] >= offset]
                                   for k, v in piece.keyframes.items()}
            if offset:  # the clip's own entrance belongs to its real start, not to this cut
                piece.style = {k: v for k, v in piece.style.items() if not k.startswith('transition')}
            kept.clips.append(piece)
        part.tracks.append(kept)
    part.markers = [dict(m, frame=m['frame'] - start) for m in timeline.markers if start <= m.get('frame', 0) < end]
    return part


def prepare(part, number, count, *, fill=True, label=True, say=str):
    """Make a sliced part ready for a vertical export: fill the frame, add the part label."""
    if fill:
        for track in part.tracks:
            if track.kind in ('video', 'overlay'):
                for clip in track.clips:
                    if not clip_fit.is_fill(clip.style):
                        clip_fit.apply(clip, clip_fit.FILL, 0.5)
    if label and count > 1:
        fps = part.fps_num / part.fps_den
        length = min(duration_frames(part), round(LABEL_SECONDS * fps))
        if length > 0:
            text = say('Bölüm {number}/{count}').format(number=number, count=count)
            part.tracks.append(Track('text', LABEL_TRACK, [Clip('', 0, length, text=text,
                                                                style={'x': 0.5, 'y': 0.1, 'size': 'medium', 'color': 'yellow'})]))
    return part


def output_for(chosen, number, count):
    base = Path(chosen)
    stem = base.stem if base.suffix.lower() == '.mp4' else base.name
    width = max(2, len(str(count)))
    return str(base.with_name(f'{stem}_short_{number:0{width}d}.mp4'))


def clock(seconds):
    seconds = max(0, round(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


class ShortsExportWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)

    def __init__(self, timeline, parts, chosen, executable, *, adjustments=None, fill=True, label=True, say=str,
                 canvas=CANVAS):
        super().__init__()
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.parts = list(parts)
        self.outputs = [output_for(chosen, n + 1, len(self.parts)) for n in range(len(self.parts))]
        self.adjustments = dict(adjustments or {})
        self.fill, self.label, self.say = fill, label, say
        self.canvas = canvas
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
                prepare(part, index + 1, len(self.parts), fill=self.fill, label=self.label, say=self.say)
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
