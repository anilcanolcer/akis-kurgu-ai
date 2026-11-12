"""Checks made on the timeline just before an export, so surprises are named before minutes are spent.

Only things read straight off the timeline: no decoding, nothing slow. Each finding is one Turkish
sentence; none of them blocks the export (the user may want exactly that), they are only shown first.
"""
from pathlib import Path

MIN_GAP_SECONDS = 0.1     # shorter holes are rounding at cut points, not something a viewer notices
MAX_LISTED = 3


def _seconds(frames, fps):
    return f'{frames / fps:.1f}'.replace('.', ',')


def _clock(frames, fps):
    total = frames / fps
    return f'{int(total // 60)}:{total % 60:04.1f}'.replace('.', ',')


def missing_files(timeline, exists=None):
    exists = exists or (lambda path: Path(path).is_file())
    seen = []
    for track in timeline.tracks:
        if track.muted:
            continue
        for clip in track.clips:
            if clip.source and clip.source not in seen and not exists(clip.source):
                seen.append(clip.source)
    return seen


def picture_gaps(timeline):
    """(start, end) frame ranges, up to the last picture frame, where no video or overlay clip is shown."""
    spans = sorted((clip.start, clip.end) for track in timeline.tracks if track.kind in ('video', 'overlay') and not track.muted
                   for clip in track.clips)
    gaps, cursor = [], 0
    for start, end in spans:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    return gaps, cursor


def check(timeline, *, exists=None):
    """Findings as Turkish sentences, most serious first; [] when nothing stands out."""
    fps = timeline.fps_num / timeline.fps_den
    findings = []
    missing = missing_files(timeline, exists)
    if missing:
        names = ', '.join(Path(path).name for path in missing[:MAX_LISTED]) + (' …' if len(missing) > MAX_LISTED else '')
        findings.append(f'{len(missing)} kaynak dosya bulunamıyor ({names}); dışa aktarma bu yüzden durur.')
    gaps, picture_end = picture_gaps(timeline)
    gaps = [(a, b) for a, b in gaps if (b - a) / fps >= MIN_GAP_SECONDS]
    if gaps and picture_end:
        places = ', '.join(_clock(a, fps) for a, _ in gaps[:MAX_LISTED]) + (' …' if len(gaps) > MAX_LISTED else '')
        total = sum(b - a for a, b in gaps)
        findings.append(f'Videoda {len(gaps)} yerde görüntü yok (toplam {_seconds(total, fps)} sn, {places}); '
                        'buralar siyah görünecek.')
    whole = max((clip.end for track in timeline.tracks if not track.muted for clip in track.clips), default=0)
    if picture_end and whole - picture_end >= MIN_GAP_SECONDS * fps:
        findings.append(f'Görüntü bittikten sonra {_seconds(whole - picture_end, fps)} sn daha yazı ya da ses sürüyor; '
                        'bu bölüm siyah ekranla dışa aktarılır.')
    return findings


def question(findings):
    """The text of the "export anyway?" question."""
    lines = '\n'.join(f'• {finding}' for finding in findings)
    return f'Dışa aktarmadan önce bilmeniz gerekenler:\n\n{lines}\n\nYine de dışa aktarılsın mı?'
