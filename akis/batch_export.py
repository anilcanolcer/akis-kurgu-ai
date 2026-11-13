"""Process a list of videos the same way and export each: pauses cut, a saved template, the project's look.

Each video becomes its own timeline (at its own frame rate), optionally gets a saved template's tracks and
title (akis.user_templates) and its silences cut with the default settings (akis.silence_cut); it is then
exported with the colour, speed and sound settings and the canvas of the open project. One file failing
does not stop the others; the result lists what worked and what did not.
"""
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from akis import edit_plan, silence_cut, timeline_service, user_templates
from akis.media_service import MediaService, RenderCancelled
from akis.timeline_model import Timeline
from akis.timeline_render import TimelineRenderer, output_overwrites_source

SUFFIX = '_akis'


def output_for(source, folder):
    return str(Path(folder) / f'{Path(source).stem}{SUFFIX}.mp4')


def build(source, media, *, cut_silences=False, template=None, measure=silence_cut.measure):
    """The timeline for one video, ready to export."""
    seconds = media.duration(source)
    rate = media.frame_rate(source) or (30, 1)
    timeline = Timeline.from_legacy({'source': source, 'start': 0, 'end': seconds}, rate)
    if template:
        user_templates.apply(timeline, template)
    if cut_silences:
        sources = [{'path': source, 'duration': seconds}]
        segments = edit_plan.current_segments(timeline, sources)
        levels = measure(media.executable, source)
        spans = silence_cut.silent_spans(levels, silence_cut.DEFAULT_THRESHOLD_DB, silence_cut.DEFAULT_MIN_SILENCE)
        kept, cuts = silence_cut.keep_segments(segments, {0: spans}, silence_cut.DEFAULT_MARGIN)
        if cuts:
            timeline = edit_plan.apply_plan(timeline, sources, {'segments': kept})
    return timeline


class BatchExportWorker(QThread):
    """completed(report): one line per video; failed only when nothing at all could start."""
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)

    def __init__(self, sources, folder, executable, *, aspect, profile, adjustments=None,
                 cut_silences=False, template=None, say=str):
        super().__init__()
        self.sources, self.folder = list(sources), folder
        self.aspect, self.profile = aspect, profile
        self.adjustments = dict(adjustments or {})
        self.cut_silences, self.template = cut_silences, template
        self.say = say
        self.media = MediaService(executable)
        self.results = []          # (source, output or None, error or '')
        self._percent = None

    def cancel(self):
        self.media.cancel()

    def _report(self, index, fraction):
        percent = int((index + fraction) / len(self.sources) * 100)
        if percent != self._percent:
            self._percent = percent
            self.progress.emit(percent)

    def run(self):
        try:
            for index, source in enumerate(self.sources):
                output = output_for(source, self.folder)
                try:
                    timeline = build(source, self.media, cut_silences=self.cut_silences, template=self.template)
                    if output_overwrites_source(timeline, output):
                        raise ValueError(self.say('Çıktı dosyası kaynak medyayla aynı olamaz.'))
                    canvas = timeline_service.output_canvas_size(self.aspect, timeline, self.media, self.profile)
                    renderer = TimelineRenderer(self.media, canvas, **self.adjustments)
                    renderer.export(timeline, output, on_progress=lambda f, index=index: self._report(index, f))
                    self.results.append((source, output, ''))
                except RenderCancelled:
                    raise
                except Exception as exc:
                    if self.media.cancelled:
                        raise RenderCancelled() from exc
                    self.results.append((source, None, str(exc).splitlines()[-1] if str(exc) else type(exc).__name__))
                self._report(index, 1.0)
            self.completed.emit(self.report())
        except RenderCancelled:
            self.cancelled.emit()

    def report(self):
        done = [Path(output).name for _, output, _ in self.results if output]
        failed = [(Path(source).name, error) for source, output, error in self.results if not output]
        lines = [self.say('{done} / {total} video dışa aktarıldı:').format(done=len(done), total=len(self.results)),
                 str(self.folder), '']
        lines += [f'✓ {name}' for name in done]
        lines += [f'✕ {name}: {error}' for name, error in failed]
        return '\n'.join(lines)
