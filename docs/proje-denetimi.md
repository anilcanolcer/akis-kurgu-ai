# Windows özellik denetimi · 0.6.15

Başlangıç noktası GitHub ve yerel main üzerindeki 0.6.14 (`54733aa`). Windows 11, Python 3.12.10 ve FFmpeg 9.0.2 kullanıldı. Önceki üç sürümün raporları ile 0.6.0 için tutulan Claude test kaydı yeniden sınanacak işlemlerin seçimine yardımcı oldu. Aşağıdaki ölçümler bu denetime aittir.

## Kapsam

98 test modülü 13 gruba ayrıldı. Her modül ana konusuna göre bir kez sayıldı. Bazı testler birkaç özelliği birlikte kullanır.

| Özellik grubu | Test | Sınanan davranış ve yöntem |
| --- | ---: | --- |
| Proje, medya, otomatik kayıt ve kurtarma | 92 | Medya ekleme, eski proje açma, kaydetme, taşıma, eksik kaynağı bağlama, sürüm ve kurtarma dosyaları. Geçici dosyalar ve ana pencere kullanıldı. |
| Zaman çizelgesi ve elle kurgu | 98 | İzler arası sürükleme, bölme, iki uçtan kırpma, aralık silme, boşluklar, klip hızı ve sesi, kadraj, geri al ve yinele. Model ve Qt etkileşimleri sınandı. |
| Önizleme ve oynatma | 59 | Konum, hız, proxy, parçalı önizleme, küçük resim ve dalga biçimi. Qt’nin Windows ses çıkışında konum ilerlemesi ve hız değişimi ölçüldü. |
| Otomatik kurgu ve konuşmacılar | 101 | Sessizlik, tekrar, dolgu sözcüğü, ritme kesim, vurgu, öne çıkan anlar ve konuşmacı işaretleri. Sentetik sesler, kurgu kararları ve model bileşenleri kullanıldı. |
| Altyazı, ses ve seslendirme | 66 | Altyazı yerleşimi ve kelime zamanları, ses eşitleme, gürültü azaltma, müzik kısma, seslendirme ve sesli dışa aktarma. FFmpeg çıktıları ve Windows sesi kullanıldı. |
| Kurgu isteği ve sağlayıcılar | 146 | Öneri, kurgu planı, onay, sağlayıcı seçimi, bozuk veya yarım yanıt, zaman aşımı, yeniden deneme ve gizlilik kaydı. Sağlayıcı yanıtları test ortamında üretildi. |
| Hikâye Stüdyosu | 45 | Rehber, sahne yazma ve düzenleme, görsel/video işleri, iptal, kaydetme ve açma. Yerel dosyalar gerçek, Gemini yanıtları kontrollüydü. |
| İlham, stil ve şablonlar | 55 | İlham fikrinden kurgu isteğine geçiş, hazır şablonlar, örnek videodan stil ölçümü ve kişisel şablonları saklama ve uygulama. |
| Kamera, mikrofon ve ekran kaydı | 13 | Kaynak seçimi, kayıt başlatma ve durdurma, projeye ekleme. Ekrandan gerçek kısa kayıt alındı. Kamera ve mikrofon akışlarında test aygıtları kullanıldı. |
| Dışa aktarma ve Shorts | 150 | Tek MP4, çoklu oran, toplu aktarım, hızlı aktarım, FCPXML, Shorts, çıktı çakışmaları, iptal, disk alanı ve ilerleme. FFmpeg, XML ve yerel Windows penceresi kullanıldı. |
| Arayüz, dil ve kısayollar | 50 | Açılış paneli, iki tema, Türkçe ve İngilizce, klavye kısayolları ve temel yardımcılar. |
| Güncelleme ve kurulum | 56 | Sürüm denetimi, indirme, özet doğrulama, iptal ve kurucunun dosya listesi. Gerçek paketle kurulum, yerinde güncelleme ve kaldırma ayrıca GitHub Windows işine dahildir. |
| Birden çok özelliği birlikte sınayan testler | 109 | Ana pencere akışları, iptalden sonra gelen sonuçlar, arka plan işlerinin kapanması, geçici dosyalar ve önceki sürümlerin regresyonları. |
| **Toplam** | **1.040** | Genel keşifte yerel Shorts penceresi atlanır. Aynı denetim komutu onu ayrı bir süreçte Windows pencere sistemiyle çalıştırır. |

Genel koşuda 1.039 test geçti. Ayrı Windows sürecinde Shorts testi de geçti. Altı medya grubu ve isteğe bağlı çevrimdışı konuşma deneyi başarılı oldu.

Aynı kaynaklardan bu PC’de üretilen 0.6.15 EXE’sinde iki saniyelik örnek proje açıldı. Başlık önizlemede göründü ve oynatma sayacı son kareye ulaştı (1,97 sn). Paket ses tanılaması bir çıkış aygıtında 1,5× oynatmayı doğruladı. Paketlenmiş Whisper tanılaması da indirmeye izin verilen ve çevrimdışı modlarda tamamlandı.

## Doğrulanan sorunlar ve düzeltmeler

| İşlem | 0.6.14’te gözlenen sonuç | 0.6.15’te kontrol |
| --- | --- | --- |
| Kaydedilmemiş proje açıkken başka proje açma | Açmadan vazgeçilince veya yeni dosya okunamayınca eski projenin kurtarma kopyası erken silinebiliyordu. | Başarısız açma ve iptalde kopyanın baytları aynı kaldı. Aynı proje başarıyla yeniden açıldığında kayıtlı sürüm geldi. |
| Hikâye taslağı açıkken başka dosya açma | Değişiklikleri bırakıp açılamayan bir dosya seçince mevcut taslak kaydedilmiş görünüyordu. İlgisiz JSON ve gelecekteki dosya sürümleri boş hikâye gibi açılabiliyordu. | Hatalı açma mevcut taslağı korudu. Eski, biçim etiketsiz hikâye dosyası açıldı. |
| Rehberin karakter listesini düzenleme | Liste yerine sayı yazılınca arayüzde işlenmeyen hata oluşuyordu. | Düzenleyici hata bildirdi ve önceki rehberi korudu. |
| Hikâye ve FCPXML kaydı | Windows’un kabul ettiği uzun hedef adlarından üretilen geçici ad dosya sistemi sınırını aşıyordu. | 252 ve 253 karakterlik hedef adlarıyla yazma ve geri okuma başarılı oldu. |
| Güncelleme sırasında kaydedilmemiş hikâye | Hikâye penceresinde iptal edilse bile kurucu daha önce başlatılmış olabiliyordu. | İptal durumunda kurucu çağrısı ve bekleyen sürüm kaydı oluşmadı. |
| Ses ayarları, video yükleme ve şablondan geri alma | Açık görünen ses eşitleme yeni videonun dışa aktarım ayarına geçmiyordu. Şablonu geri alınca değiştirdiği ses ayarı kalıyordu. | Denetim kutusu, proje kaydı ve render ayarı aynı durumu gösterdi. Geri al ve yinele seçimi geri getirdi. |
| Kişisel şablonları saklama | Okunamayan şablon dosyasına ekleme veya silme denemesi koleksiyonun üzerine yazabiliyordu. İki editör aynı geçici dosya ve kilitsiz liste üzerinde çalışıyordu. | Bozuk girdinin baytları korundu. Eş zamanlı iki kayıt sonrasında iki şablon da geri okundu. |
| Şablon ayrıntıları ve toplu dışa aktarma | İngilizce arayüzde dolu şablon ayrıntıları Türkçe kalıyordu. Örnek videodan gelen bulanık kadraj, toplu sessizlik kesiminden sonra iki klipte de yoktu. | Arayüz etiketleri çevrildi, kullanıcı başlığı korundu ve iki klip de seçili kadrajı aldı. |
| FCPXML ile aktarım | Aynı filmin ses ve katman izlerindeki kopyaları iki medya bileşenini de etkin bırakıyordu. Yatay 30 fps kaynak, dikey 25 fps projenin biçimiyle etiketleniyordu. | Üç izde kullanılan aynı dosyanın bileşen seçimleri XML’de ayrı ayrı kontrol edildi. 320×240, 30 fps kaynak 1080×1920, 25 fps projeden ayrı tanımlandı. |

FCPXML kontrolü kaynak referansları, bileşen seçimi ve zaman değerleri üzerinden yapıldı. [Apple’ın asset-clip belgesi](https://developer.apple.com/documentation/professional-video-applications/asset-clip)

## Gerçek medya ile yapılan ek kontroller

- Windows’un Türkçe sistem sesiyle iki cümle üretildi. Önbellekteki Whisper tiny, çevrimdışı çalışarak 10 kelimeye zaman damgası verdi. Beş altyazı klibi içeren proje başka klasöre taşındı ve eksik kaynak olmadan açıldı. 4,87 saniyelik MP4’ün örnek karesinde altyazı eklenince 2.079 piksel değişti. FCPXML taşınan kaynağı gösterdi.
- Beş kare hızı, dokuz klip hızı, yedi klip uzunluğu, dört kesirli başlangıç ve iki boşluk durumu toplam 2.520 kombinasyon oluşturdu. Bu deney, sonraki klip kısaltıldığında önceki klibin kareleri ve işaretçilerinin korunmasını ölçer.
- Ayrı FFmpeg deneylerinde iki renk ve iki ses frekansı ile proje taşıma, doğru kaynağa yeniden bağlama, önizleme önbelleği, çok izli ses eşlemesi, kesim karesi, geçiş ortasında Shorts bölme ve çıktı kare hızı doğrulandı.

## Yeniden çalıştırma

Başlangıç sürümünün genel keşfinde 1.023 test listelendi ve hata bildirilmedi. Yeni dosya ve arayüz senaryoları aynı sürümde yukarıdaki sorunları gösterdi. Eski temel yardımcı testi de standart keşfe dahil edildi. GitHub’ın Windows işi altı medya grubunun tamamını yeniden çalıştırıyor ve ölçümleri iş çıktısı olarak tutuyor.

Windows’ta proje bağımlılıkları, yerel AI bağımlılıkları ve FFmpeg kurulu olmalı. Aşağıdaki komut tam yerel denetimi çalıştırır. `-LocalSpeech` için Türkçe veya İngilizce Windows sesi ve önceden indirilmiş Whisper tiny gerekir. Bu seçenek çıkarıldığında diğer denetimler çalışır.

```powershell
./scripts/media-audit/run-audit.ps1 -Project . -LocalSpeech
```

Her çalıştırma ayrı bir sonuç klasörü oluşturur. Bir test grubu başarısız olsa da diğer bağımsız gruplar çalışır. Sonuç yolunu komut ilk satırda gösterir. GitHub Windows işi kurucuyu ve paketlenmiş Whisper’ı ayrıca sınar.

**Doğrulama sınırları.** Canlı ücretli sağlayıcılar, fiziksel kamera ve mikrofonla çekim kalitesi, farklı GPU ve sürücüler ve FCPXML’in Final Cut Pro veya DaVinci Resolve içinde açılması bu turda doğrulanmadı. Konuşma tanıma örneği Türkçe sentetik sestir. Uzun veya gürültülü insan kayıtlarındaki doğruluk bu örnekle ölçülmedi.
