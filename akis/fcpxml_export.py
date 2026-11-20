"""Hand the edit to DaVinci Resolve or Final Cut Pro as an FCPXML file.

The file refers to the original media (nothing is rendered); the other program cuts the same pieces at
the same places. The first video track becomes the main storyline; other video tracks and the audio
tracks are clips connected to it. Clip volume goes along. Text, shapes, transitions and the colour, speed
and sound settings are this app's own and are not written; describe() says what was left out.
"""
import math
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

VERSION = '1.10'


def rational(frames, fps_num, fps_den):
    """A time in FCPXML's form: a whole number of seconds ('2s') or a fraction ('1001/30000s')."""
    value = Fraction(frames * fps_den, fps_num)
    return f'{value.numerator}s' if value.denominator == 1 else f'{value.numerator}/{value.denominator}s'


def seconds_rational(seconds, fps_num, fps_den):
    """A media length in seconds, rounded to whole frames of the sequence."""
    return rational(max(1, round(seconds * fps_num / fps_den)), fps_num, fps_den)


def volume_db(volume):
    return '-96dB' if volume <= 0 else f'{20 * math.log10(volume):.1f}dB'


def build(timeline, canvas, media, name='Akış Kurgu'):
    """(XML text, report). report: {'clips': written, 'texts': left out, 'transitions': left out}."""
    num, den = timeline.fps_num, timeline.fps_den
    time = lambda frames: rational(frames, num, den)
    width, height = canvas
    report = {'clips': 0, 'texts': 0, 'transitions': 0, 'speeds': 0}

    root = ET.Element('fcpxml', version=VERSION)
    resources = ET.SubElement(root, 'resources')
    ET.SubElement(resources, 'format', id='r1', name=f'Akis{width}x{height}', frameDuration=rational(1, num, den),
                  width=str(width), height=str(height))
    assets = {}
    formats = {(width, height, Fraction(num, den)): 'r1'}

    def source_format(source):
        # The project can be portrait / 25 fps while the original movie is landscape / 30 fps.
        # Leave the optional reference to the importer when FFmpeg cannot identify the rate reliably.
        try:
            w, h = media.dimensions(source)
            rate = Fraction(*media.frame_rate(source))
            if abs(media.video_rate(source) - float(rate)) > 0.0051:
                return None
        except (TypeError, ValueError, OSError, RuntimeError, AttributeError, ZeroDivisionError):
            return None
        key = (w, h, rate)
        if key not in formats:
            identifier = f'fmt{len(formats) + 1}'
            ET.SubElement(resources, 'format', id=identifier, name=f'Akis{w}x{h}', width=str(w), height=str(h),
                          frameDuration=rational(1, rate.numerator, rate.denominator))
            formats[key] = identifier
        return formats[key]

    def asset(source):
        if source not in assets:
            identifier = f'r{len(assets) + 2}'
            try:
                seconds = float(media.duration(source))
            except Exception:
                seconds = 0.0
            # What the file really holds: a WAV or MP3 has no picture, a mono recording one channel.
            # Resolve and Final Cut trust these attributes, so a sound file described as video with two
            # channels came in as a blank video clip with a phantom right channel.
            try:
                picture = bool(media.has_video(source))
                channels = int(media.audio_channels(source))
            except Exception:
                picture, channels = True, 2
            attributes = {'id': identifier, 'name': Path(source).name, 'start': '0s',
                          'duration': seconds_rational(seconds, num, den) if seconds else time(1),
                          'hasVideo': '1' if picture else '0', 'hasAudio': '1' if channels else '0'}
            if picture:
                fmt = source_format(source)
                if fmt:
                    attributes['format'] = fmt
            element = ET.SubElement(resources, 'asset', attributes)
            if channels:
                element.set('audioSources', '1')
                element.set('audioChannels', str(channels))
            ET.SubElement(element, 'media-rep', kind='original-media', src=Path(source).resolve().as_uri())
            assets[source] = identifier
        return assets[source]

    def clip_element(parent, clip, offset, lane=None, kind="video"):
        attributes = {'ref': asset(clip.source), 'name': Path(clip.source).name, 'offset': offset,
                      'start': time(clip.source_in), 'duration': time(clip.length)}
        if lane is not None:
            attributes['lane'] = str(lane)
        if kind == 'overlay':
            attributes['srcEnable'] = 'video'
        elif kind == 'audio':
            attributes['srcEnable'] = 'audio'
            attributes['audioRole'] = 'music'
        element = ET.SubElement(parent, 'asset-clip', attributes)
        if clip.volume != 1.0:
            ET.SubElement(element, 'adjust-volume', amount=volume_db(clip.volume))
        report['clips'] += 1
        if clip.style.get('transition'):
            report['transitions'] += 1
        if clip.speed != 1.0:   # written at normal speed, from its in-point, for its timeline length
            report['speeds'] += 1
        return element

    tracks = [track for track in timeline.tracks if not track.muted]
    for track in tracks:
        if track.kind == 'text':
            report['texts'] += len(track.clips)
    media_tracks = [t for t in tracks if t.kind in ('video', 'overlay', 'audio') and t.clips]
    total = max((clip.end for track in media_tracks for clip in track.clips), default=0)
    primary = next((t for t in media_tracks if t.kind == 'video'), None)

    library = ET.SubElement(root, 'library')
    event = ET.SubElement(library, 'event', name=name)
    project = ET.SubElement(event, 'project', name=name)
    sequence = ET.SubElement(project, 'sequence', format='r1', duration=time(max(1, total)), tcStart='0s',
                             tcFormat='NDF', audioLayout='stereo', audioRate='48k')
    spine = ET.SubElement(sequence, 'spine')

    # The storyline: the main video track's clips, with gaps wherever it is empty, out to the end.
    items, cursor = [], 0                  # (timeline start, timeline end, element, local start frame)
    for clip in sorted(primary.clips if primary else [], key=lambda c: c.start):
        if clip.start > cursor:
            gap = ET.SubElement(spine, 'gap', name='Boşluk', offset=time(cursor), start='0s', duration=time(clip.start - cursor))
            items.append((cursor, clip.start, gap, 0))
        element = clip_element(spine, clip, time(clip.start))
        items.append((clip.start, clip.end, element, clip.source_in))
        cursor = clip.end
    if total > cursor:
        gap = ET.SubElement(spine, 'gap', name='Boşluk', offset=time(cursor), start='0s', duration=time(total - cursor))
        items.append((cursor, total, gap, 0))

    # Everything else hangs off the storyline item it starts over, in that item's own time.
    lanes = {}
    video_lane, audio_lane = 0, 0
    for track in media_tracks:
        if track is primary:
            continue
        if track.kind == 'audio':
            audio_lane -= 1
            lanes[id(track)] = audio_lane
        else:
            video_lane += 1
            lanes[id(track)] = video_lane
    for track in media_tracks:
        if track is primary:
            continue
        for clip in sorted(track.clips, key=lambda c: c.start):
            parent = next((item for item in items if item[0] <= clip.start < item[1]), None)
            if parent is None:
                continue
            first, _, element, local = parent
            clip_element(element, clip, time(local + clip.start - first), lanes[id(track)], track.kind)

    ET.indent(root, space='  ')
    text = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(root, encoding='unicode') + '\n'
    return text, report


def describe(report, say=str):
    """One sentence about what was written and what was left out."""
    parts = [say('{count} klip yazıldı.').format(count=report['clips'])]
    if report['texts']:
        parts.append(say('{count} yazı ve altyazı klibi aktarılmadı.').format(count=report['texts']))
    if report['transitions']:
        parts.append(say('{count} geçiş aktarılmadı.').format(count=report['transitions']))
    if report.get('speeds'):
        parts.append(say('{count} klibin hızı aktarılmadı; normal hızda yazıldı.').format(count=report['speeds']))
    return ' '.join(parts)
