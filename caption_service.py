"""Timed caption and timeline snapping operations."""
import math
from timeline_model import Clip, Track


def caption_track(timeline, source, segments):
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
                left = max(clip.source_in, round(start * fps))
                right = min(clip.source_in + clip.length, round(end * fps))
                if right > left:
                    spans.append((clip.start + left - clip.source_in, clip.start + right - clip.source_in, text))
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
