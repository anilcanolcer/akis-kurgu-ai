"""Practical starting points built from the application's native timeline primitives."""
from dataclasses import dataclass
from akis.timeline_model import Track, Clip

TITLE_SECONDS = 3


@dataclass(frozen=True)
class Template:
    name: str
    ratio: str
    seconds: int
    tracks: tuple
    title: str
    style: str
    tempo: str
    summary: str = ''   # one sentence: what the template is for
    platforms: str = ''  # where the result is usually published


TEMPLATES = (
    Template('Reels / TikTok hızlı kesim', '9:16', 30, (('video','Ana video'),('video','B-roll'),('audio','Müzik'),('text','Başlık / altyazı')), 'Dikkat çekici başlık', 'Enerjik', 'Hızlı',
             'İlk saniyede dikkat çeken, hızlı kesimli kısa dikey video.', 'Instagram Reels · TikTok'),
    Template('YouTube Shorts', '9:16', 45, (('video','Ana video'),('video','Detaylar'),('audio','Ses'),('text','Başlık / altyazı')), 'Kısa ve net başlık', 'Minimal', 'Dinamik',
             'Tek bir fikri net anlatan, sade görünümlü dikey video.', 'YouTube Shorts'),
    Template('Ürün tanıtım', '1:1', 30, (('video','Ürün'),('video','Detay'),('audio','Müzik'),('text','Ürün adı')), 'Ürün adı', 'Sinematik', 'Orta',
             'Ürünü ve ayrıntılarını öne çıkaran kare tanıtım videosu.', 'Instagram gönderisi · Reklam'),
    Template('Eğitim / anlatım', '16:9', 120, (('video','Anlatım'),('video','Gösterim'),('audio','Seslendirme'),('text','Konu başlıkları')), 'Ders başlığı', 'Minimal', 'Orta',
             'Anlatım ile ekran gösterimini konu başlıklarıyla birleştiren ders videosu.', 'YouTube · Kurs'),
    Template('Vlog', '16:9', 180, (('video','Ana görüntü'),('video','B-roll'),('audio','Müzik'),('text','Bölüm başlıkları')), 'Bugünün hikâyesi', 'Sıcak', 'Orta',
             'Günlük anlatımı ara görüntüler ve bölüm başlıklarıyla toparlayan video.', 'YouTube'),
    Template('Müzik klibi', '16:9', 180, (('video','Performans'),('video','Ek görüntü'),('audio','Müzik'),('text','Şarkı adı')), 'Şarkı adı', 'Sinematik', 'Dinamik',
             'Performans görüntüsünü müziğin ritmine göre kesmek için sinematik düzen.', 'YouTube'),
    Template('Altyazılı konuşma', '9:16', 60, (('video','Konuşma'),('audio','Ses'),('text','Altyazılar')), 'Konuşma başlığı', 'Minimal', 'Orta',
             'Kameraya konuşulan videolar için altyazı odaklı sade düzen.', 'Reels · Shorts · TikTok'),
    Template('Basit slideshow', '16:9', 30, (('video','Görseller'),('audio','Müzik'),('text','Başlıklar')), 'Hikâyeniz', 'Yumuşak', 'Yavaş',
             'Fotoğraf ve kısa klipleri müzik eşliğinde sakin bir tempoyla sıralar.', 'YouTube · Sunum'),
)
STYLES = {'Sinematik': (-4, 15, -10), 'Enerjik': (2, 10, 20), 'Minimal': (0, 0, 0), 'Sıcak': (5, 5, 10), 'Siyah-Beyaz': (0, 10, -50), 'Yumuşak': (5, -10, -10)}
TEMPOS = {'Yavaş': '0.75×', 'Orta': '1.00×', 'Hızlı': '1.25×', 'Dinamik': '1.50×'}


def missing_tracks(timeline, template):
    """The (kind, name) tracks of `template` that `timeline` does not have yet."""
    return [(kind, name) for kind, name in template.tracks
            if not any(t.kind == kind and t.name == name for t in timeline.tracks)]


def apply_template(timeline, template):
    """Add missing named tracks and a short editable title without touching existing clips.

    Tracks are drawn in list order, so new video and audio tracks go below the first text track:
    appended after it, B-roll would cover the titles already on that track.
    """
    for kind, name in missing_tracks(timeline, template):
        first_text = next((i for i, t in enumerate(timeline.tracks) if t.kind == 'text'), len(timeline.tracks))
        timeline.tracks.insert(len(timeline.tracks) if kind == 'text' else first_text, Track(kind, name))
    title_track = next(t for t in timeline.tracks if t.kind == 'text' and t.name == next(n for k, n in template.tracks if k == 'text'))
    start = max((c.end for c in title_track.clips), default=0)
    title_track.add(Clip(source='', start=start, length=round(TITLE_SECONDS * timeline.fps_num / timeline.fps_den), text=template.title))
    return timeline
