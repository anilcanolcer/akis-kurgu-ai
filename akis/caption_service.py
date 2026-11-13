"""Timed caption and timeline snapping operations."""
import math
from akis.caption_layout import split_caption
from akis.timeline_model import Clip, Track


def caption_track(timeline, source, segments, look='klasik'):
    """Caption the clips of `source` from its transcript segments (seconds in the source). look: 'klasik'
    (sentence by sentence) or a word-by-word look of akis.word_captions, used when the words have timings."""
    from akis import word_captions
    words = [w for segment in segments if isinstance(segment, dict) for w in (segment.get('words') or ())]
    if look in word_captions.LOOKS and words:
        return _word_track(timeline, source, words, look)
    return _sentence_track(timeline, source, segments)


def _word_track(timeline, source, words, look):
    from akis import word_captions
    fps = timeline.fps_num / timeline.fps_den
    video_track = next((t for t in timeline.tracks if t.kind == 'video'), None)
    track = Track('text', 'Altyazı / Captions')
    for clip in sorted(video_track.clips if video_track else [], key=lambda c: c.start):
        if clip.source != source:
            continue
        for start, length, text, style in word_captions.caption_clips(clip, words, fps, look):
            begin = max(start, max((c.end for c in track.clips), default=0))
            if start + length - begin < 1:
                continue
            shift = begin - start
            style = dict(style, words=[[max(0, a - shift), b - shift, t] for a, b, t in style['words'] if b - shift > 0])
            track.add(Clip('', begin, start + length - begin, text=text, style=style))
    if track.clips:
        timeline.tracks.append(track)
    return len(track.clips)


def _sentence_track(timeline, source, segments):
    """Map source-time segments through every matching video clip, non-destructively."""
    fps = timeline.fps_num / timeline.fps_den
    track = Track('text', 'Altyazı / Captions')
    spans = []
    for video_track in timeline.tracks:
        if video_track.kind != 'video' or video_track.muted:
            continue
        for clip in video_track.clips:
            if clip.source != source:
                continue
            for segment in segments:
                start, end = float(segment['start']), float(segment['end'])
                text = str(segment['text']).strip()
                if not text or not math.isfinite(start) or not math.isfinite(end) or start >= end:
                    continue
                # A long sentence becomes several short captions in a row, not one block of many lines.
                for piece_start, piece_end, piece in split_caption(text, start, end):
                    left = max(clip.source_in, round(piece_start * fps))
                    right = min(clip.source_end, round(piece_end * fps))
                    if right > left:  # placed where the clip shows those source frames, at its own speed
                        spans.append((round(clip.timeline_frame(left)), round(clip.timeline_frame(right)), piece))
    for start, end, text in sorted(spans):
        start = max(start, max((c.end for c in track.clips), default=0))
        if end > start:
            track.add(Clip('', start, end-start, text=text))
    if track.clips:
        timeline.tracks.append(track)
    return len(track.clips)


def snap_frame(timeline, frame, threshold, exclude=None):
    edges = {0}
    for i, track in enumerate(timeline.tracks):
        for clip in track.clips:
            if exclude != (i, clip.id):
                edges.update((clip.start, clip.end))
    edge = min(edges, key=lambda e: (abs(e-frame), e))
    return edge if abs(edge-frame) <= threshold else frame
