# Akış Kurgu AI 0.6.20 Windows denetimi (ikinci tur)

21 Kasım 2026. 0.6.19 denetimi temel kurgu, kayıt ve dışa aktarma akışlarını gerçek arayüzde denemişti. Bu tur, o denetimin yalnız otomatik testlerle sınadığı özellikleri de gerçek Windows arayüzünde, düğmelere basarak ve üretilen dosyaları ölçerek denedi. Ayrıca önceki raporda “denenmedi” denen bozuk proje ayarlarını rastgele girdiyle sınadı.

## Başlangıç noktası

| Kaynak | Durum |
| --- | --- |
| Yerel çalışma kopyası | `main`, `7ddedb1`. GitHub `main` ile aynı. Codex'ten yeni commit yok. |
| GitHub'daki son sürüm | 0.6.19, `fb00406`. `7ddedb1` program kodunda bununla aynı; yalnız raporu tamamlıyor. |
| Denenen program | `7ddedb1` kaynak koddan; düzeltmelerden sonra aynı koddan bu bilgisayarda PyInstaller ile derlenen 0.6.20 paketi (`AkisKurguAI.exe`). |
| Korunan yerel çalışmalar | `scripts/installer-scenarios.ps1` değişikliği ve `scripts/media-audit/ui0610/` klasörü commit'lere girmedi. Uygulama veri klasöründeki `recovery.akis.json` (11.11) ve `templates.json` aynı kaldı; şablon akışı `templates.json`'u yedekleyip geri koydu (SHA-256 öncesiyle aynı). |

**Ortam:** Windows 11 Pro 10.0.26300, Python 3.12.10, PySide6 6.10.0, FFmpeg 9.0.2, iki 1920×1080 ekran, kamera ve mikrofon yok.

## Yöntem

1. Başlangıçta bütün test kümesi ve `scripts/media-audit/run-audit.ps1` (Windows pencere testleri ve yerel konuşma tanımayla) çalıştırıldı.
2. Önceki raporun özellik tablosundan arayüzde denenmemiş olanlar seçildi; her biri için `scripts/media-audit/ui-flows` altına bir akış yazıldı. Program ayrı bir süreç olarak açıldı; düğmelere UI Automation ile, zaman çizelgesine ve kısayollara gerçek fare ve tuş olaylarıyla basıldı; dosya pencereleri Windows'un ve Qt'nin kendi pencereleriydi.
3. Her akış ekrandaki yazıyla değil çıktıyla doğrulandı. Deneme videolarında her kare kendi numarasını, her saniye kendi ses perdesini taşıyor; uzun videoda her 4 saniyede 1 saniyelik duraklama var. Dışa aktarılan her kare ve her yarım saniyelik ses okunup kaynağın hangi anı olduğu denetlendi.
4. Akışta görülen her belirti, programdan mı betikten mi geldiği ayrı bir yoklamayla (`probe_*.py`) ayrıldı; program hatası olmayanlar aşağıda “Betik kaynaklı belirtiler”de.
5. Doğrulanan her hata düzeltildi, görüldüğü akışta yeniden denendi ve eski kodda başarısız olan bir testle korundu. Akışlar son olarak paketlenmiş 0.6.20 üzerinde tekrarlandı.

## Gerçek arayüzde denenenler (bu tur)

K: kaynak koddan, E: paketlenmiş `.exe`. Hepsi düzeltmelerden sonraki son çalıştırmanın sonuçları.

| Özellik | Akış ve ölçüm | Sonuç |
| --- | --- | --- |
| Üç biçimde dışa aktar | 64 sn video → üç dosya. Boyutlar, 1.920 karenin her biri, her yarım saniye ses | K+E geçti: 1080×1920, 1080×1080, 1920×1080; üç dosyada da 1.920/1.920 kare doğru |
| Shorts'a böl | Parça en çok 20 sn → 4 parça, Qt klasör seçicisi | K+E geçti: parçalar birlikte videonun bütün karelerini eksiksiz ve tekrarsız taşıyor, hepsi 1080×1920 |
| Öne çıkan anlar | Listelenen aralık → dışa aktarılan Short | K+E geçti: dosya listelenen aralığın kesintisiz kareleri (ör. E: 0:08–0:52) |
| Böl, Ripple sil → FCPXML | 10–15 sn atıldı | K+E geçti: FCPXML'de 0–10 sn ve kaynağın 15. saniyesinden 49 sn |
| Kesilmiş kurguyu dışa aktarma (Ctrl+E) | Aynı kesim | K+E geçti: 0–299 ve 450–1.919. kareler, ses doğru saniyelerden |
| Hızlı (kopyalayarak) dışa aktarma | “Kaynak oranı”, aynı kesim, soruya Evet | K+E geçti: kayıp kare yok; kesim yerinde 5 fazla kare (program soruda bunu söylüyor) |
| Toplu dışa aktar | 2 video, “Sessizlikleri çıkar” açık | K+E geçti: yalnız sessiz kareler atıldı (64 sn → 54,2 sn, 24 sn → 20,2 sn), konuşmalı kare atılmadı |
| Başlık katmanı | Düzenle › başlık + Enter → dışa aktar | K+E geçti: ilk 3 sn'nin her karesinde yazı, sonrasında tek piksel fark yok |
| Oynatma hızı 2,00× | Düzenle › hız → dışa aktar | **Bulgu 2**, düzeltildi. K+E: 120 karenin her biri kaynağın 2n. karesi, ses doğru |
| −14 LUFS | Kısık (−33,4 LUFS) video | K+E geçti: −13,5 LUFS |
| Windows sesiyle seslendirme | Metin → WAV → oynatma çizgisine | K+E geçti: 3,52 sn WAV, 45. karede “Seslendirme” izinde, tam süresiyle |
| Kapanma sonrası kurtarma | Kaydedilmemiş bölme → otomatik kayıt → süreç zorla kapatıldı → aç | K+E geçti: “Kurtarılmış çalışma bulundu… Açılsın mı?”, “Aç”tan sonra kurgu (iki parça, başlık, seslendirme) aynen geri geldi |
| Yerel Whisper altyazı | Windows sesiyle Türkçe konuşma → metne çevir → altyazı ekle → dışa aktar | K+E geçti: metin eksiksiz tanındı (“Bugün hava çok güzel…”), 7 altyazı klibi, konuşma boyunca videoda görünüyor |
| Sessizlikleri çıkar | 24 sn, 6 duraklama | K+E geçti: 6 duraklama kesildi, konuşmalı kare atılmadı |
| Ayarları bozuk proje açma | 3 dosya, “Proje aç” | **Bulgu 1**, düzeltildi. K+E: üçü de açılıyor, tek Türkçe ileti |
| İngilizce arayüz | English düğmesi → ana pencere, 3 sekme, 10 pencere; adlar, ipuçları, yer tutucular | **Bulgu 3**, düzeltildi. Pencerelerde Türkçe kalan yazı yok; tek kalan “şey, yani” örnekli ipucu (bilinçli). Türkçe'ye dönüş geçti |
| Açık/koyu tema | Ekran görüntüsü parlaklığı | K+E geçti: 24 → 185 → 23 |
| Güncelleme denetimi | Sürüm düğmesi | E geçti: “0.6.20 is the latest version.” |
| Şablonlar | Hazır şablon uygula → geri al | K+E geçti: izler ve ayarlar geldi, geri alınca proje ilk haline döndü |
| Şablonlarım | Kaydet (Türkçe ad) → her şeyi sıfırla → uygula → sil | K+E geçti: renk 5/10/18, 1,25× ve gürültü azaltma geri geldi |
| Prompt ile kurgula (yapay zekâ) | `fake_ai_launch.py`: servis yerine sabit plan; plan onayı, dışa aktarma, geri al/yinele, plan olmayan yanıt | K geçti: istek 4 kareyle hazırlandı, çıktı tam 30–89 ve 150–209. kareler, geri al 8 sn / yinele 4 sn; plan olmayan yanıtta “AI yanıtında geçerli JSON bulunamadı.” |
| Temel düzenleme akışı (0.6.19 turundan) | Video ekle → böl → kırp → geri al/yinele → kaydet → kapat → aç → dışa aktar | E geçti: 240/240 kare ve 16/16 yarım saniye doğru |

Yapay zekâ akışı yalnız kaynak koddan çalışır: sahte servis Python koduna yerleştirilir. Hiçbir istek internete çıkmadı, Windows anahtar deposu okunmadı ve yazılmadı.

## Bulgular ve düzeltmeler

### 1. Ayar bölümü bozuk bir proje hiç açılmıyordu ve Python metni gösteriyordu

- **Yeniden üretme:** Bir `.akis.json` dosyasında `state` metin ya da liste olur, `saturation` çok büyük bir sayı olur, `publish` sayı olur, `ai_prompt` sözlük olur ya da `speed` “hızlı” yazılır (elle düzenleme, başka bir program, yarım kalan eşitleme). “Proje aç” ile açılır.
- **Beklenen:** Kurgu (asıl iş) açılsın; kullanılamayan ayarlar varsayılana dönsün ve bu söylensin.
- **0.6.19'da gerçek arayüzde görülen:**
  - “Proje açılamadı: 'str' object has no attribute 'get'”
  - önce “Beklenmeyen bir hata oluştu: int too big to convert”, ardından nedeni boş bir “Proje açılamadı:”
  - “Proje açılamadı: could not convert string to float: 'hızlı'”

  Kurgu sağlam olduğu halde hiç açılamıyordu. Açık proje korunuyordu.
- **Etkisi:** Ayarları bozulmuş bir projedeki bütün kurgu kullanılamaz; ileti nedeni söylemez.
- **Düzeltme:** `akis/project_service.py: repair_settings`. Açarken ayarlar denetlenir: yanlış türdekiler varsayılana döner, renk değerleri −50…50'ye çekilir, eski sürümlerin “1.25×” gibi hız yazıları olduğu gibi okunur. Pencere “Proje açıldı. Dosyadaki şu ayarlar okunamadı ve varsayılana döndürüldü: doygunluk, yayın metni, AI isteği.” der (İngilizce arayüzde İngilizcesi).
- **Doğrulama:** Gerçek arayüzde aynı üç dosya K+E açıldı (8,00 sn'lik kurgu yerinde), tek bir bilgi iletisi çıktı.
- **Testler:** `tests/test_windows_audit_0620.py` (SettingsRepairTests, WindowOpensDamagedSettingsTests). Altı testten beşi eski kodda başarısız; altıncısı sağlam projenin uyarısız açıldığını koruyor. Yeni kural denetleyicisi `scripts/media-audit/open_fuzz.py`: projeyi gerçek ana pencerede (görünmez) açıp hiçbir hatanın dışarı kaçmadığını, reddin anlaşılır olduğunu, açılan ayarların aralıkta kaldığını ve kaydet-aç sonrası aynı kaldığını denetler. Eski kodda 600 denemenin 452'sinde hata, yeni kodda 1.500 denemede 0. Her derlemede çalışır.

### 2. Oynatma hızı 1,00× dışındayken görüntü sesten kayıyordu

- **Yeniden üretme:** Düzenle › Oynatma hızı 2,00× (ya da 1,25×, 1,5×, 0,75×, 0,5×) → dışa aktar.
- **Ölçülen (0.6.19):**

  | Hız | Görüntü | Ses |
  | --- | --- | --- |
  | 1,25×, 1,5×, 2× | 67 ms (2 kare) geç | zamanında |
  | 0,5×, 0,75× | 33 ms (1 kare) erken, video 1 kare kısa (479 yerine 480) | zamanında |

  67 ms dudak kayması fark edilebilir düzeydedir. Aynı yol üç biçimde aktarma, Shorts, öne çıkanlar ve toplu aktarmada da kullanılıyor.
- **Neden:** Proje hızı bitmiş görüntüye yalnız `setpts=PTS/hız` ile uygulanıyordu. 1/30 sn'lik zaman tabanında tek sayılı damgalar kesiliyor, kare seçimi de dosya yazılırken `-r` dönüşümüne kalıyordu; o dönüşüm kare atarken gecikme biriktiriyor.
- **Düzeltme:** `akis/timeline_render.py`. Her kare açıkça çıkış karesine yerleştirilir (`ceil(N/hız)`) ve `fps` süzgeci bir tane seçer; klip hızı yolunun yöntemi. Çıkış karesi n, her hızda kaynağın ⌊n×hız⌋. karesidir. Süresi tam kare olmayan kurgularda (17 kare 2×'te) son kare korunur.
- **Doğrulama:** Beş hızda da görüntü ve ses aynı anda (0 ms); gerçek arayüzde K+E 2× çıktının 120 karesi de doğru.
- **Testler:** `ProjectSpeedFrameTests` (programın sunduğu beş hızın beşi eski kodda başarısız). `render_fuzz` artık dışa aktarmaların üçte birinde rastgele bir proje hızı kullanıyor ve kareleri okuyor: eski kodda 60 denemenin 17'sinde hata, yeni kodda 90'da 0.

### 3. İngilizce arayüzde ekran okuyucu adları Türkçe kalıyordu

- **Görülen:** İngilizce arayüzde UI Automation “Arayüz dili”, “Görünüm” ve “Altyazı görünümü” adlarını Türkçe veriyordu. Görünür yazısı olmayan bu denetimleri ekran okuyucuyla kullanan biri Türkçe duyuyordu.
- **Düzeltme:** `main.py: apply_language` erişilebilir adları da çevirir ve Türkçe'ye dönüşte geri koyar.
- **Test:** `EnglishScreenReaderNameTests`. Eski kodda tam olarak bu üç adla başarısız.

### Mevcut testler bu sorunları neden kaçırdı

- **Bulgu 1:** 0.6.19 kuralı (`store_fuzz`) yalnız dosyanın kendisini ve kurgu bölümünü bozuyordu; ayarlar pencereye uygulanırken denetlenmiyordu. İki mevcut test ise bozuk hızı (“invalid”, “hızlı”) yalnızca açmayı başarısız kılmak için kullanıyordu; yani reddi doğru sayıyordu. Bu testler artık hatayı pencerenin kendi içinde üretiyor ve korudukları davranışı (başarısız açılışta önceki proje aynen kalır) korumaya devam ediyor.
- **Bulgu 2:** `render_fuzz` kareleri klibin kendi hızında okuyordu, projenin genel hızında değil. Proje hızı için var olan test yalnız süzgeç metnini ve süreyi denetliyordu; zamanlama grubu önizleme ile dışa aktarmayı karşılaştırıyordu, görüntüyü sesle değil.
- **Bulgu 3:** Dil testleri görünür yazıları, ipuçlarını ve yer tutucuları denetliyordu; erişilebilir adları değil.

## Hata sayılmayan gözlemler

- **Toplu dışa aktar:** Yazılan klasör henüz yoksa “Başlat” kapalı kalıyor ve nedeni söylenmiyor; “Seç…” ile seçilen klasörde sorun yok. Qt'nin klasör seçicisi de var olmayan klasör için “Seç”i kapalı tutuyor (Qt davranışı).
- **Hızlı dışa aktarma:** İkinci parça 3 kare erken başlıyor, birleşme yerinde 0,13 sn fazla ya da donmuş kare var. Program soruda bunu söylüyor; kayıp kare yok.
- **Öne çıkan anlar:** Aralık tam saniyeye yuvarlanarak gösteriliyor (3,5 sn için “0:04”).
- **Sessizlik ölçümü** sesi 2 kHz ile okuyor, yani 1 kHz üstünü duymuyor. Pencere “Konuşma olmayan yerler kesilir” dediği için bu tasarım gereği; ilk test videom 1 kHz üstü tonlar içerdiğinden o bölümler doğru biçimde kesildi. Islık, yüksek perdeli müzik gibi konuşma dışı sesler de kesilir.
- **Zaman çizelgesi:** Klibe tıklamak onu yalnız seçer; oynatma çizgisini cetvele ya da boş yere tıklamak taşır.

## Betik kaynaklı belirtiler (program hatası değil)

Her biri ayrı yoklamayla doğrulandı:
- Ctrl+E'nin “çalışmaması”: betik, UI Automation ile kapatılan ileti kutusu henüz kapanmadan tuşa basıyordu.
- Açık kalan liste kutusu: pywinauto'nun `select()` yöntemi bazen Qt listesini açık bırakıyor; açık liste sonraki tuşları alıyor.
- Qt, ipucu ve yer tutucu metinleri UIA'da `HelpText` yerine `FullDescription` olarak veriyor; dil ve tema anahtarları onay kutusu olarak görünüyor.
- İç içe pencereler (Şablonlarım › ad, Toplu aktar › dosya seç) üst pencerenin alt penceresi olarak listeleniyor.

## Otomatik testler ve denetim

| | Başlangıç (`7ddedb1`) | Düzeltmelerden sonra |
| --- | --- | --- |
| Genel test kümesi | 1.080 test, 2 atlandı, hepsi geçti | 1.088 test, hepsi geçti (gerçek ekranla 2, ekransız 3 atlandı) |
| Windows pencere testleri (Shorts penceresi, iki ekranda gerçek kayıt) | 2 geçti (kayıtlar 3,63 sn / 89 ve 99 kare) | 2 geçti (kayıtlar 3,63 sn / 98 ve 98 kare) |
| Medya grupları | 6/6 | 6/6 |
| Kural denetleyicileri | 9 denetleyici, hepsi 0 hata | 10 denetleyici, hepsi 0 hata (`open_fuzz` 600 dosya: 596 açıldı, 4'ü “kaynak video bulunamadı” ile reddedildi; `render_fuzz` proje hızıyla) |
| Yerel konuşma projesi | 10 kelime, 5 altyazı, 4,87 sn | 10 kelime, 5 altyazı, 4,87 sn |

Son tam denetimde yalnız yeni `EnglishScreenReaderNameTests` bir kez düştü: test kümesinin başka bir testi Qt'nin Türkçe kataloğunu yüklediği için Qt'nin kendi sekme kaydırma düğmesine “Sağa Sar” adını vermişti. Bu ad programın değil Qt'nindir; test programın kendi koyduğu adlarla sınırlandı. Bütün küme tek süreçte yeniden çalıştırıldı ve geçti; test eski kodda yine aynı üç adla başarısız.

Eklenen ve değişen testler: `tests/test_windows_audit_0620.py` (yeni; 10 test). `tests/test_open_path.py`, `tests/test_project_open.py` ve `tests/test_timeline_render.py`'de birer test, yukarıda anlatılan nedenle güncellendi.

## Sınanamayan koşullar

- Gerçek ücretli yapay zekâ sağlayıcılarının yanıtları: arayüz akışı sabit test yanıtıyla, kurallar taklit yanıtlarla sınandı. Hikâye Stüdyosu yalnız açılıp kapatıldı; Gemini ile üretim denenmedi.
- Kamera ve mikrofonla kayıt: bu bilgisayarda aygıt yok.
- Sesin kulakla duyulan kalitesi, seslendirmenin doğallığı.
- Whisper'ın uzun, gürültülü ya da çok kişili gerçek kayıtlarda doğruluğu (deneme Windows sesiyle sentetik Türkçe).
- Konuşmacı ayırma (indirilmiş konuşmacı modeli gerekiyor), ritme oturtma ve ses artışında yakınlaştırma arayüzde denenmedi; testler ve kurallarla sınanıyor.
- FCPXML'in Final Cut Pro ve DaVinci Resolve içinde açılması.
- Farklı ekran kartı, ekran ölçeği ve güvenlik yazılımları; ekran okuyucunun kendisi (adlar UI Automation'dan okundu).
- Kurulum, güncelleme ve kaldırma GitHub'ın temiz Windows makinesinde denendi; bu bilgisayardaki 0.6.10 kurulumuna dokunulmadı. Kurucu dijital imzalı değil.

## Yayın

Sürüm commit'i `3679f5b`. GitHub Windows derlemesi ([çalıştırma 44935731306](https://github.com/anilcanolcer/akis-kurgu-ai/actions/runs/44935731306)) yaklaşık 18 dakikada başarıyla bitti ve sürümü yayımladı.

| Adım | Sonuç |
| --- | --- |
| Genel test kümesi | 1.088 test geçti. 6 test GitHub makinesinde atlandı: gerçek ses çıkışı, masaüstü penceresi, gerçek ekran kaydı ya da indirilmiş konuşmacı modeli gerektiriyorlar. Ses ve kayıt olanları bu bilgisayarda çalıştı (yukarıdaki tablo). |
| Medya grupları | 6/6 geçti |
| Kural denetleyicileri | 10 denetleyici (yeni `open_fuzz` ve proje hızlı `render_fuzz` dahil) hata vermedi; biri hata verseydi derleme dururdu |
| Paketlenmiş programda ses ve Whisper tanılaması | Geçti |
| Kurulum, yerinde güncelleme ve kaldırma senaryoları | 18 senaryonun 18'i geçti |
| Yayımlanmış sürümle güncelleme denemesi | Geçti |
| Kaldırma doğrulaması (kullanıcı dosyası korunur, program silinir) | Geçti |

**Yayımlanan kurucu:** [AkisKurguAI-Setup.exe](https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/v0.6.20/AkisKurguAI-Setup.exe), 146.876.139 bayt. Bu bilgisayara indirildi ve SHA-256 değeri hesaplandı: `9af251bba385e6f83ed18248492d166156c72ac772c683e2ca34aaa8a399a339`. Bu değer yanındaki `AkisKurguAI-Setup.exe.sha256` dosyası ve GitHub'ın verdiği özetle aynı. Programın güncelleme denetimi 0.6.19'dan v0.6.20'yi aynı özet ve boyutla buluyor.

## Yeniden çalıştırma

```powershell
./scripts/media-audit/run-audit.ps1 -Project . -LocalSpeech
.venv/Scripts/python.exe -m unittest tests.test_windows_audit_0620
.venv/Scripts/python.exe scripts/media-audit/open_fuzz.py . 1500
```

Gerçek arayüz akışları ve nasıl çalıştırılacakları `scripts/media-audit/ui-flows/README.md`'de.
