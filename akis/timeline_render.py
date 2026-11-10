"""Timeline composition shared by still preview and full export.

Tracks composite in list order. Video and overlay clips fill the canvas; text is
centered near the bottom. Audio tracks are mixed; muted tracks are ignored.
"""
from __future__ import annotations

import os
import tempfile
import textwrap
import zlib
from pathlib import Path
from akis.frame_plan import plan_frame, plan_segments

TRANSITIONS = ('fade', 'flash', 'dip', 'slide_left', 'slide_right', 'slide_up', 'slide_down')
TEXT_SCALE = {'small': 0.75, 'medium': 1.0, 'large': 1.5}
TEXT_WRAP = {'small': 30, 'medium': 22, 'large': 15}
TEXT_COLORS = {'white': 'white', 'yellow': '#FFDD00', 'red': '#FF2D2D', 'green': '#39FF5A',
               'blue': '#3CA0FF', 'pink': '#FF50C8'}


def transition_of(track, clip):
    """(name, frames) for the transition into clip, or None."""
    name = clip.style.get('transition')
    if track.kind != 'video' or name not in TRANSITIONS:
        return None
    frames = min(int(clip.style.get('transition_frames', 10)), clip.length // 2)
    return (name, frames) if frames >= 1 else None


def outgoing_hold(track, clip):
    """Frames this clip's last picture is held under the next clip's transition."""
    following = next((c for c in track.clips if c.start == clip.end), None)
    transition = transition_of(track, following) if following else None
    return transition[1] if transition else 0


def active_clips(timeline, frame):
    return [(layer.kind, timeline.tracks[layer.track_index].find(layer.clip_id), layer.source_frame)
            for layer in plan_frame(timeline, frame)]


def duration_frames(timeline):
    return max((clip.end for track in timeline.tracks if not track.muted for clip in track.clips), default=0)


def output_overwrites_source(timeline, output, extra_sources=()):
    """Reject outputs resolving to a media source, including hard links."""
    target = Path(output)
    target_key = os.path.normcase(str(target.resolve()))
    sources = list(extra_sources) + [clip.source for track in timeline.tracks for clip in track.clips]
    for name in sources:
        if not name:
            continue
        source = Path(name)
        if target_key == os.path.normcase(str(source.resolve())):
            return True
        try:
            if target.exists() and source.exists() and os.path.samefile(target, source):
                return True
        except OSError:
            continue
    return False


def _escape_filter_path(path):
    return str(path).replace('\\', '/').replace(':', r'\:').replace("'", r"\'")


class TimelineRenderer:
    def __init__(self, media, size=(1080, 1920), font=None, *, brightness=0, contrast=0, saturation=0, speed=1.0, fast=False):
        self.fast = fast  # quick, larger encode for the in-app playback proxy
        self.media = media
        self.width, self.height = size
        if self.width <= 0 or self.height <= 0 or self.width % 2 or self.height % 2:
            raise ValueError('Canvas must have positive even dimensions')
        self.font = font or str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf')
        if not 0.5 <= speed <= 2.0:
            raise ValueError('Speed must be between 0.5 and 2.0')
        if any(not -50 <= v <= 50 for v in (brightness, contrast, saturation)):
            raise ValueError('Color adjustment out of range')
        self.brightness, self.contrast, self.saturation, self.speed = brightness, contrast, saturation, speed

    def _render(self, timeline, output, *, frame=None):
        if frame is None and self.speed != 1.0:
            with tempfile.TemporaryDirectory(prefix='akis_speed_') as tmp:
                intermediate = str(Path(tmp) / 'composition.mp4')
                TimelineRenderer(self.media, (self.width, self.height), self.font,
                                 brightness=self.brightness, contrast=self.contrast,
                                 saturation=self.saturation).export(timeline, intermediate)
                args = ['-y', '-i', intermediate, '-vf', f'setpts=PTS/{self.speed:.6f}']
                if self.media.has_audio(intermediate):
                    args += ['-af', f'atempo={self.speed:.6f}', '-c:a', 'aac', '-b:a', '192k']
                args += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
                result = self.media.run(args, text=True)
                if result.returncode or not Path(output).is_file():
                    raise RuntimeError('\n'.join(result.stderr.splitlines()[-12:]))
                return str(output)
        total = duration_frames(timeline)
        if total <= 0:
            raise ValueError('Timeline is empty')
        fps = timeline.fps_num / timeline.fps_den
        if frame is not None and not 0 <= frame < total:
            raise ValueError('Frame is outside timeline')
        segments = plan_segments(timeline)
        planned_ids = {(layer.track_index, layer.clip_id)
                       for _, _, layers in segments for layer in layers}
        if frame is not None:
            planned_ids = {(layer.track_index, layer.clip_id) for layer in plan_frame(timeline, frame)}
            for track_index, track in enumerate(timeline.tracks):  # outgoing clip is still visible mid-transition
                if track.kind == 'video' and not track.muted:
                    for clip in track.clips:
                        if clip.end <= frame < clip.end + outgoing_hold(track, clip):
                            planned_ids.add((track_index, clip.id))
        with tempfile.TemporaryDirectory(prefix='akis_render_') as tmp:
            args = ['-y', '-f', 'lavfi', '-i', f'color=c=black:s={self.width}x{self.height}:r={timeline.fps_num}/{timeline.fps_den}:d={total/fps:.9f}']
            graph = ['[0:v]format=yuv420p[base0]']
            base = 'base0'
            audio = []
            index = 1
            layer = 0
            for track_index, track in enumerate(timeline.tracks):
                if track.muted:
                    continue
                for clip in sorted(track.clips, key=lambda c: c.start):
                    if (track_index, clip.id) not in planned_ids:
                        continue
                    start, length, source_in = clip.start/fps, clip.length/fps, clip.source_in/fps
                    if track.kind in ('video', 'overlay'):
                        if not Path(clip.source).is_file():
                            raise FileNotFoundError(clip.source)
                        args += ['-i', clip.source]
                        layer += 1
                        hold = outgoing_hold(track, clip) / fps
                        chain = f'[{index}:v]trim=start={source_in:.9f}:duration={length:.9f},setpts=PTS-STARTPTS'
                        if hold:
                            chain += f',tpad=stop_mode=clone:stop_duration={hold:.9f}'
                        chain += (f',scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,'
                                  f'pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1')
                        position = ''
                        transition = transition_of(track, clip)
                        if transition:
                            name, seconds = transition[0], transition[1] / fps
                            if name == 'fade':
                                chain += f',format=yuva420p,fade=t=in:st=0:d={seconds:.9f}:alpha=1'
                            elif name in ('flash', 'dip'):
                                tint = 'white' if name == 'flash' else 'black'
                                chain += f',fade=t=in:st=0:d={seconds:.9f}:color={tint}'
                            else:  # eased slide of the incoming picture over the held outgoing one
                                ease = f'pow(max(0,1-(t-{start:.9f})/{seconds:.9f}),2)'
                                axis, extent = ('x', 'W') if name in ('slide_left', 'slide_right') else ('y', 'H')
                                sign = '' if name in ('slide_left', 'slide_up') else '-'
                                position = f"{axis}='{sign}{extent}*{ease}':"
                        graph.append(f'{chain},setpts=PTS+{start:.9f}/TB[v{layer}]')
                        graph.append(f'[{base}][v{layer}]overlay={position}eof_action=pass:enable=\'gte(t,{start:.9f})*lt(t,{(clip.end/fps + hold):.9f})\'[base{layer}]')
                        base = f'base{layer}'
                        if track.kind == 'video' and frame is None and self.media.has_audio(clip.source):
                            delay = round(start * 1000)
                            graph.append(f'[{index}:a]atrim=start={source_in:.9f}:duration={length:.9f},asetpts=PTS-STARTPTS,volume={clip.volume:.6f},adelay={delay}:all=1[a{index}]')
                            audio.append(f'[a{index}]')
                        index += 1
                    elif track.kind == 'audio':
                        if frame is not None:
                            continue
                        if not Path(clip.source).is_file():
                            raise FileNotFoundError(clip.source)
                        args += ['-i', clip.source]
                        delay = round(start * 1000)
                        graph.append(f'[{index}:a]atrim=start={source_in:.9f}:duration={length:.9f},asetpts=PTS-STARTPTS,volume={clip.volume:.6f},adelay={delay}:all=1[a{index}]')
                        audio.append(f'[a{index}]')
                        index += 1
                    elif track.kind == 'text' and clip.style.get('shape'):
                        from akis.shape_art import draw_shape
                        layer += 1
                        picture = Path(tmp) / f'shape{layer}.png'
                        draw_shape(clip.style, (self.width, self.height), zlib.crc32(clip.id.encode())).save(picture)
                        args += ['-loop', '1', '-framerate', f'{timeline.fps_num}/{timeline.fps_den}',
                                 '-t', f'{length:.9f}', '-i', str(picture)]
                        pop = min(0.2, length / 2)
                        graph.append(f'[{index}:v]format=rgba,fade=t=in:st=0:d={pop:.9f}:alpha=1,setpts=PTS+{start:.9f}/TB[v{layer}]')
                        graph.append(f'[{base}][v{layer}]overlay=eof_action=pass:enable=\'gte(t,{start:.9f})*lt(t,{clip.end/fps:.9f})\'[base{layer}]')
                        base = f'base{layer}'
                        index += 1
                    elif track.kind == 'text' and clip.text:
                        textfile = Path(tmp) / f'text{layer}.txt'
                        layer += 1
                        window = f'enable=\'gte(t,{start:.9f})*lt(t,{clip.end/fps:.9f})\''
                        common = f'[{base}]drawtext=textfile=\'{_escape_filter_path(textfile)}\':expansion=none'
                        if clip.style:
                            size = clip.style.get('size') if clip.style.get('size') in TEXT_SCALE else 'medium'
                            textfile.write_text('\n'.join(textwrap.wrap(clip.text, TEXT_WRAP[size])) or clip.text,
                                                encoding='utf-8', newline='\n')  # CRLF would render as a blank line
                            x, y = float(clip.style.get('x', 0.5)), float(clip.style.get('y', 0.78))
                            bold = Path(self.font).with_name('arialbd.ttf')
                            font = bold if bold.is_file() else self.font
                            colour = TEXT_COLORS.get(clip.style.get('color'), 'white')
                            graph.append(f'{common}:fontfile=\'{_escape_filter_path(font)}\':text_align=C:line_spacing=6'
                                         f':fontcolor={colour}:fontsize=h/18*{TEXT_SCALE[size]}:borderw={max(2, round(self.height / 300))}:bordercolor=black'
                                         f':x=\'max(10,min(w-text_w-10,w*{x:.4f}-text_w/2))\''
                                         f':y=\'max(10,min(h-text_h-10,h*{y:.4f}-text_h/2))\':{window}[base{layer}]')
                        else:
                            textfile.write_text(clip.text, encoding='utf-8')
                            graph.append(f'{common}:fontfile=\'{_escape_filter_path(self.font)}\':fontcolor=white:fontsize=h/18'
                                         f':x=(w-text_w)/2:y=h*0.78:box=1:boxcolor=black@0.5:boxborderw=12:{window}[base{layer}]')
                        base = f'base{layer}'
            graph.append(f'[{base}]eq=brightness={self.brightness/100:.3f}:contrast={1+self.contrast/100:.3f}:saturation={1+self.saturation/50:.3f}[graded]')
            base = 'graded'
            if audio:
                graph.append(''.join(audio) + f'amix=inputs={len(audio)}:duration=longest:normalize=0[aout]')
            args += ['-filter_complex', ';'.join(graph), '-map', f'[{base}]']
            if frame is not None:
                args += ['-ss', f'{frame/fps:.9f}', '-frames:v', '1', '-an', str(output)]
            else:
                if audio:
                    args += ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k']
                quality = ['-preset', 'ultrafast', '-crf', '24', '-g', '15'] if self.fast else []
                args += ['-r', f'{timeline.fps_num}/{timeline.fps_den}', '-c:v', 'libx264', *quality, '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
            result = self.media.run(args, text=True)
            if result.returncode:
                raise RuntimeError('\n'.join(result.stderr.splitlines()[-12:]))
            if not Path(output).is_file():
                raise RuntimeError('FFmpeg did not create output')
            return str(output)

    def preview(self, timeline, frame, output):
        return self._render(timeline, output, frame=frame)

    def export(self, timeline, output):
        if output_overwrites_source(timeline, output):
            raise ValueError('Çıktı dosyası kaynak medyayla aynı olamaz.')
        return self._render(timeline, output)
