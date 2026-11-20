# Akış Kurgu AI 0.6.14 toplu denetimi

Başlangıç sürümü 0.6.13, commit `cdc2c71`. Bu sürümün kontrollerine ek olarak zaman çizelgesindeki bir değişikliğin akıcı önizlemeye, oynatmaya ve dışa aktarmaya nasıl yansıdığı sınandı.

| Birlikte sınanan işlemler | 0.6.13'te tekrar üretilen sorun | Düzeltme |
| --- | --- | --- |
| El çizimi işaret, düzenleme, önbellek | Aynı konuma gelen farklı bir çizim öncekinin görüntüsünü kullanabiliyordu. | Önbellek, çizimi oluşturan kimliği hesaba katıyor. FFmpeg örneğinde 3.963 piksel değişti. Aynı yeni çizim tekrar istendiğinde parça önbellekten geldi. |
| Önizleme hazırlama, iptal, yeni proje | İptal edilmiş eski işlemin hatası yeni önizleme için hata bildirimi yapabiliyordu. | İptal edilmiş işlemin geç gelen hata bildirimi dikkate alınmıyor. |
| Farklı kare hızına sahip iki proje | Yeni önizleme hazırlanırken oynatılan dosyanın kare hızı değişebiliyordu. | Sayacı ve konum hesabını oynatılan dosyanın kare hızı belirliyor. |
| Akıcı önizleme hatası, kare kare oynatma | Akıcı kopya üretilemeyince oynatma kesiliyordu. | Kullanıcı oynatma başlattıysa kare kare oynatma devam ediyor. |
| Son kare, tekrar oynat | Kare kare oynatmada oynat düğmesi kurguyu başa almıyordu. | Tekrar oynatma ilk karede başlıyor. |
| Kaynak kare hızı, hızlı dışa aktarma | Akış kopyalama, zaman çizelgesinin gerekli kare hızı dönüşümünü atlayabiliyordu. | Hızlar farklıysa normal dışa aktarma uygulanıyor. 25 fps H.264 kaynak 30 fps olarak dışa aktarıldı. |

Depodaki Windows denetimi genel testleri, kısa ekran kaydını, 2.520 kesim kombinasyonunu, gerçek FFmpeg medya deneylerini ve yerel Shorts pencere testini içerir. Proje kökünde FFmpeg ve bağımlılıkların kurulu olduğu `.venv` ile çalıştırılır.

```powershell
./scripts/media-audit/run-audit.ps1 -Project .
```

Canlı ücretli servis çağrıları, fiziksel kamera ve mikrofon kalitesi ve farklı donanım sürücüleri bu denetimin kapsamı dışındadır.
