"""Timeline composition shared by still preview and full export.

Tracks composite in list order. Video and overlay clips fill the canvas; text is
centered near the bottom. Audio tracks are mixed; muted tracks are ignored.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def active_clips(timeline, frame):
    if frame < 0:
        raise ValueError('Invalid frame')
    return [(track.kind, clip, clip.source_in + frame - clip.start)
            for track in timeline.tracks if not track.muted
            for clip in track.clips if clip.start <= frame < clip.end]


def duration_frames(timeline):
    return max((clip.end for track in timeline.tracks if not track.muted for clip in track.clips), default=0)


def _escape_filter_path(path):
    return str(path).replace('\\', '/').replace(':', r'\:').replace("'", r"\'")


class TimelineRenderer:
    def __init__(self, media, size=(1080, 1920), font=None):
        self.media = media
        self.width, self.height = size
        if self.width <= 0 or self.height <= 0 or self.width % 2 or self.height % 2:
            raise ValueError('Canvas must have positive even dimensions')
        self.font = font or str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf')

    def _render(self, timeline, output, *, frame=None):
        total = duration_frames(timeline)
        if total <= 0:
            raise ValueError('Timeline is empty')
        fps = timeline.fps_num / timeline.fps_den
        if frame is not None and not 0 <= frame < total:
            raise ValueError('Frame is outside timeline')
        with tempfile.TemporaryDirectory(prefix='akis_render_') as tmp:
            args = ['-y', '-f', 'lavfi', '-i', f'color=c=black:s={self.width}x{self.height}:r={timeline.fps_num}/{timeline.fps_den}:d={total/fps:.9f}']
            graph = ['[0:v]format=yuv420p[base0]']
            base = 'base0'
            audio = []
            index = 1
            layer = 0
            for track in timeline.tracks:
                if track.muted:
                    continue
                for clip in track.clips:
                    start, length, source_in = clip.start/fps, clip.length/fps, clip.source_in/fps
                    if track.kind in ('video', 'overlay'):
                        if not Path(clip.source).is_file():
                            raise FileNotFoundError(clip.source)
                        args += ['-i', clip.source]
                        layer += 1
                        graph.append(f'[{index}:v]trim=start={source_in:.9f}:duration={length:.9f},setpts=PTS-STARTPTS+{start:.9f}/TB,scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[v{layer}]')
                        graph.append(f'[{base}][v{layer}]overlay=eof_action=pass:enable=\'gte(t,{start:.9f})*lt(t,{(clip.end/fps):.9f})\'[base{layer}]')
                        base = f'base{layer}'
                        if track.kind == 'video' and frame is None and self.media.has_audio(clip.source):
                            delay = round(start * 1000)
                            graph.append(f'[{index}:a]atrim=start={source_in:.9f}:duration={length:.9f},asetpts=PTS-STARTPTS,adelay={delay}:all=1[a{index}]')
                            audio.append(f'[a{index}]')
                        index += 1
                    elif track.kind == 'audio':
                        if not Path(clip.source).is_file():
                            raise FileNotFoundError(clip.source)
                        args += ['-i', clip.source]
                        delay = round(start * 1000)
                        graph.append(f'[{index}:a]atrim=start={source_in:.9f}:duration={length:.9f},asetpts=PTS-STARTPTS,adelay={delay}:all=1[a{index}]')
                        audio.append(f'[a{index}]')
                        index += 1
                    elif track.kind == 'text' and clip.text:
                        textfile = Path(tmp) / f'text{layer}.txt'
                        textfile.write_text(clip.text, encoding='utf-8')
                        layer += 1
                        graph.append(f'[{base}]drawtext=fontfile=\'{_escape_filter_path(self.font)}\':textfile=\'{_escape_filter_path(textfile)}\':expansion=none:fontcolor=white:fontsize=h/18:x=(w-text_w)/2:y=h*0.78:box=1:boxcolor=black@0.5:boxborderw=12:enable=\'gte(t,{start:.9f})*lt(t,{clip.end/fps:.9f})\'[base{layer}]')
                        base = f'base{layer}'
            if audio:
                graph.append(''.join(audio) + f'amix=inputs={len(audio)}:duration=longest:normalize=0[aout]')
            args += ['-filter_complex', ';'.join(graph), '-map', f'[{base}]']
            if frame is not None:
                args += ['-ss', f'{frame/fps:.9f}', '-frames:v', '1', '-an', str(output)]
            else:
                if audio:
                    args += ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k']
                args += ['-t', f'{total/fps:.9f}', '-r', f'{timeline.fps_num}/{timeline.fps_den}', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
            result = self.media.run(args, text=True)
            if result.returncode:
                raise RuntimeError('\n'.join(result.stderr.splitlines()[-12:]))
            if not Path(output).is_file():
                raise RuntimeError('FFmpeg did not create output')
            return str(output)

    def preview(self, timeline, frame, output):
        return self._render(timeline, output, frame=frame)

    def export(self, timeline, output):
        return self._render(timeline, output)
