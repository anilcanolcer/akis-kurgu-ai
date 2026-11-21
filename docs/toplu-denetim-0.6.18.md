# Akış Kurgu AI 0.6.18 Windows denetimi

21 Kasım 2026. Başlangıç noktası GitHub’daki 0.6.17 sürümü (`fb259c0`). Aynı bilgisayarda önce bu sürümün denetimi, ardından düzeltmeler ve yeni regresyon testleri çalıştırıldı. Ortam Windows 11 Pro, Python 3.12.10, PySide6 6.10.0 ve FFmpeg 9.0.2. İki fiziksel monitörün her biri 1920×1080. İkinci monitör birincinin solunda.

## Bildirilen ekran kaydı sorunu

Kullanıcının ekran görüntüsünde FFmpeg, Videolar altındaki MP4 dosyasını açarken “No such file or directory” bildiriyordu. Eski sürüm aynı adlı Türkçe klasöre bu test bilgisayarında yazabildi. Görüntüden kullanıcının Windows hesabındaki dosya erişim hatasının kesin nedeni belirlenemiyor. Önceki gerçek ekran testi, geçici klasörde küçük bir alanı doğrudan FFmpeg ile kaydediyordu. Durdurma çubuğu testi ise düğmenin metodunu doğrudan çağırıyordu. Bu iki test, açık bir kayıt penceresinin fareyi başka bir penceredeki çubuğa iletip iletmediğini ölçmüyordu.

| Deneme | Gözlem ve düzeltme |
| --- | --- |
| MP4 hedefi | Editör artık hedefi Windows üzerinden kendisi açıyor. FFmpeg dosya yolu yerine açık, üzerinde ileri geri gidilebilen dosya tanıtıcısına yazıyor. Mevcut bir kayıt aynı adla açılırsa korunuyor. Klasöre yazılamazsa kullanıcı kayıt penceresinde başka bir klasör seçip tekrar deneyebiliyor. |
| Başlat, küçült ve durdur | Eski sürümde ana pencere küçüldüğünde etkin modal pencere kayıt diyaloğuydu. Artık küçük çubuk etkin pencere oluyor. Kayıt bitince editör önceki pencere boyutuna dönüyor. Başlatma ve dosyayı kapatma hataları süre göstergesinin altında okunabiliyor. |
| Canlı önizleme | Kayıt öncesi seçilen ekran diyalogda görüntülendi. Kayıt sürerken çubuktaki **Önizleme** düğmesiyle aynı ekranın küçük canlı görüntüsü açıldı. |
| İki monitör ve ölçek | Windows’ta monitör başlangıç koordinatına ölçek iki kez uygulanıyordu. %125 ölçekle iki ekrandan ayrı ayrı kayıt alındı. Çözümleyici 3,57 ve 3,60 saniyelik dosyalarda sırasıyla 65 ve 60 kare okudu. Ölçek yalnızca test sürecine uygulandı. |
| Paketli uygulama | Yerel PyInstaller paketi örnek projeyle açıldı. **Kayıt al → Kaydı başlat → Durdur ve ekle** akışı varsayılan Videolar klasöründe tamamlandı. Dosya medya listesine girdi. FFmpeg 67,67 saniyelik MP4’ten 1.303 kareyi hatasız çözdü. |
| Kamera ve mikrofon | **Kaydı sil** seçeneğinde Qt’nin dosyayı kapatması bekleniyor ve ardından dosya siliniyor. Gecikmeli durma bildirimiyle test edildi. Bu bilgisayarda fiziksel kamera veya mikrofon görünmedi. |

## Diğer bulgular ve kontroller

| İş akışı | Doğrulanan sorun ve karşılık gelen test |
| --- | --- |
| Hikâye Stüdyosu | Rehberdeki elle yazılmış başlık, **Uygula** tıklanmadan kaydedildiğinde kayboluyordu. Artık **Kaydet** geçerli değişikliği dosyaya geçiriyor. Geçersiz JSON’da kaydetme duruyor, düzenleme ve önceki dosya korunuyor. Dosya yeniden okunarak kontrol edildi. |
| Video çıktıları | Toplu işlem, Shorts veya öne çıkanlar, zaman çizelgesinden çıkarılmış bir proje kaynağının üzerine yazabiliyordu. Her video dışa aktarma yolunda hedefler, açık projenin ana kaynağına, kliplerine ve medya listesine karşı denetleniyor. Çakışma denemelerinde işçi başlamadı ve özgün dosyanın baytları korundu. |
| Uzun dosya adları | Windows’ta 251 karakterlik geçerli bir proje kaydedilebildiği hâlde sürüm kopyası oluşmuyordu. Otomatik kayıt, kilit ve çıktı son ekleri de sınırı aşabiliyordu. İki uzun proje için ayrı kilit, otomatik kayıt ve geçmiş kopyası oluşturuldu. Tek bir uzun kaynaktan iki toplu ve üç oranlı çıktı adı ayrı ayrı yazılabildi. |
| Eşzamanlı indirme | İki editör aynı kurucuyu veya konuşmacı modelini indirirken aynı geçici dosyayı paylaşıyordu. Her deneme artık kendi dosyasını kullanıyor. Doğrulanmış dosyanın yayımlanmasında geçici Windows paylaşım kilidi hesaba katılıyor. Her iki indirme türünü ikişer paralel istemciyle sınayan test 50 kez arka arkaya geçti. |
| Güncelleme klasörü | Temizlik, kurucuya ait olmayan bir metin dosyasını da siliyordu. Artık yalnızca tanınan güncelleme dosyaları temizleniyor. Testte klasöre bırakılan kişisel dosya korundu. |

## Kapsam ve yeniden çalıştırma

- Birim ve uygulama testleri proje açma, taşıma, kurtarma, medya ekleme, zaman çizelgesi, geçmiş, altyazı, ses, şablonlar, Hikâye Stüdyosu, kayıt, dışa aktarma ve güncelleme akışlarını kapsıyor. Önceki modül envanteriyle birlikte okunabilir. [Özellik ve modül listesi](toplu-denetim-0.6.17.md)
- Standart medya denetiminde 2.520 ayar birleşimi, ayrıca zamanlama, proje kurtarma, çok izli kurgu ve önizleme/çıktı karşılaştırmaları var. Kurgu, görüntü, ses, yapay zekâ yanıtları, önizleme, ana pencere ve depolama için standart tarama 14.670 senaryo içeriyor.
- Ek taramada bu yedi grubun her biri 36.121 başlangıç değeriyle çalıştırıldı. Sırasıyla 1.000, 24, 24, 4.000, 600, 50 ve 750 yeni senaryoda hata saptanmadı. Görüntü ve ses gruplarında çıkan medya tekrar çözüldü.
- Yerel Türkçe ses sentezi ve Whisper ile yapılan uçtan uca denemede 10 zamanlı kelime, 5 altyazı klibi ve 4,87 saniyelik çıktı elde edildi. Taşınmış projede kayıp kaynak bulunmadı.
- Ücretli bulut sağlayıcılarının yanıt, iptal ve hata yolları test yanıtlarıyla sınandı. Canlı ücretli üretim, fiziksel kameradan görüntü, mikrofondan ses ve kullanıcının ekran görüntüsünü aldığı Windows hesabındaki klasör izinleri doğrulanamadı. Denetim, belgelenen koşullardaki sonucu gösterir.

Yerel Windows denetimi aşağıdaki komutla çalıştırılır. Etkileşimli masaüstü, FFmpeg, yerel Türkçe ses ve Whisper modeli gerekir. GitHub’daki Windows iş akışı ayrıca uygulamayı paketler ve kurulum, yerinde güncelleme ve kaldırma senaryolarını çalıştırır. [Windows iş akışı](../.github/workflows/windows-build.yml)

```powershell
./scripts/media-audit/run-audit.ps1 -Project . -Python ./.venv/Scripts/python.exe -LocalSpeech
```
