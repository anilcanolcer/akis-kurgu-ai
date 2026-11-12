<p align="center"><img src="https://raw.githubusercontent.com/anilcanolcer/akis-kurgu-ai/main/docs/banner.svg" alt="Akış Kurgu AI — yapay zekâ destekli, yerel öncelikli video düzenleyici" width="100%"></p>

<p align="center">
  <a href="https://github.com/anilcanolcer/akis-kurgu-ai/releases/latest"><img alt="Son sürüm" src="https://img.shields.io/github/v/release/anilcanolcer/akis-kurgu-ai?label=s%C3%BCr%C3%BCm&color=8b6aff"></a>
  <a href="https://github.com/anilcanolcer/akis-kurgu-ai/actions/workflows/windows-build.yml"><img alt="Derleme" src="https://img.shields.io/github/actions/workflow/status/anilcanolcer/akis-kurgu-ai/windows-build.yml?branch=main&label=derleme"></a>
  <a href="LICENSE"><img alt="Lisans: GPL-3.0" src="https://img.shields.io/badge/lisans-GPL--3.0-4fe1c0"></a>
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%2F%2011-5b3be0">
</p>

<p align="center"><b>Ne istediğini yaz, Akış kurgulasın.</b><br>Windows için Türkçe ve İngilizce, çok izli video düzenleyici. Kurgu ve dışa aktarma bilgisayarınızda yapılır; yapay zekâ yalnızca siz başlattığınızda, kendi anahtarınızla çalışır.</p>

<p align="center"><a href="https://github.com/anilcanolcer/akis-kurgu-ai/releases/latest/download/AkisKurguAI-Setup.exe"><b>⬇ Windows kurucusunu indir</b></a></p>

![Akış Kurgu AI düzenleyicisi: önizleme, çok izli zaman çizelgesi ve AI kurgu paneli](https://raw.githubusercontent.com/anilcanolcer/akis-kurgu-ai/main/docs/editor-demo.png)

## Öne çıkanlar

| | |
| --- | --- |
| **İstekle kurgu** | "Sessizlikleri kes, en çarpıcı anı başa al, altyazı ekle" yazın; plan uygulanır, beğenmezseniz tek adımda geri alınır. B-roll, başlık ve müzik izleriniz korunur. |
| **Hikâye Stüdyosu** | Gemini ile öncülden hikâye künyesi ve sahneler; sahnenin görseli (Nano Banana) ve kısa videosu (Omni Flash) üretilip zaman çizelgesine eklenir. |
| **Çok izli zaman çizelgesi** | Video, ses, metin ve katman izleri; bölme, kırpma, tüm izleri kaydıran ripple silme, geri al / yinele (Ctrl+Z, Ctrl+Y). |
| **Hızlı önizleme ve dışa aktarma** | Akıcı oynatma için arka planda proxy; H.264/AAC MP4, 4K profilleri, iptal edilebilir ve yarıda kalırsa eski dosyayı bozmayan dışa aktarma. |
| **Kaynağa sadık çıktı** | Proje videonun kendi kare hızında çalışır (24–60 fps); HDR telefon çekimleri SDR'ye ton eşlemesiyle çevrilir; birden fazla ses karışınca sınırlayıcı patlamayı önler. |
| **Altyazı ve seslendirme** | Yerel Whisper ile çevrimdışı konuşma dökümü ve altyazı; Windows sesleriyle metinden seslendirme. |
| **İlham ve Şablonlar** | 23 hazır video fikri (çekim listesi ve kurgu isteğiyle) ve platforma göre iz, oran, renk ve tempo şablonları. |
| **Sağlayıcı seçimi** | OpenAI, Anthropic, xAI, Google Gemini veya Cloudflare Workers AI; anahtarlar Windows Kimlik Bilgileri Yöneticisi'nde saklanır. |
| **Güvenli çalışma** | Otomatik kayıt ve çökme sonrası kurtarma, proje sürümleri, eski sürüme geri dönebilen güvenli güncelleme. |

## Ekran görüntüleri

| Hikâye Stüdyosu | İlham |
| --- | --- |
| ![Hikâye Stüdyosu: sahne listesi ve sahne metni](https://raw.githubusercontent.com/anilcanolcer/akis-kurgu-ai/main/docs/hikaye-studyosu.png) | ![İlham: yaratıcı video fikirleri, çekim listesi ve önerilen kurgu isteği](https://raw.githubusercontent.com/anilcanolcer/akis-kurgu-ai/main/docs/ilham.png) |

![Düzenle sekmesi: tuval oranı, hız ve renk ayarları](https://raw.githubusercontent.com/anilcanolcer/akis-kurgu-ai/main/docs/editor-adjustments.png)

*Görüntüler uygulamanın gerçek arayüzünden alınmıştır; örnek klipler FFmpeg ile üretilmiş renk geçişleridir, Hikâye Stüdyosu'ndaki metin örnek içeriktir.*

## Kurulum

1. [Kurucuyu indirin](https://github.com/anilcanolcer/akis-kurgu-ai/releases/latest/download/AkisKurguAI-Setup.exe) ve çalıştırın.
2. Başlat menüsünden **Akis Kurgu AI** uygulamasını açın.
3. Yerel Whisper modeli ilk kullanımda indirilir; sonrasında çevrimdışı çalışır.

Kurucu dijital olarak imzalı değildir; Windows veya güvenlik yazılımınız uyarı gösterebilir, kurumsal güvenlik ürünleri kurulumu engelleyebilir. Ayrıntılar ve indirilen dosyayı doğrulama: [docs/kod-imzalama.md](docs/kod-imzalama.md). Uygulama yeni sürümü kendisi önerir; güncelleme sırasında eski sürüm silinmez, bir sorun olursa geri yüklenir.

## Kısa kullanım

1. **Video ekle** ile dosya açın; ilk klip Video izine yerleşir.
2. **AI Kurgu** sekmesinde isteğinizi yazıp **Prompt ile kurgula** deyin ya da klipleri elle düzenleyin: seçin, sürükleyin, **Böl**, **Ripple sil**.
3. **İlham**'dan bir fikir veya **Şablonlar**'dan bir yapı seçerek başlayabilirsiniz.
4. **Düzenle** sekmesinden oran, renk ve hızı ayarlayın.
5. **Dışa aktar** ile MP4 oluşturun; projeyi `.akis.json` olarak kaydedin.

AI özellikleri için AI sekmesinde sağlayıcıyı seçip kendi API anahtarınızı girin. Cloudflare için anahtar `Hesap Kimliği:API anahtarı` biçimindedir. Gemini ile metin, görsel ve video çağrılarının ayrıntıları: [docs/gemini-hikaye.md](docs/gemini-hikaye.md).

### Bilinen sınırlamalar

- Akıcı oynatma, düzenlemeden kısa süre sonra arka planda hazırlanan proxy ile başlar; hazırlanana kadar önizleme kare kare ilerler.
- Hikâye Stüdyosu'nda görsel ve video üretimi Google tarafında ücretli kota gerektirir; ücretsiz katmandaki anahtarlar yalnızca metin üretebilir.
- Yerel Whisper dökümü ve Windows seslendirmesi başladıktan sonra iptal edilemez.
- Keyframe düzenleyici, dışa aktarma kuyruğu ve gelişmiş renk araçları yoktur; İngilizce çeviri eksiksiz değildir.
- Hesap eşitleme veya doğrudan yayınlama sunulmaz.

## Kaynak koddan çalıştırma

Python 3.12, Windows ve PATH üzerinde FFmpeg gerekir:

```powershell
git clone https://github.com/anilcanolcer/akis-kurgu-ai.git
cd akis-kurgu-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

```powershell
# Birim testleri, arayüz etkileşimleri ve gerçek FFmpeg testleri
python -m unittest discover -v
# FFmpeg PATH üzerinde veya AKIS_FFMPEG ile belirtilmişken Windows paketi
python -m PyInstaller AkisKurguAI.spec --noconfirm --clean
```

PyInstaller çıktısı `dist/AkisKurguAI/` klasöründedir. FFmpeg içeren dağıtımlarda ilgili FFmpeg derlemesinin lisans koşulları değerlendirilmelidir.

## Mimari ve katkı

- `akis/timeline_model.py`: kare tabanlı klip ve izler; `akis/frame_plan.py`: etkin katmanlar.
- `akis/timeline_service.py`, `akis/timeline_audio.py`: düzenleme, oynatma saati ve temel ses konumu eşleme.
- `akis/timeline_render.py`, `akis/render_worker.py`, `akis/preview_controller.py`, `akis/media_service.py`: ortak kompozisyon, önizleme iş sırası ve FFmpeg sınırı.
- `akis/multitrack_widget.py`, `main.py`: zaman çizelgesi arayüzü ve uygulama penceresi. Pencerede hâlâ ayrıştırılabilecek iş akışları vardır.
- `akis/project_service.py`: proje şeması ve kayıt; `logo.svg`, `logo.png`, `app.ico`: logo ve simge varlıkları.

Hata bildirirken Windows/Python/FFmpeg sürümlerini ve adımları paylaşın; API anahtarlarını veya kişisel medya dosyalarını depoya eklemeyin. Değişikliklerde mevcut proje dosyalarıyla uyumluluğu koruyun ve testleri çalıştırın.

Testler `tests/` klasöründedir; uygulama modülleri `akis/` altında bulunur.

## Özellik ayrıntıları

### AI kurgu ve öneriler

AI sekmesinde sağlayıcıyı (OpenAI, Anthropic Claude, xAI Grok, Google Gemini veya Cloudflare Workers AI) ve modeli seçin. Görsel giriş destekleyen bir model gerekir; model alanı düzenlenebilir. Her sağlayıcının anahtarı ayrı girilir ve “Anahtarı güvenli kaydet” ile Windows Kimlik Bilgileri Yöneticisi'nde saklanır; anahtarlar proje dosyasına yazılmaz. Videodan seçilen kareler seçtiğiniz sağlayıcıya gönderilir ve sağlayıcının ücretleri geçerli olabilir.

- **Prompt ile kurgula:** isteğinizi uygular; kesimler, yazılar, işaretler, renk, hız ve oran tek adımda değişir ve tek adımda geri alınır.
- **Öneri al:** platform, tempo, stil ve odağa göre en fazla üç öneri getirir. Seçilen öneri zaman çizelgesine başlangıç ve bitiş işaretleri ile yayın metnini ekler; klipleri kendisi kesmez.

### İlham ve Şablonlar

- **İlham:** 23 hazır video fikri. Her fikir çekim listesi ve hazır bir kurgu isteğiyle gelir; fikri seçince istek AI sekmesine yazılır, isterseniz eşleşen şablon da uygulanır.
- **Şablonlar:** sekiz başlangıç düzeni. Önerilen oranı, izleri, renk stilini ve tempoyu uygular; mevcut klipleri koruyarak iz ve üç saniyelik bir başlık ekler. Tempo tüm projenin oynatma ve dışa aktarma hızını değiştirir; önerilen süre otomatik kesme yapmaz. Boş projede önce şablonu seçip ardından video ekleyebilirsiniz. Şablonlar özgün tanımlardır; üçüncü taraf varlık içermez.

### Konuşma metni ve altyazı

AI sekmesinde **Yerel Whisper** ile model boyutunu seçin. İlk kullanımda “Modeli indir” internet bağlantısı gerektirir; model indikten sonra çevrimdışı çalışır. Sonuç yayın açıklamasına aktarılır; “Yerel altyazıyı timeline’a ekle” konuşmayı mevcut video kliplerine eşleyip bir altyazı izi oluşturur. Yeniden uygulandığında önceki altyazı izinin yerine geçer. Yerel döküm Türkçe konuşma için ayarlıdır.

API ile dökümde OpenAI, xAI veya Gemini seçilebilir; sonuç zamansız düz metindir. Gemini'de ses dosyası en fazla 14 MB olabilir. Claude için bu uygulamada döküm yoktur.

Kaynak koddan çalıştırırken yerel döküm için ek bağımlılıklar gerekir (kurucuda hazır gelir):

```powershell
python -m pip install -r requirements-local-ai.txt
```

### Zaman çizelgesi ve ses

- Cetvel ve klip taşıma yakın klip kenarlarına yapışır; klibin bitişini kırparken yapışma yoktur.
- Dalga biçimi ses içeren klipler için arka planda hesaplanır; kaynak başına ilk 60 dakika gösterilir.
- **Klip sesi** ile klip başına sabit ses düzeyi ayarlanır (en fazla %100). Ses zarfı ve otomatik kısma (ducking) yoktur.
- Birden fazla ses aynı anda çalıyorsa dışa aktarmada −1 dB sınırlayıcı uygulanır; tek ses olduğu gibi kalır.
- Yerel seslendirme Windows sistem sesiyle çevrimdışı WAV dosyası oluşturur; kullanılabilir dil ve sesler Windows kurulumuna bağlıdır.

### Görüntü

- Yeni proje, eklenen ilk videonun kare hızını alır (24, 25, 30, 50, 60 fps ve NTSC karşılıkları). Kayıtlı projeler kaydedildikleri hızda açılır; 60 fps üzerindeki ağır çekim kaynaklar 60 fps'e sabitlenir.
- HDR (PQ/HLG) kaynaklar önizlemede ve dışa aktarmada SDR'ye çevrilir.
- 4K profilleri sabit oranlarda 3840×2160 / 2160×3840 üretir; “Kaynak oranı”nda görüntü en fazla 4K'ya büyütülür.
- Duraklatılmış kare, önizleme alanının boyutuna göre üretilir; yakınlaştırınca (Ctrl + tekerlek) yeniden netleştirilir.

### Kurulum ve güncelleme

Kurucu varsayılan olarak `C:\Program Files\AkisKurguAI` klasörünü kullanır ve yönetici onayı ister; başka bir klasör seçebilirsiniz.

Uygulama açılışta yeni sürüme bakar. Yeni sürüm varsa sorar; kabul ederseniz kurucuyu indirir, SHA-256 özetini GitHub'daki sürüm bilgisiyle karşılaştırır ve kurucuyu görünür bir pencerede başlatır. Eski sürüm, yenisi tam olarak yazılana kadar silinmez; hata olursa geri yüklenir. Ayarlar ve projeler korunur. Özet karşılaştırması indirmenin bozulmadığını gösterir; dijital yayıncı imzası değildir.

GitHub, giriş yapmadan gelen isteklere bağlantı (IP) başına saatlik sınır uygular. 0.5.2'den itibaren bu sınır dolduğunda uygulama en son sürümü normal sürüm sayfalarından okur. 0.5.1 ve öncesinde bildirim gelmiyorsa güncel kurucuyu bir kez elle indirip çalıştırın; 0.4.2 ve öncesinden geçişte de elle kurulum önerilir.

Kurucuyu kaynaktan oluşturmak için önce `python scripts/generate-nsis-uninstall.py dist/AkisKurguAI dist/uninstall-files.nsh`, ardından `makensis installer.nsi` çalıştırılır. GitHub Actions her gönderimde testleri, paketlenmiş uygulamanın açılışını, kurulumu, güncellemeyi ve kaldırmayı denetler; sürüm numarası değiştiğinde kurucuyu ve özet dosyasını yayınlar.

## Planlananlar

Bunlar hedeftir, mevcut özellik değildir:

- Dışa aktarmada yüzde ve kalan süre
- Klavye kısayolları (oynat, sil, kaydet), klibin baş tarafını kırpma, klibi başka ize taşıma
- Fotoğraf ekleme; “doldur/kırp” yerleşimi
- Yönetici izni istemeyen kurulum ve kod imzası
- Eksiksiz İngilizce çeviri

## Lisans

Akış Kurgu AI, [GNU General Public License v3.0](LICENSE) ile yayımlanan özgür bir yazılımdır. Kurulum paketine eklenen FFmpeg, kendi lisansı (GPL) ile ayrı bir program olarak dağıtılır; diğer bağımlılıklar (PySide6/Qt — LGPL, faster-whisper ve diğerleri) kendi açık kaynak lisanslarını taşır.

## Gizlilik / Privacy policy

Uygulama hesap gerektirmez, telemetri veya kullanım istatistiği toplamaz ve projelerinizi hiçbir yere göndermez. Ağ bağlantısı yalnızca şu durumlarda kurulur:

- **Güncelleme denetimi:** açılışta GitHub'ın sürüm bilgisi okunur (`api.github.com`; istek sınırı dolmuşsa `github.com` üzerindeki sürüm sayfası ve özet dosyası). Bu isteklerde size ait veri gönderilmez; indirme ve kurulum yalnızca siz onaylarsanız yapılır.
- **AI özellikleri:** yalnızca siz kendi API anahtarınızı girip bir AI işlemi başlattığınızda, seçtiğiniz sağlayıcıya (OpenAI, Anthropic, xAI, Google Gemini veya Cloudflare Workers AI) isteğiniz, videodan seçilen kareler ve varsa konuşma dökümü gönderilir. Bu veriler ilgili sağlayıcının gizlilik koşullarına tabidir. API anahtarları Windows Kimlik Bilgileri Yöneticisi'nde saklanır.
- **Yerel Whisper modeli:** "Modeli indir" seçeneğini işaretlediğinizde model dosyaları Hugging Face üzerinden indirilir.

Bunların dışında uygulama, kullanıcı ya da uygulamayı kuran kişi özellikle istemedikçe başka sistemlere bilgi aktarmaz. Kaldırmak için Windows "Uygulamalar" listesindeki **Akis Kurgu AI** girdisini veya kurulum klasöründeki `Uninstall-Akis.exe` dosyasını kullanın.

## Kod imzalama politikası / Code signing policy

Sürümler şu anda dijital olarak imzalı değildir. Açık kaynak projeler için ücretsiz kod imzalama sağlayan SignPath Foundation'a başvuru hazırlanmaktadır; onaylandığında bu bölüm şu ifadeyle güncellenecektir: *Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).*

- **Derleme:** yayımlanan tüm dosyalar, bu depodaki kaynak koddan GitHub Actions üzerinde (`.github/workflows/windows-build.yml`) GitHub'ın barındırdığı makinelerde derlenir.
- **Committers and reviewers:** [@anilcanolcer](https://github.com/anilcanolcer)
- **Approvers:** [@anilcanolcer](https://github.com/anilcanolcer)
- Her sürümün kurucusunun SHA-256 değeri sürüm sayfasında yer alır; ayrıntılar: [docs/kod-imzalama.md](docs/kod-imzalama.md).
