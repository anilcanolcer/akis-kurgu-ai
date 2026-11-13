"""Timeline composition shared by still preview and full export.

Tracks composite in list order. Video and overlay clips fill the canvas; text is
centered near the bottom. Audio tracks are mixed; muted tracks are ignored.
"""
from __future__ import annotations

import os
import re
import tempfile
import textwrap
import zlib
from pathlib import Path
from akis import audio_polish, caption_layout, clip_fit, emphasis
from akis.frame_plan import plan_frame, plan_segments

TRANSITIONS = ('fade', 'flash', 'dip', 'slide_left', 'slide_right', 'slide_up', 'slide_down')
AUDIO_PREROLL = 0.5  # seconds decoded before a cut so the audio decoder has settled at the cut
# HDR (BT.2020 PQ/HLG) to SDR BT.709: linear light, tone curve, then back to an 8-bit video signal.
# mobius keeps everything up to SDR white as it is and only rolls off the highlights (hable darkens the whole picture).
TONE_MAP = ('zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=mobius:desat=0,'
            'zscale=t=bt709:m=bt709:r=tv,format=yuv420p')
LIMITER = 'alimiter=limit=0.89:level=0:latency=1'  # -1 dB ceiling; no automatic gain, no added delay
TEXT_SCALE = {'small': 0.75, 'medium': 1.0, 'large': 1.5}
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
    """A path as an unquoted filter option value, escaped for both parsing levels.

    The option parser treats \\ ' : specially; the graph parser (also for -/filter_complex
    scripts, checked with ffmpeg 9) additionally \\ ' [ ] , ;. Inside '...' quoting there is
    no way to write an apostrophe, so a user folder like O'Neil needs backslashes instead.
    """
    value = re.sub(r"([\\':])", r'\\\1', str(path).replace('\\', '/'))
    return re.sub(r"([\\'\[\],;])", r'\\\1', value)


def _text_lines(text, width=None):
    """The user's own line breaks kept (any of CRLF/CR/LF), each paragraph wrapped on its own."""
    paragraphs = str(text).replace('\r\n', '\n').replace('\r', '\n').rstrip('\n').split('\n')
    if width is None:
        return '\n'.join(paragraphs)
    return '\n'.join('\n'.join(textwrap.wrap(p, width)) or p for p in paragraphs)


def _font_px(width, height, scale=1.0):
    """Text size from the canvas' shorter side, so a vertical (9:16) frame does not get
    landscape-height letters that cannot fit across its narrow width."""
    return max(12, round(min(height / 18, width / 12) * scale))


def _fit_lines(text, font_path, px, max_width):
    """Greedy word wrap by measured pixel width (user line breaks kept); a word wider than
    the line is split by characters, so no line is ever wider than max_width."""
    try:
        from PIL import ImageFont
        measure = ImageFont.truetype(str(font_path), px).getlength
    except Exception:
        measure = lambda s: len(s) * px * 0.62  # conservative Arial estimate
    out = []
    for paragraph in _text_lines(text).split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = f'{line} {word}' if line else word
            if measure(candidate) <= max_width:
                line = candidate
                continue
            if line:
                out.append(line)
            line = ''
            for ch in word:
                if line and measure(line + ch) > max_width:
                    out.append(line)
                    line = ''
                line += ch
        out.append(line)
    return '\n'.join(out)


def partial_output_path(output):
    """Sibling name an export is written to before it replaces the target; keeps the extension
    so FFmpeg still picks the container from it."""
    target = Path(output)
    return target.with_name(f'{target.stem}.part{target.suffix or ".mp4"}')


class TimelineRenderer:
    def __init__(self, media, size=(1080, 1920), font=None, *, brightness=0, contrast=0, saturation=0, speed=1.0, fast=False,
                 audio=()):
        self.audio = audio_polish.clean(audio)  # sound clean-up options, see akis.audio_polish
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

    def _needs_tone_mapping(self, source):
        """HDR footage (PQ/HLG, e.g. phone video) must be mapped to SDR or it comes out grey and flat.
        Skipped when this FFmpeg build lacks zscale; the picture is then converted as before."""
        try:
            return (self.media.is_hdr(source) is True and self.media.has_filter('zscale') is True
                    and self.media.has_filter('tonemap') is True)
        except (AttributeError, TypeError):  # a stand-in media service without these probes
            return False

    def _picture_rect(self, timeline, text_clip):
        """The rectangle the video under a text clip covers on the canvas; the whole canvas when there is
        no video there or its size cannot be read."""
        canvas = (self.width, self.height)
        for track in timeline.tracks:
            if track.kind != 'video' or track.muted:
                continue
            under = next((clip for clip in track.clips if clip.start <= text_clip.start < clip.end), None)
            if under is None:
                continue
            try:
                size = self.media.dimensions(under.source)
                return caption_layout.picture_rect(canvas, (int(size[0]), int(size[1])), clip_fit.is_fill(under.style))
            except Exception:  # an unreadable file or a stand-in media service
                break
        return 0, 0, self.width, self.height

    @staticmethod
    def _open_input(args, source, position, with_audio):
        """Adds a source input seeked to `position` seconds; returns how far before `position` the
        seek lands, for the trim filter to drop.

        Input seeking (accurate by default when transcoding) replaces decoding the whole source up
        to the cut and trimming there. Audio decoders need a few packets of history (an AAC frame
        overlaps the previous one; Opus asks for 80 ms), so inputs whose sound is used start a
        little early; the picture is unaffected because video decoding restarts at a keyframe.
        """
        lead = min(position, AUDIO_PREROLL) if with_audio else 0.0
        if position - lead > 0:
            args += ['-ss', f'{position - lead:.9f}']
        args += ['-i', source]
        return lead

    @staticmethod
    def _trim(name, lead, duration):
        return f'{name}=start={lead:.9f}:duration={duration:.9f}' if lead else f'{name}=duration={duration:.9f}'

    def _render(self, timeline, output, *, frame=None, on_progress=None):
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
        # A still preview renders only from its own moment onward: every input is seeked straight to
        # the frame instead of decoding from the start, so a frame ten minutes in costs the same as
        # the first one. Output time 0 is timeline time `window`. Export keeps window = 0.
        window = frame / fps if frame is not None else 0.0
        with tempfile.TemporaryDirectory(prefix='akis_render_') as tmp:
            args = ['-y', '-f', 'lavfi', '-i', f'color=c=black:s={self.width}x{self.height}:r={timeline.fps_num}/{timeline.fps_den}:d={total/fps - window:.9f}']
            graph = ['[0:v]format=yuv420p[base0]']
            base = 'base0'
            audio = []
            voices, music = [], []  # the same labels, split by what they are
            voice_filter = audio_polish.voice_filter(self.audio)
            index = 1
            layer = 0
            for track_index, track in enumerate(timeline.tracks):
                if track.muted:
                    continue
                for clip in sorted(track.clips, key=lambda c: c.start):
                    if (track_index, clip.id) not in planned_ids:
                        continue
                    start, length, source_in = clip.start/fps, clip.length/fps, clip.source_in/fps
                    # skip: how far into this clip the preview moment lies (the last frame for a clip
                    # held under the next clip's transition); placed: output time its remainder starts.
                    skip = 0.0 if frame is None else min(max(0, frame - clip.start), clip.length - 1) / fps
                    placed = max(0.0, start - window)
                    local_start, end_at = start - window, clip.end / fps - window
                    # Frame times are not exact in floating point; compare against half-frame edges so
                    # a layer appears on its first frame rather than one frame late.
                    on, off = local_start - 0.5 / fps, end_at - 0.5 / fps
                    if track.kind in ('video', 'overlay'):
                        if not Path(clip.source).is_file():
                            raise FileNotFoundError(f'Medya bulunamadı: {clip.source}')
                        layer += 1
                        hold = outgoing_hold(track, clip) / fps
                        # Each clip has its own input, seeked (not decoded from the source's start);
                        # the clip's audio below reads the same seeked input.
                        lead = self._open_input(args, clip.source, source_in + skip, frame is None)
                        chain = f'[{index}:v]{self._trim("trim", lead, length - skip)},setpts=PTS-STARTPTS'
                        if hold:
                            chain += f',tpad=stop_mode=clone:stop_duration={hold:.9f}'
                        scale, place = clip_fit.filters(clip.style, self.width, self.height)  # fit inside, or fill and crop
                        chain += f',{scale}'
                        if self._needs_tone_mapping(clip.source):  # after scaling: the float maths is costly
                            chain += f',{TONE_MAP}'
                        chain += f',{place},setsar=1'
                        # Punch-in zooms (akis.emphasis); zoompan restarts time at 0, as the chain has here.
                        zoom = emphasis.zoom_filter(clip, timeline.fps_num, timeline.fps_den, skip, self.width, self.height)
                        if zoom:
                            chain += f',{zoom}'
                        if skip:  # restore clip-local time so transitions see where they are
                            chain += f',setpts=PTS+{skip:.9f}/TB'
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
                                ease = f'pow(max(0,1-(t-({local_start:.9f}))/{seconds:.9f}),2)'
                                axis, extent = ('x', 'W') if name in ('slide_left', 'slide_right') else ('y', 'H')
                                sign = '' if name in ('slide_left', 'slide_up') else '-'
                                position = f"{axis}='{sign}{extent}*{ease}':"
                        graph.append(f'{chain},setpts=PTS-{skip:.9f}/TB+{placed:.9f}/TB[v{layer}]')
                        graph.append(f'[{base}][v{layer}]overlay={position}eof_action=pass:enable=\'gte(t,{on:.9f})*lt(t,{(off + hold):.9f})\'[base{layer}]')
                        base = f'base{layer}'
                        if track.kind == 'video' and frame is None and self.media.has_audio(clip.source):
                            delay = round(start * 1000)
                            graph.append(f'[{index}:a]{self._trim("atrim", lead, length)},asetpts=PTS-STARTPTS,{voice_filter}volume={clip.volume:.6f},adelay={delay}:all=1[a{index}]')
                            audio.append(f'[a{index}]')
                            voices.append(f'[a{index}]')
                        index += 1
                    elif track.kind == 'audio':
                        if frame is not None:
                            continue
                        if not Path(clip.source).is_file():
                            raise FileNotFoundError(f'Medya bulunamadı: {clip.source}')
                        lead = self._open_input(args, clip.source, source_in, True)
                        delay = round(start * 1000)
                        graph.append(f'[{index}:a]{self._trim("atrim", lead, length)},asetpts=PTS-STARTPTS,volume={clip.volume:.6f},adelay={delay}:all=1[a{index}]')
                        audio.append(f'[a{index}]')
                        music.append(f'[a{index}]')
                        index += 1
                    elif track.kind == 'text' and clip.style.get('shape'):
                        from akis.shape_art import draw_shape
                        layer += 1
                        picture = Path(tmp) / f'shape{layer}.png'
                        draw_shape(clip.style, (self.width, self.height), zlib.crc32(clip.id.encode())).save(picture)
                        args += ['-loop', '1', '-framerate', f'{timeline.fps_num}/{timeline.fps_den}',
                                 '-t', f'{length - skip:.9f}', '-i', str(picture)]
                        pop = min(0.2, length / 2)
                        graph.append(f'[{index}:v]format=rgba,setpts=PTS+{skip:.9f}/TB,fade=t=in:st=0:d={pop:.9f}:alpha=1,'
                                     f'setpts=PTS-{skip:.9f}/TB+{placed:.9f}/TB[v{layer}]')
                        graph.append(f'[{base}][v{layer}]overlay=eof_action=pass:enable=\'gte(t,{on:.9f})*lt(t,{off:.9f})\'[base{layer}]')
                        base = f'base{layer}'
                        index += 1
                    elif track.kind == 'text' and clip.text:
                        textfile = Path(tmp) / f'text{layer}.txt'
                        layer += 1
                        visible = f'enable=\'gte(t,{on:.9f})*lt(t,{off:.9f})\''
                        common = f'[{base}]drawtext=textfile={_escape_filter_path(textfile)}:expansion=none'
                        # Always LF: drawtext draws the CR of a CRLF as an extra blank line.
                        if clip.style:
                            size = clip.style.get('size') if clip.style.get('size') in TEXT_SCALE else 'medium'
                            x, y = float(clip.style.get('x', 0.5)), float(clip.style.get('y', 0.78))
                            bold = Path(self.font).with_name('arialbd.ttf')
                            font = bold if bold.is_file() else self.font
                            colour = TEXT_COLORS.get(clip.style.get('color'), 'white')
                            px = _font_px(self.width, self.height, TEXT_SCALE[size])
                            border = max(2, round(min(self.width, self.height) / 300))
                            lines = _fit_lines(clip.text, font, px, self.width * 0.9 - 2 * border)
                            textfile.write_text(lines, encoding='utf-8', newline='\n')
                            graph.append(f'{common}:fontfile={_escape_filter_path(font)}:text_align=C:line_spacing=6'
                                         f':fontcolor={colour}:fontsize={px}:borderw={border}:bordercolor=black'
                                         f':x=\'max(10,min(w-text_w-10,w*{x:.4f}-text_w/2))\''
                                         f':y=\'max(10,min(h-text_h-10,h*{y:.4f}-text_h/2))\':{visible}[base{layer}]')
                        else:
                            # A caption is sized and placed by the picture under it, not by the whole canvas.
                            left, top, across, down = self._picture_rect(timeline, clip)
                            whole = (left, top, across, down) == (0, 0, self.width, self.height)
                            px = _font_px(self.width, self.height) if whole and self.width >= self.height \
                                else caption_layout.font_px((left, top, across, down), (self.width, self.height))
                            pad = max(6, round(px / 5))
                            lines = _fit_lines(clip.text, self.font, px, across * 0.9 - 2 * pad)
                            textfile.write_text(lines, encoding='utf-8', newline='\n')
                            if whole:
                                place = f':x=(w-text_w)/2:y=\'min(h*0.78,h-text_h-{pad}-h*0.04)\''
                            else:  # centred on the picture, in its lower part, and never above the canvas
                                place = (f':x=\'{left}+({across}-text_w)/2\''
                                         f':y=\'max({pad},min({top + down * 0.78:.1f},{top + down * 0.96 - pad:.1f}-text_h))\'')
                            graph.append(f'{common}:fontfile={_escape_filter_path(self.font)}:fontcolor=white:fontsize={px}'
                                         f':text_align=C:line_spacing=6{place}'
                                         f':box=1:boxcolor=black@0.5:boxborderw={pad}:{visible}[base{layer}]')
                        base = f'base{layer}'
            graph.append(f'[{base}]eq=brightness={self.brightness/100:.3f}:contrast={1+self.contrast/100:.3f}:saturation={1+self.saturation/50:.3f}[graded]')
            base = 'graded'
            # Playback speed is part of the one export graph (one encode): retime the finished
            # picture, then the finished mix. atempo takes 0.5-2.0 per instance, the allowed range.
            speed = self.speed if frame is None else 1.0
            if speed != 1.0:
                graph.append(f'[{base}]setpts=PTS/{speed:.6f}[timed]')
                base = 'timed'
            if audio:
                tempo = f',atempo={speed:.6f}' if speed != 1.0 else ''
                # Sources are summed at full level (normalize=0 keeps a lone voice as loud as it was), so
                # music under speech can exceed full scale: a limiter catches those peaks instead of
                # letting the encoder clip them. Quieter material passes through unchanged.
                graph += audio_polish.mix(voices, music, self.audio, LIMITER, tempo)
            # The graph grows with every clip; passed inline it overflows the Windows command line
            # (32,767 chars). ffmpeg >= 7 reads it from a file via -/filter_complex. The temp dir
            # outlives the ffmpeg call below.
            script = Path(tmp) / 'graph.txt'
            script.write_text(';\n'.join(graph), encoding='utf-8', newline='\n')
            args += ['-/filter_complex', str(script), '-map', f'[{base}]']
            if frame is not None:
                args += ['-frames:v', '1', '-an', str(output)]
            else:
                if audio:
                    args += ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k']
                quality = ['-preset', 'ultrafast', '-crf', '24', '-g', '15'] if self.fast else []
                if speed != 1.0:  # retimed frames would otherwise round up to an extra frame or two
                    args += ['-t', f'{total / fps / speed:.9f}']
                args += ['-r', f'{timeline.fps_num}/{timeline.fps_den}', '-c:v', 'libx264', *quality, '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
            if on_progress is None:
                result = self.media.run(args, text=True)
            else:  # ffmpeg reports seconds of output; the caller gets the share of the whole export
                length = total / fps / speed
                result = self.media.run(args, text=True,
                                        on_progress=lambda seconds: on_progress(min(1.0, seconds / length)))
            if result.returncode:
                raise RuntimeError('\n'.join(result.stderr.splitlines()[-12:]))
            if not Path(output).is_file():
                raise RuntimeError('FFmpeg did not create output')
            return str(output)

    def preview(self, timeline, frame, output):
        return self._render(timeline, output, frame=frame)

    def export(self, timeline, output, on_progress=None):
        """Renders next to the target and moves it into place only when complete, so a failed or
        cancelled export (RenderCancelled from the media service) leaves an existing file intact.
        on_progress(fraction 0..1) is called from a helper thread as the render advances."""
        partial = partial_output_path(output)
        if output_overwrites_source(timeline, output) or output_overwrites_source(timeline, partial):
            raise ValueError('Çıktı dosyası kaynak medyayla aynı olamaz.')
        try:
            self._render(timeline, partial, on_progress=on_progress)
            os.replace(partial, output)
        except BaseException:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return str(output)
