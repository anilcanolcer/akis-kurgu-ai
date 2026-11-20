# Windows toplu denetimi

0.6.12 düzeltmeleri, 0.6.11 sürümündeki beş bulgu üzerinden hazırlandı. Aynı senaryoların tekrar denenebilmesi için betikler bu depoda yer alıyor.

| Alan | Tekrarlanan sorun | Doğrulama |
| --- | --- | --- |
| Yerel kesimler | Başka klipteki kesim, dokunulmayan klibin kaynak karesini, işaretçilerini veya boşluğunu değiştirebiliyordu. | Beş kare hızı, dokuz klip hızı, yedi uzunluk, dört kesirli kaynak başlangıcı ve iki boşluk değeri. Düzeltmeden önce 2.520 durumun 1.102'sinde fark görüldü. Düzeltmeden sonra fark sıfır. |
| Proje taşıma | Taşınan proje eski klasörün medyasını açabiliyordu. | Her iki kopya diskteyken medya çözümleme, eksik medya bağlama ve dışa aktarımdaki renk/ses kontrolleri. |
| Analiz önbelleği | Büyük iç içe sonuçlar sabit boyutta sayılıyordu. | Bellek bütçesi küçük tutularak büyük bir sonucun önbelleğe alınmadan geri verilmesi sınandı. |
| Windows sesi | Hız veya konum değiştirirken oynatıcı altı saniyelik dosyanın sonuna sıçrayabiliyordu. | Gerçek Qt oynatıcısıyla konum ve hız takibi, yüklenen kaynağın yeniden oynatılması, çok izli ses kontrolleri. |
| Paketleme | Derleme makinesindeki farklı bir ICU kitaplığı QtCore'un açılmasını engelleyebiliyordu. | Windows paketinin açılışı, örnek projenin yüklenmesi, paket içinden ses ve yerel Whisper tanılamaları. |

## Aynı kontrolleri çalıştırmak

Windows'ta proje bağımlılıklarının kurulu olduğu bir `.venv` ve PATH üzerinde FFmpeg gerekir. Proje kökünde şu komutu çalıştırın.

```powershell
./scripts/media-audit/run-audit.ps1 -Project .
```

Betik genel test kümesini, gerçek kısa ekran kaydını, kare matrisini, dört sentetik medya deneyini ve yerel Windows Shorts penceresi testini çalıştırır. Başlangıçta yazdırılan geçici klasör ölçüm dosyalarını içerir. Matris her GitHub Windows derlemesinde ayrıca çalışır.

## Ölçümün sınırları

Medya deneyleri üretilmiş görüntü ve ses kullanır. Gerçek bir dosyadan alınan ölçümler sessizlik temizliği, tempo, aynı kaynağın tekrar kullanımı, önizleme, geçişler, boşluklar, altyazı ve dışa aktarma kontrollerine girer. Bulut sağlayıcılarının yanıtları testlerde taklit edilir. Testler canlı ücretli üretim, fiziksel mikrofon kalitesi veya farklı sürücülerin tümü hakkında sonuç vermez.

Örnek videodan stil alma testi, 0.6.11 denetiminde bir ara çalıştırmada hata verdi. Daha sonraki bağımsız tekrarlarda geçti. İlk hatanın nedeni doğrulanamadı.
