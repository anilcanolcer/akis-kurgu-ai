"""Export without re-encoding when the edit is nothing but cuts of one video.

Copying the compressed picture and sound takes seconds instead of minutes and loses no quality at all.
The price: a copy can only start on a keyframe, so each kept piece may begin a little before its cut
(usually well under two seconds). The user is told and chooses; anything that changes the picture or the
sound (text, colour, speed, a different canvas, sound clean-up…) makes the edit ineligible, and the
normal export is used instead.
"""
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from akis.media_service import MediaService, RenderCancelled
from akis.timeline_model import Timeline
from akis.timeline_render import output_overwrites_source, partial_output_path

COPYABLE = ('.mp4', '.mov', '.m4v')   # containers whose streams go into an .mp4 unchanged
QUESTION = ('Bu kurgu yalnızca kesimlerden oluşuyor. Yeniden kodlamadan, hızlı dışa aktarılsın mı?\n\n'
            'Kalite hiç düşmez ve işlem çok daha kısa sürer. Kesim noktaları en yakın anahtar kareye '
            'kayabilir; her parçanın başında genellikle iki saniyeden kısa bir fazlalık kalabilir ve '
            'birleşme yerinde tek bir kare atlanabilir.\n\n'
            '“Hayır” derseniz olağan (kare hassasiyetli) dışa aktarma yapılır.')


def plan(timeline, adjustments, canvas, media):
    """The pieces to copy as [(source, start seconds, length seconds)], or None when a copy would not
    give the same result as the normal export."""
    if any(adjustments.get(name, 0) for name in ('brightness', 'contrast', 'saturation')):
        return None
    if adjustments.get('speed', 1.0) != 1.0 or adjustments.get('audio'):
        return None
    used = [track for track in timeline.tracks if track.clips and not track.muted]
    if len(used) != 1 or used[0].kind != 'video':
        return None
    clips = sorted(used[0].clips, key=lambda clip: clip.start)
    source = clips[0].source
    if Path(source).suffix.lower() not in COPYABLE or not Path(source).is_file():
        return None
    cursor = 0
    for clip in clips:
        if clip.source != source or clip.start != cursor or clip.volume != 1.0 or clip.style or clip.keyframes:
            return None
        cursor = clip.end
    try:
        if tuple(media.dimensions(source)) != tuple(canvas) or media.is_hdr(source) is True:
            return None
    except Exception:  # a file that cannot be probed is not a candidate
        return None
    fps = timeline.fps_num / timeline.fps_den
    pieces = []
    for clip in clips:
        if pieces and pieces[-1][1] + pieces[-1][2] == clip.source_in:  # a split that was never cut: one piece
            pieces[-1][2] += clip.length
        else:
            pieces.append([source, clip.source_in, clip.length])
    return [(path, first / fps, length / fps) for path, first, length in pieces]


def export(pieces, output, media, on_progress=None):
    """Copy the pieces into `output`. Written next to the target and moved into place only when complete."""
    partial = partial_output_path(output)
    report = on_progress or (lambda fraction: None)
    try:
        with tempfile.TemporaryDirectory(prefix='akis_copy_') as folder:
            parts = []
            for index, (source, start, length) in enumerate(pieces):
                part = Path(folder) / f'part{index}.mp4'
                result = media.run(['-y', '-ss', f'{start:.6f}', '-i', source, '-t', f'{length:.6f}', '-map', '0:v:0',
                                    '-map', '0:a?', '-c', 'copy', '-avoid_negative_ts', 'make_zero', part], text=True)
                if result.returncode or not part.is_file():
                    raise RuntimeError('\n'.join((result.stderr or '').splitlines()[-6:]) or 'FFmpeg parça üretemedi')
                parts.append(part)
                report((index + 1) / (len(pieces) + 1))
            listing = Path(folder) / 'parts.txt'
            listing.write_text(''.join(f"file '{part.as_posix()}'\n" for part in parts), encoding='utf-8')
            result = media.run(['-y', '-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy', '-movflags', '+faststart',
                                partial], text=True)
            if result.returncode or not Path(partial).is_file():
                raise RuntimeError('\n'.join((result.stderr or '').splitlines()[-6:]) or 'FFmpeg çıktı üretemedi')
        os.replace(partial, output)
        report(1.0)
    except BaseException:
        try:
            Path(partial).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return str(output)


class FastExportWorker(QThread):
    """Same signals as TimelineRenderWorker, so the window treats both exports alike."""
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)

    def __init__(self, timeline, pieces, output, executable):
        super().__init__()
        self.timeline = Timeline.from_dict(timeline.to_dict())
        self.pieces, self.output = list(pieces), output
        self.media = MediaService(executable)

    def cancel(self):
        self.media.cancel()

    def run(self):
        try:
            if output_overwrites_source(self.timeline, self.output):
                raise ValueError('Çıktı dosyası kaynak medyayla aynı olamaz.')
            export(self.pieces, self.output, self.media, lambda fraction: self.progress.emit(int(fraction * 100)))
            self.completed.emit(self.output)
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.media.cancelled:
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
