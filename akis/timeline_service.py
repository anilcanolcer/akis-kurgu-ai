"""Testable operations for the editor's frame-based timeline."""
import time
from typing import NamedTuple

from akis.frame_plan import audio_at, plan_frame
from akis.timeline_model import MAX_CLIP_SPEED, MIN_CLIP_SPEED, Clip, Track
from akis.timeline_render import duration_frames, output_overwrites_source


def selected_clip(timeline, selection):
    if selection is None:
        return None, None
    track_index, clip_id = selection
    if not 0 <= track_index < len(timeline.tracks):
        return None, None
    track = timeline.tracks[track_index]
    return track, next ( (clip for clip in track.clips if clip.id == clip_id), None)


def split_selected(timeline, selection, frame):
    track, clip = selected_clip(timeline, selection)
    if clip is None:
        raise ValueError('Select a clip first')
    return track.split(clip.id, frame)


def append_media(timeline, track_index, path, seconds):
    track = timeline.tracks[track_index]
    if track.kind not in ('video', 'audio', 'overlay'):
        raise ValueError('This track cannot contain media')
    frames = max(1, round(seconds * timeline.fps_num / timeline.fps_den))
    clip = Clip(path, max((item.end for item in track.clips), default=0), frames, source_length=frames)
    track.add(clip)
    return clip


def validate_track_media(media, kind, path):
    """Prevent audio-only or silent sources from entering incompatible tracks."""
    if kind in ('video', 'overlay'):
        try:
            media.dimensions(path)
        except ValueError as exc:
            raise ValueError('Bu iz için görüntü içeren bir dosya seçin.') from exc
    elif kind == 'audio' and not media.has_audio(path):
        raise ValueError('Bu iz için ses içeren bir dosya seçin.')


def append_video(timeline, path, seconds, preferred_track=None):
    """Append a video to the selected video track or the first available one."""
    index = preferred_track
    if index is None or not 0 <= index < len(timeline.tracks) or timeline.tracks[index].kind != 'video':
        index = next((i for i, track in enumerate(timeline.tracks) if track.kind == 'video'), None)
    if index is None:
        timeline.tracks.append(Track('video', 'Video'))
        index = len(timeline.tracks) - 1
    return append_media(timeline, index, path, seconds)


UHD_LONG_SIDE = 3840


def canvas_size(aspect, timeline, media):
    if aspect.startswith('16:9'):
        return 1920, 1080
    if aspect.startswith('1:1'):
        return 1080, 1080
    if aspect.startswith('4:5'):
        return 1080, 1350
    if aspect in ('Kaynak oranı', 'Source ratio'):
        for track in timeline.tracks:
            if track.kind == 'video' and track.clips:
                return media.dimensions(track.clips[0].source)
        raise ValueError('Kaynak video bulunamadı.')
    return 1080, 1920


def output_canvas_size(aspect, timeline, media, profile):
    """Preserve the chosen aspect; 4K profiles double the standard canvas."""
    width, height = canvas_size(aspect, timeline, media)
    if not profile.startswith('4K'):
        return width, height
    # Fixed canvases are 1080-based and double to 4K. A source-ratio canvas is whatever the video is:
    # enlarge it up to 4K at most, so 4K footage stays 4K instead of becoming 8K.
    scale = max(1.0, min(2.0, UHD_LONG_SIDE / max(width, height)))
    return round(width * scale / 2) * 2, round(height * scale / 2) * 2


def audio_target(timeline, frame, speed):
    """Map an unscaled timeline frame to the chosen media position and rate."""
    if speed <= 0:
        raise ValueError('Speed must be positive')
    layer = audio_at(timeline, frame)
    if layer is None:
        return None
    milliseconds = round(layer.source_frame * 1000 * timeline.fps_den / timeline.fps_num)
    clip = timeline.tracks[layer.track_index].find(layer.clip_id)
    return layer.source, milliseconds, speed * clip.speed   # the project's speed times the clip's own


class AudioTarget(NamedTuple):
    track_index: int
    source: str
    position: int       # milliseconds into the source
    rate: float
    volume: float       # the clip's own volume, 0..1


def audio_targets(timeline, frame, speed):
    """Every sound heard at `frame`: each audio-track clip and each video clip's own sound, in track order.
    Clips at volume 0 are left out."""
    if speed <= 0:
        raise ValueError('Speed must be positive')
    found = []
    for layer in plan_frame(timeline, frame):
        if layer.kind not in ('audio', 'video') or not layer.source:
            continue
        clip = timeline.tracks[layer.track_index].find(layer.clip_id)
        if clip.volume <= 0:
            continue
        milliseconds = round(layer.source_frame * 1000 * timeline.fps_den / timeline.fps_num)
        found.append(AudioTarget(layer.track_index, layer.source, milliseconds, speed * clip.speed, clip.volume))
    return found


class PlaybackClock:
    """Wall-clock playback avoids accumulating delayed QTimer events as drift."""
    def __init__(self, now=time.monotonic):
        self.now = now
        self.anchor_time = now()
        self.anchor_frame = 0.0
        self.rate = 1.0
        self.playing = False

    def position(self, timeline):
        position = self.anchor_frame
        if self.playing:
            position += (self.now() - self.anchor_time) * timeline.fps_num / timeline.fps_den * self.rate
        return max(0, int(position))

    def start(self, frame, speed):
        self.anchor_frame, self.rate, self.anchor_time = float(frame), speed, self.now()
        self.playing = True

    def seek(self, frame):
        self.anchor_frame, self.anchor_time = float(frame), self.now()

    def set_speed(self, timeline, speed):
        if speed <= 0:
            raise ValueError('Speed must be positive')
        if self.playing:
            elapsed = self.now() - self.anchor_time
            self.anchor_frame += elapsed * timeline.fps_num / timeline.fps_den * self.rate
            self.anchor_time = self.now()
        self.rate = speed

    def stop(self):
        self.playing = False


def set_clip_volume(timeline, selection, volume):
    track, clip = selected_clip(timeline, selection)
    if clip is None or track.kind not in ('audio', 'video'):
        raise ValueError('Select a video or audio clip')
    if not 0 <= volume <= 1:
        raise ValueError('Volume must be between 0 and 1')
    clip.volume = volume


def set_clip_speed(timeline, selection, speed):
    """Play the selected media clip at `speed` (0.25-4). The clip keeps the same footage, so its length
    changes; later clips on its track move with it (ripple). Keyframes are stretched along. Returns the
    change in length, in frames. Rolls back and raises ValueError when the result would not fit."""
    track, clip = selected_clip(timeline, selection)
    if clip is None or not clip.source or track.kind not in ('video', 'overlay', 'audio'):
        raise ValueError('Select a video or audio clip')
    if not MIN_CLIP_SPEED <= speed <= MAX_CLIP_SPEED:
        raise ValueError('Speed out of range')
    footage, old = clip.source_frames, clip.speed
    length = max(1, round(footage / speed))
    delta = length - clip.length
    later = [other for other in track.clips if other is not clip and other.start >= clip.end]
    saved = (clip.length, dict(clip.style), clip.keyframes, [other.start for other in later])
    style = {key: value for key, value in clip.style.items() if key != 'speed'}
    if speed != 1.0:
        style['speed'] = speed
    clip.style = style
    clip.length = length
    clip.keyframes = {name: [dict(p, frame=min(length - 1, round(p['frame'] * old / speed))) for p in points]
                      for name, points in clip.keyframes.items()}
    for other in later:
        other.start += delta
    try:
        track.validate()
    except ValueError:
        clip.length, clip.style, clip.keyframes = saved[0], saved[1], saved[2]
        for other, start in zip(later, saved[3]):
            other.start = start
        raise
    return delta


def playback_volume(timeline, frame, master):
    layer = audio_at(timeline, frame)
    if layer is None:
        return 0.0
    clip = timeline.tracks[layer.track_index].find(layer.clip_id)
    return max(0.0, min(1.0, master * clip.volume))
