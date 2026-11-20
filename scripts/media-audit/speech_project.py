"""Windows speech to local Whisper, a moved project, visible captions and FCPXML.

Requires an installed Turkish or English voice and a cached faster-whisper tiny model. All media is synthetic.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

from akis import ai_service, caption_service, fcpxml_export, project_service, tts_service
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer


def ffmpeg(*args):
    return subprocess.run([executable, '-nostdin', '-v', 'error', *map(str, args)],
                          capture_output=True, check=True).stdout


def pixels(path, timestamp):
    raw = ffmpeg('-ss', timestamp, '-i', path, '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-')
    return np.frombuffer(raw, dtype=np.uint8).reshape(180, 320, 3).astype(int)


executable = shutil.which('ffmpeg')
media = MediaService(executable)
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    project = root / 'original'
    project.mkdir()
    wav = project / 'voice.wav'
    languages = {lang.split('-')[0] for _, _, lang in tts_service.voices()}
    if 'tr' in languages:
        language = 'tr'
        sentence = 'Bugün hava çok güzel. Kırmızı araba yavaş yavaş yolda gidiyor.'
        keywords = {'bugün', 'hava', 'güzel', 'kırmızı', 'araba', 'yavaş', 'yolda', 'gidiyor'}
    elif 'en' in languages:
        language = 'en'
        sentence = 'The blue train stops at the station. The red train crosses the river.'
        keywords = {'train', 'blue', 'station', 'red', 'river'}
    else:
        raise RuntimeError('The speech audit needs an installed Turkish or English Windows voice.')
    tts_service.synthesize(sentence, wav, language=language)
    movie = project / 'train.mp4'
    ffmpeg('-f', 'lavfi', '-i', 'color=c=navy:s=320x180:r=30', '-i', wav, '-shortest',
           '-c:v', 'libx264', '-c:a', 'aac', movie)
    segments = ai_service.local_transcribe(movie, 'tiny', timed=True, language=language, download=False)
    words = [word for segment in segments for word in segment.get('words', [])]
    recognized = set(re.findall(r'[^\W\d_]+', ' '.join(segment['text'] for segment in segments).lower()))
    matches = recognized & keywords
    assert len(matches) >= 3 and all(w['start'] <= w['end'] for w in words), segments

    frames = round(media.duration(movie) * 30)
    timeline = Timeline(tracks=[Track('video', 'Video', [Clip(str(movie), 0, frames)])])
    captions = caption_service.caption_track(timeline, str(movie), segments, look='vurgu')
    assert captions and all(c.style.get('words') for c in timeline.tracks[-1].clips)
    document = project_service.make_document({'source': str(movie)}, timeline, {}, '')
    project_service.save_with_snapshot(project / 'train.akis.json', document, snapshot=True)
    moved = root / 'taşınmış proje'
    project.rename(moved)
    saved, source, missing = project_service.load_project(moved / 'train.akis.json')
    assert not missing and Path(source).samefile(moved / 'train.mp4')
    restored = Timeline.from_dict(saved['timeline'])
    clip = restored.tracks[-1].clips[0]
    when = (clip.start + clip.length // 2) / 30
    output = TimelineRenderer(media, (320, 180)).export(restored, root / 'captioned.mp4')
    changed = int(np.count_nonzero(np.abs(pixels(output, when) - pixels(source, when)).max(axis=2) > 40))
    assert changed > 100 and media.has_audio(output)
    assert abs(media.duration(output) - frames / 30) < 0.1
    xml, report = fcpxml_export.build(restored, (320, 180), media)
    assert ET.fromstring(xml).find('resources/asset/media-rep').get('src') == (moved / 'train.mp4').as_uri()
    assert report['texts'] == captions
    print(json.dumps(dict(language=language, timed_words=len(words), caption_clips=captions, recognized_keywords=sorted(matches),
                          changed_pixels=changed, export_seconds=media.duration(output), missing_sources=missing)))
