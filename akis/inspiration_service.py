"""Creative video ideas (pure Python): hook, shot list and a ready prompt for the prompt-driven editor."""
import random
from dataclasses import dataclass

from akis.template_service import TEMPLATES

_HIK, _URUN, _EGT, _VLOG, _TREND, _SIN = 'Hikâye anlatımı', 'Ürün / tanıtım', 'Eğitim', 'Vlog / günlük', 'Trend / eğlence', 'Sinematik'
_REELS, _SHORTS, _UTANITIM, _EGITIM, _VLOGT, _KLIP, _ALTYAZI, _SLAYT = (t.name for t in TEMPLATES)


@dataclass(frozen=True)
class Idea:
    key: str
    title: str
    category: str
    platform: str
    hook: str
    description: str
    shots: tuple
    prompt: str
    template: str = ''


def _i(key, title, category, platform, hook, description, shots, prompt, template=''):
    return Idea(key, title, category, platform, hook, description, tuple(shots), prompt, template)


IDEAS = (
    _i('sonu-basa', 'Sonu başa alan hikâye', _HIK, 'Reels / TikTok',
       'Videonun en çarpıcı karesiyle başla, sonra "Peki bu nasıl oldu?" diye geriye sar.',
       'Finali ilk saniyelere koyup izleyiciyi merak içinde sona kadar tutar.',
       ['0-3 sn: en etkileyici an', 'Geri sarma efekti ve başlık', 'Olayın başlangıcı', 'Gerilimin yükseldiği orta bölüm', 'Finalin tam hali'],
       'İlk 3 saniyeye videonun en çarpıcı anını koy, ardından olayı başından anlat. Sessizlikleri kes, geçişleri hızlı tut ve son sahnede finali tekrar göster.',
       _REELS),
    _i('bir-gunde', '24 saatte bir şehir', _HIK, 'YouTube Shorts',
       'Sabah 06:00 saat yazısıyla başla ve her saat başı kısa bir sahneye geç.',
       'Bir günü saat damgalı kısa sahnelerle sıkıştırarak anlatır.',
       ['06:00 uyanış ve ilk kahve', 'Öğleden önce yolculuk', 'Öğle arası lezzet kareleri', 'Akşam üstü altın saat', 'Gece ışıkları ve kapanış'],
       'Videoyu kronolojik sırayla kısa sahnelere böl, her sahnenin başına saat yazısı ekle, boş kısımları at ve toplam süreyi 45 saniyeye indir.',
       _SHORTS),
    _i('once-sonra', 'Önce / sonra dönüşümü', _HIK, 'Reels / TikTok',
       'Aynı kadrajı yan yana ya da ani bir kesmeyle "önce" ve "sonra" olarak göster.',
       'Dönüşümü tek bir net karşılaştırmayla anlatan, paylaşılabilir bir format.',
       ['"Önce" hali, sabit kadraj', 'Çalışma sürecinden hızlı kesitler', 'Ani geçiş efekti', '"Sonra" hali, aynı kadraj', 'Kısa tepki ya da sonuç yazısı'],
       'Başlangıç ve bitiş görüntülerini aynı kadrajla art arda koy, aradaki süreci hızlandırılmış kısa kesitlerle özetle ve en sona "sonra" karesini 3 saniye tut.',
       _REELS),
    _i('tek-plan-sir', 'Tek soru, tek sır', _HIK, 'Shorts',
       '"Kimsenin sana söylemediği şey şu…" diyerek doğrudan kameraya konuş.',
       'Merak uyandıran bir cümleyle başlayan, tek konuşmalı kısa anlatı.',
       ['Kameraya doğrudan merak cümlesi', 'Cümleyi destekleyen görsel', 'Asıl bilgi', 'Kısa örnek', 'Soru ile kapanış'],
       'Konuşmadaki duraksamaları ve tekrarları kes, ilk cümleyi başa al, altyazıları büyük ve okunur ekle ve süreyi 40 saniyenin altında tut.',
       _ALTYAZI),
    _i('acilis-kutusu', 'Gizemli kutu açılışı', _URUN, 'Instagram',
       'Kapalı bir kutu, yavaş bir müzik ve elin kapağı kaldırdığı an.',
       'Ürünü bir sürpriz gibi sunarak ilk izlenimi güçlendirir.',
       ['Kapalı kutu, yakın plan', 'Kapağın açılışı', 'Ürünün ilk görünüşü', 'Detay kareleri', 'Ürün adı ve kısa not'],
       'Kutu açılışını yavaşlat, ürün göründüğü anda müziği vurgula, ardından detayları hızlı kesitlerle göster ve sonda ürün adını yaz.',
       _UTANITIM),
    _i('uc-ozellik', 'Üç özellik, üç saniye', _URUN, 'Reels / TikTok',
       'Üç numaralı özellikten geri sayarak başla.',
       'Ürünün üç güçlü yönünü ritimli kesmelerle sayar.',
       ['Başlık: 3 özellik', 'Özellik 3 kısa gösterim', 'Özellik 2 kısa gösterim', 'Özellik 1 en etkileyici', 'Çağrı: nereden alınır'],
       'Her özelliği 3 ila 4 saniyelik ayrı bir kesit yap, her birinin üstüne numara yaz, en güçlü özelliği sona bırak ve tempoyu yüksek tut.',
       _REELS),
    _i('paket-hikayesi', 'Siparişin yolculuğu', _URUN, 'Instagram',
       'Paketin hazırlanışından teslimata kadar küçük bir yolculuk.',
       'Küçük işletmeler için güven veren, arka plan odaklı bir tanıtım.',
       ['Ürünün hazırlanması', 'Paketleme detayı', 'Kargoya veriliş', 'Müşterinin açışı', 'Teşekkür kartı'],
       'Hazırlık ve paketleme sahnelerini sıcak renklerle birleştir, gereksiz bekleme anlarını kes ve sonda müşteri tepkisini göster.',
       _UTANITIM),
    _i('musteri-yorumu', 'Müşteri sözüyle tanıtım', _URUN, 'YouTube',
       'Bir müşteri cümlesini büyük yazıyla göster, sonra ürünü o cümleyle eşleştir.',
       'Yorumları görüntülerle eşleştirerek sosyal kanıt oluşturur.',
       ['Yorum cümlesi büyük yazıyla', 'Ürün kullanımı', 'İkinci yorum', 'Detay görüntüsü', 'Marka kapanışı'],
       'Konuşma kayıtlarından en güçlü cümleleri seç, her cümleyi ilgili ürün görüntüsüyle eşleştir ve altyazı ekle.',
       _UTANITIM),
    _i('60-sn-ders', '60 saniyede bir kavram', _EGT, 'Shorts',
       '"Bunu 60 saniyede öğreneceksin." cümlesiyle sayaç başlat.',
       'Tek bir kavramı sayaçla sınırlı sürede anlatan ders.',
       ['Sayaç ve soru', 'Tanım, tek cümle', 'Basit örnek', 'Sık yapılan hata', 'Özet kartı'],
       'Tek konuya odaklan, her konuşma bölümüne kısa başlık ekle, duraksamaları kes ve toplam süreyi 60 saniyeye sığdır.',
       _SHORTS),
    _i('adim-adim', 'Adım adım nasıl yapılır', _EGT, 'YouTube',
       'Bitmiş sonucu önce göster, sonra "şimdi birlikte yapalım" de.',
       'Önce sonucu gösterip ardından numaralı adımlarla ilerleyen eğitim.',
       ['Bitmiş sonuç', 'Gerekli malzemeler', 'Adım 1', 'Adım 2', 'Adım 3 ve son kontrol', 'Özet ve soru daveti'],
       'Sonucu başa koy, her adımı numaralı başlıkla ayır, bekleme ve yanlış başlangıçları kes ve önemli yerlerde ekranı yakınlaştır.',
       _EGITIM),
    _i('mit-gercek', 'Mit mi, gerçek mi?', _EGT, 'Shorts',
       '"Bunu hep yanlış biliyoruz." yazısıyla başla.',
       'Yaygın bir yanlışı çürüten, hızlı ve eğlenceli bir bilgi formatı.',
       ['Yanlış inanış yazısı', 'Kısa ters köşe', 'Gerçeğin kanıtı', 'Basit görsel açıklama', 'Doğru bilgi özeti'],
       'Mit cümlesini ekranda göster, ardından gerçeği net bir kesitle açıkla, altyazıları vurgulu yap ve tempoyu orta hızda tut.',
       _SHORTS),
    _i('ekran-kaydi', 'Ekran kaydı mini rehber', _EGT, 'YouTube',
       'Sorunu gösteren ekranla başla, çözümün adını başlık yap.',
       'Ekran kaydını sadeleştirip önemli tıklamaları vurgulayan kısa rehber.',
       ['Sorunun görüldüğü ekran', 'Menüye giriş', 'Ayarın değiştirilmesi', 'Sonucun görülmesi', 'İpucu kartı'],
       'Ekran kaydındaki bekleme anlarını kes, önemli tıklamaları yakınlaştır, konuşmayı altyazıyla destekle ve sonda kısa bir özet ver.',
       _EGITIM),
    _i('sabah-rutini', 'Sabah rutini, saniye saniye', _VLOG, 'Reels / TikTok',
       'Çalar saatin sesiyle başla ve rutini ritimli kesmelerle geç.',
       'Gündelik rutini müzikle senkron, temiz kesmelerle gösterir.',
       ['Çalar saat', 'Yatağı toplama', 'Kahve ya da kahvaltı', 'Hazırlanma', 'Kapıdan çıkış'],
       'Rutini müziğin ritmine göre kes, bekleme anlarını at, geçişleri hızlı yap ve en sona kapıdan çıkış karesini koy.',
       _REELS),
    _i('haftalik-ozet', 'Haftanın özeti', _VLOG, 'YouTube',
       'Pazartesiden pazara, her güne tek bir kare.',
       'Bir haftayı gün başlıklarıyla toparlayan sıcak bir vlog.',
       ['Pazartesi ilk kare', 'Haftanın zor anı', 'Haftanın komik anı', 'Hafta sonu', 'Gelecek hafta planı'],
       'Her güne kısa bir başlık koy, en güzel kareleri seç, sıcak renk tonu ver ve süreyi 2 dakikanın altında tut.',
       _VLOGT),
    _i('gezi-mini', 'Gezi: 5 durak, 1 video', _VLOG, 'YouTube',
       'Haritada beş durağı göster, ilk durağa kesme yap.',
       'Bir geziyi durak durak anlatan, kolay izlenen bir seyahat videosu.',
       ['Harita ve durak listesi', 'Durak 1 manzara', 'Durak 2 yemek', 'Durak 3 sürpriz', 'Durak 4-5 kısa kesit', 'Dönüş yolu'],
       'Duraklara ayır, her durağın başına yer adı yaz, en güzel manzara karelerini seç ve sonda tüm durakları hızlı bir özetle göster.',
       _VLOGT),
    _i('slayt-anilar', 'Fotoğraflardan anı filmi', _VLOG, 'Instagram',
       'En sevdiğin fotoğrafla başla, sonra kronolojik ilerle.',
       'Fotoğrafları müzik eşliğinde duygusal bir anı filmine çevirir.',
       ['Açılış fotoğrafı', 'Kronolojik seçki', 'Yakın plan yüzler', 'Komik an', 'Teşekkür notu'],
       'Görselleri her biri 2-3 saniye olacak şekilde sırala, yumuşak geçişler ekle, müziğe uydur ve sonda kısa bir not yaz.',
       _SLAYT),
    _i('sessiz-meydan', 'Sessiz meydan okuma', _TREND, 'TikTok',
       'Hiç konuşmadan yalnızca yazı ve ses efektleriyle başla.',
       'Konuşmasız, yalnızca görüntü ve yazıyla ilerleyen eğlenceli bir akış.',
       ['Meydan okumanın yazısı', 'İlk deneme', 'Başarısız deneme', 'Başarılı deneme', 'Tepki karesi'],
       'Konuşmaları sessize al, deneme anlarını hızlandır, başarısızlıklara komik ses efekti yazısı ekle ve sonda başarılı denemeyi yavaş çekimle göster.',
       _REELS),
    _i('beklenti-gercek', 'Beklenti ve gerçek', _TREND, 'Reels / TikTok',
       'Ekranı ikiye böl: solda beklenti, sağda gerçek.',
       'Beklenti ile gerçeği karşılaştıran, çok paylaşılan komik format.',
       ['Beklenti başlığı', 'Mükemmel hayal', 'Gerçek başlığı', 'Komik gerçek', 'Kısa son tepki'],
       'Beklenti ve gerçek sahnelerini art arda yerleştir, her birinin üstüne başlık yaz, ses efektlerini vurgula ve süreyi 20 saniyeye indir.',
       _REELS),
    _i('hizli-tepki', 'Hızlı tepki dizisi', _TREND, 'TikTok',
       'Aynı olaya art arda farklı tepkiler.',
       'Kısa tepki karelerini ritimli biçimde dizerek mizah yaratır.',
       ['Olayın kendisi', 'Tepki 1', 'Tepki 2', 'Tepki 3', 'En komik tepki'],
       'Her tepkiyi 1-2 saniyeye kırp, tekrarlayan kısımları sil, en komik tepkiyi sona koy ve zoom vurguları ekle.',
       _REELS),
    _i('altin-saat', 'Altın saat şiiri', _SIN, 'YouTube',
       'Güneşin ufka değdiği yavaş bir kareyle başla.',
       'Doğal ışığa ve yavaş hareketlere dayanan, sakin bir görsel şiir.',
       ['Geniş manzara', 'Işığın detayı', 'İnsan siluet', 'Yavaş kamera hareketi', 'Kararan kapanış'],
       'Sinematik renk stili uygula, yavaş geçişler kullan, konuşmayı ve gürültüyü azalt, müziği öne çıkar ve sonda yavaşça karart.',
       _KLIP),
    _i('sinematik-fragman', 'Kişisel fragman', _SIN, 'YouTube',
       '"Bu yaz her şey değişecek." gibi bir fragman cümlesi.',
       'Sıradan görüntüleri film fragmanı ritmiyle birleştirir.',
       ['Fragman cümlesi', 'Karakter tanıtımı', 'Gerilim kareleri', 'Hızlanan kesmeler', 'Ad ve tarih kartı'],
       'Görüntüleri fragman ritmiyle kes, gerilimi kademeli artır, sinematik renk uygula ve sonda başlık kartı göster.',
       _KLIP),
    _i('yagmur-sehir', 'Yağmurlu şehir', _SIN, 'Reels / TikTok',
       'Camdaki damlaların odaktan çıkıp ışıklara döndüğü bir kare.',
       'Atmosfer odaklı, konuşmasız ve ritmik bir şehir gecesi videosu.',
       ['Cam üstünde damlalar', 'Sokak ışıkları', 'Yansımalar', 'Yürüyen insanlar', 'Kapanış karesi'],
       'Soğuk ve sinematik renk ver, kısa kesitleri müziğin vuruşlarıyla birleştir ve geçişleri yumuşat.',
       ''),
    _i('merak-sorusu', 'Soruyla başlayan video', _EGT, 'Instagram',
       'İlk karede büyük bir soru işareti ve cevabın ipucu.',
       'Soruyu ilk sahnede sorup cevabı videonun sonuna saklayan bir merak formatı.',
       ['Soru ve ipucu', 'Tahmin zamanı', 'İpucu 2', 'Cevap öncesi sessizlik', 'Cevap ve açıklama'],
       'Soruyu ilk 3 saniyeye koy, cevabı en sona sakla, aradaki bölümleri kısa tut ve konuşmaları altyazıyla göster.',
       ''),
)


def categories():
    seen = []
    for idea in IDEAS:
        if idea.category not in seen:
            seen.append(idea.category)
    return seen


def _fold(text):
    """Turkish-aware, case-insensitive form: İ/I/ı collapse to one letter so 'ILHAM', 'ilham' and 'İlham' match."""
    return (text or '').replace('İ', 'i').replace('I', 'ı').lower().replace('ı', 'i')


def ideas(category=None, query=''):
    needle = _fold(query).strip()
    return [idea for idea in IDEAS
            if (not category or idea.category == category)
            and (not needle or needle in _fold(f'{idea.title} {idea.hook} {idea.description}'))]


def random_idea(category=None, rng=None):
    pool = ideas(category)
    return (rng or random).choice(pool) if pool else None


def template_for(idea):
    return next((t for t in TEMPLATES if idea and t.name == idea.template), None)
