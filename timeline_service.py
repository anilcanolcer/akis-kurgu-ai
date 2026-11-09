"""Testable operations for the editor's frame-based timeline."""
import time

from frame_plan import audio_at
from timeline_model import Clip, Track
from timeline_render import duration_frames


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


def audio_target(timeline, frame, speed):
    """Map an unscaled timeline frame to the chosen media position and rate."""
    if speed <= 0:
        raise ValueError('Speed must be positive')
    layer = audio_at(timeline, frame)
    if layer is None:
        return None
    milliseconds = round(layer.source_frame * 1000 * timeline.fps_den / timeline.fps_num)
    return layer.source, milliseconds, speed


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


def playback_volume(timeline, frame, master):
    layer = audio_at(timeline, frame)
    if layer is None:
        return 0.0
    clip = timeline.tracks[layer.track_index].find(layer.clip_id)
    return max(0.0, min(1.0, master * clip.volume))
