"""Pure, immutable description of the layers visible at one timeline frame."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FrameLayer:
    track_index: int
    kind: str
    clip_id: str
    source: str
    source_frame: int
    text: str


def plan_frame(timeline, frame):
    if not isinstance(frame, int) or frame < 0:
        raise ValueError('Frame must be a non-negative integer')
    return tuple(
        FrameLayer(index, track.kind, clip.id, clip.source,
                   clip.source_in + frame - clip.start, clip.text)
        for index, track in enumerate(timeline.tracks) if not track.muted
        for clip in track.clips if clip.start <= frame < clip.end
    )


def plan_segments(timeline):
    """Return half-open spans sharing the same active clips and layer order."""
    boundaries = sorted({point for track in timeline.tracks if not track.muted
                         for clip in track.clips for point in (clip.start, clip.end)})
    return tuple((start, end, plan_frame(timeline, start))
                 for start, end in zip(boundaries, boundaries[1:]) if start < end)


def audio_at(timeline, frame):
    """Select the first explicit audio layer, otherwise a video audio source."""
    active = plan_frame(timeline, frame)
    return next((layer for layer in active if layer.kind == 'audio'), None) or next(
        (layer for layer in active if layer.kind == 'video'), None)
