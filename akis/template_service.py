"""Practical starting points built from the application's native timeline primitives."""
from dataclasses import dataclass
from akis.timeline_model import Track, Clip

@dataclass(frozen=True)
class Template:
    name: str
    ratio: str
    seconds: int
    tracks: tuple
    title: str
    style: str
    tempo: str

TEMPLATES = (
    Template('Reels / TikTok hızlı kesim', '9:16', 30, (('video','Ana video'),('video','B-roll'),('audio','Müzik'),('text','Başlık / altyazı')), 'Dikkat çekici başlık', 'Enerjik', 'Hızlı'),
    Template('YouTube Shorts', '9:16', 45, (('video','Ana video'),('video','Detaylar'),('audio','Ses'),('text','Başlık / altyazı')), 'Kısa ve net başlık', 'Minimal', 'Dinamik'),
    Template('Ürün tanıtım', '1:1', 30, (('video','Ürün'),('video','Detay'),('audio','Müzik'),('text','Ürün adı')), 'Ürün adı', 'Sinematik', 'Orta'),
    Template('Eğitim / anlatım', '16:9', 120, (('video','Anlatım'),('video','Gösterim'),('audio','Seslendirme'),('text','Konu başlıkları')), 'Ders başlığı', 'Minimal', 'Orta'),
    Template('Vlog', '16:9', 180, (('video','Ana görüntü'),('video','B-roll'),('audio','Müzik'),('text','Bölüm başlıkları')), 'Bugünün hikâyesi', 'Sıcak', 'Orta'),
    Template('Müzik klibi', '16:9', 180, (('video','Performans'),('video','Ek görüntü'),('audio','Müzik'),('text','Şarkı adı')), 'Şarkı adı', 'Sinematik', 'Dinamik'),
    Template('Altyazılı konuşma', '9:16', 60, (('video','Konuşma'),('audio','Ses'),('text','Altyazılar')), 'Konuşma başlığı', 'Minimal', 'Orta'),
    Template('Basit slideshow', '16:9', 30, (('video','Görseller'),('audio','Müzik'),('text','Başlıklar')), 'Hikâyeniz', 'Yumuşak', 'Yavaş'),
)
STYLES = {'Sinematik': (-4, 15, -10), 'Enerjik': (2, 10, 20), 'Minimal': (0, 0, 0), 'Sıcak': (5, 5, 10), 'Siyah-Beyaz': (0, 10, -50), 'Yumuşak': (5, -10, -10)}
TEMPOS = {'Yavaş': '0.75×', 'Orta': '1.00×', 'Hızlı': '1.25×', 'Dinamik': '1.50×'}

def apply_template(timeline, template):
    """Add missing named tracks and a short editable title without touching existing clips."""
    for kind, name in template.tracks:
        if not any(t.kind == kind and t.name == name for t in timeline.tracks):
            timeline.tracks.append(Track(kind, name))
    title_track = next(t for t in timeline.tracks if t.kind == 'text' and t.name == next(n for k, n in template.tracks if k == 'text'))
    start = max((c.end for c in title_track.clips), default=0)
    title_track.add(Clip(source='', start=start, length=round(3 * timeline.fps_num / timeline.fps_den), text=template.title))
    return timeline
