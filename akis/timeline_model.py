"""Frame-based, non-destructive timeline primitives.

All positions are integer frames. Source paths are references; edits never modify media.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from uuid import uuid4


@dataclass
class Clip:
    source: str
    start: int
    length: int
    source_in: int = 0
    source_length: int | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    text: str = ""
    volume: float = 1.0
    keyframes: dict[str, list[dict]] = field(default_factory=dict)
    # Optional look: text position/size/colour, annotation shape, or the transition into a video clip.
    style: dict = field(default_factory=dict)

    def __post_init__(self):
        if not 0 <= self.volume <= 1:
            raise ValueError("Volume must be between 0 and 1")
        if self.start < 0 or self.source_in < 0 or self.length < 1:
            raise ValueError("Invalid clip range")
        if self.source_length is not None and self.source_in + self.length > self.source_length:
            raise ValueError("Clip exceeds source duration")

    @property
    def end(self):
        return self.start + self.length


@dataclass
class Track:
    kind: str
    name: str
    clips: list[Clip] = field(default_factory=list)
    muted: bool = False

    def __post_init__(self):
        if self.kind not in {"video", "audio", "text", "overlay"}:
            raise ValueError("Invalid track type")
        self.validate()

    def validate(self):
        clips = sorted(self.clips, key=lambda c: c.start)
        if any(c.start < 0 or c.source_in < 0 or c.length < 1 or
               (c.source_length is not None and c.source_in + c.length > c.source_length) for c in clips):
            raise ValueError("Invalid clip range")
        if len({c.id for c in clips}) != len(clips):
            raise ValueError("Duplicate clip id")
        if any(a.end > b.start for a, b in zip(clips, clips[1:])):
            raise ValueError("Clips on the same track overlap")

    def add(self, clip: Clip):
        self.clips.append(clip)
        try:
            self.validate()
        except Exception:
            self.clips.remove(clip)
            raise

    def split(self, clip_id: str, frame: int):
        clip = self.find(clip_id)
        offset = frame - clip.start
        if not 0 < offset < clip.length:
            raise ValueError("Split must be inside clip")
        right = Clip(source=clip.source, start=frame, length=clip.length-offset,
                     source_in=clip.source_in+offset, source_length=clip.source_length,
                     text=clip.text, volume=clip.volume,
                     style={k: v for k, v in clip.style.items() if not k.startswith('transition')})
        for name, points in clip.keyframes.items():
            right.keyframes[name] = [dict(p, frame=p['frame']-offset) for p in points if p['frame'] >= offset]
            clip.keyframes[name] = [p for p in points if p['frame'] < offset]
        clip.length = offset
        self.add(right)
        return right

    def find(self, clip_id: str):
        return next(c for c in self.clips if c.id == clip_id)

    def slip(self, clip_id: str, delta: int):
        clip = self.find(clip_id)
        new_in = clip.source_in + delta
        if new_in < 0 or (clip.source_length is not None and new_in + clip.length > clip.source_length):
            raise ValueError("Slip exceeds source duration")
        clip.source_in = new_in

    def move(self, clip_id: str, start: int):
        clip = self.find(clip_id)
        old = clip.start
        clip.start = start
        try:
            self.validate()
        except ValueError:
            clip.start = old
            raise

    def ripple_delete(self, clip_id: str):
        clip = self.find(clip_id)
        end, length = clip.end, clip.length
        self.clips.remove(clip)
        for other in self.clips:
            if other.start >= end:
                other.start -= length

    def trim_end(self, clip_id: str, end: int, ripple: bool = False):
        clip = self.find(clip_id)
        length = end - clip.start
        if length < 1 or (clip.source_length is not None and clip.source_in + length > clip.source_length):
            raise ValueError("Invalid trim")
        old_length = clip.length
        following = [c for c in self.clips if c.id != clip.id and c.start >= clip.end]
        clip.length = length
        if ripple:
            for other in following:
                other.start += length - old_length
        try:
            self.validate()
        except Exception:
            clip.length = old_length
            if ripple:
                for other in following:
                    other.start -= length - old_length
            raise


@dataclass
class Timeline:
    fps_num: int = 30
    fps_den: int = 1
    tracks: list[Track] = field(default_factory=list)
    markers: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.fps_num <= 0 or self.fps_den <= 0:
            raise ValueError("Invalid frame rate")

    def to_dict(self):
        return asdict(self)

    def ripple_delete(self, track_index: int, clip_id: str):
        """Delete a clip and close the gap on every track and on the markers.

        A clip on another track that spans the removed range stays put; if shifting a track's
        later clips would make it overlap, that track is left unchanged. Rolls back on error.
        """
        snapshot = deepcopy((self.tracks, self.markers))
        try:
            track = self.tracks[track_index]
            clip = track.find(clip_id)
            start, end, length = clip.start, clip.end, clip.length
            track.clips.remove(clip)
            for other_track in self.tracks:
                if other_track is not track and any(c.start < end and c.end > start for c in other_track.clips):
                    # Spanning clip: shifting later clips could collide with it, so keep this track as is.
                    shifted = sorted((c for c in other_track.clips if c.start >= end), key=lambda c: c.start)
                    kept = [c for c in other_track.clips if c.start < end]
                    if any(c.start - length < max((k.end for k in kept), default=0) for c in shifted):
                        continue
                for c in other_track.clips:
                    if c.start >= end:
                        c.start -= length
            for marker in self.markers:
                frame = marker.get('frame', 0)
                if frame >= end:
                    marker['frame'] = frame - length
                elif frame >= start:
                    marker['frame'] = start
            for t in self.tracks:
                t.validate()
        except ValueError:
            tracks, markers = snapshot
            self.tracks, self.markers = tracks, markers
            raise

    @classmethod
    def from_dict(cls, data):
        tracks = [Track(kind=t['kind'], name=t['name'], muted=t.get('muted', False),
                        clips=[Clip(**c) for c in t.get('clips', [])]) for t in data.get('tracks', [])]
        return cls(fps_num=data.get('fps_num', 30), fps_den=data.get('fps_den', 1),
                   tracks=tracks, markers=data.get('markers', []))

    @classmethod
    def from_legacy(cls, state):
        """Import version-1 editor selection without altering its source media."""
        fps = 30
        start = round(float(state.get('start', 0)) * fps)
        end = round(float(state.get('end', 0)) * fps)
        source = state.get('source', '')
        clips = [Clip(source=source, start=0, source_in=start, length=end-start)] if source and end > start else []
        return cls(tracks=[Track('video', 'Video', clips), Track('audio', 'Audio'),
                           Track('text', 'Text'), Track('overlay', 'Overlay')])
