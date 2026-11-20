# Akış Kurgu AI 0.6.13 toplu denetimi

Başlangıç sürümü 0.6.12, commit `f7cd872`. Önceki denetimdeki kesim matrisi, FFmpeg medya deneyleri ve test kümesi bu turda da çalıştırıldı. Yeni kontroller, özelliklerin birbirini etkilediği işlemlere odaklanıyor.

| Birlikte sınanan işlemler | 0.6.12'de tekrar üretilen davranış | 0.6.13 kontrolü |
| --- | --- | --- |
| Kesirli hız, bölünmüş klip, altyazı üretimi | Klipte duyulan son kelime ve cümle, kaynak zamanını tam sayıya yuvarlayınca altyazıdan düşebiliyordu. | 13,5–16,5 kaynak karesi aralığındaki söz hem klasik hem kelime altyazısında klibin son karesine yerleşiyor. |
| Kelime altyazısı, sol kenarı uzatma | Klip genişletildiğinde kelimenin vurgusu görüntüye göre erkene kayıyordu. | Klip başlangıcı dört kare geriye alındı. Vurgu aynı zaman çizelgesi karesinde kaldı. |
| Kesirli hız, Shorts metni ve duraklama | Kesimden önceki söz başlığa girebiliyor ve sonda duyulan söz atlanabiliyordu. | Başlık ve duraklama zamanlaması klibin gerçek kaynak aralığını kullanıyor. |
| El çizimi işaret, bölme, görüntü üretimi | İkinci parça yeni bir çizim üretiyor ve giriş animasyonunu baştan oynatabiliyordu. | Model aynı çizim kimliğini ve animasyon süresini koruyor. FFmpeg ile bölme öncesi ve sonrası alınan aynı karede 57.600 piksel karşılaştırıldı. Fark sıfır. |
| Fotoğrafı yeniden bağlama, kaydetme ve önbellek kaybı | Proje yeni oluşturulan MP4'ü kaydediyor, fotoğrafın eski yolunu tutuyordu. | Kullanıcının seçtiği fotoğrafın yolu projede kalıyor. Geçici MP4 yeniden kaybolduğunda fotoğraf bulunabiliyor. |

## Denetimi tekrar çalıştırma

Proje kökünde Windows PowerShell, FFmpeg ve bağımlılıkların kurulu olduğu `.venv` kullanın.

```powershell
./scripts/media-audit/run-audit.ps1 -Project .
```

Genel test kümesi beş yeni etkileşim testini, proje kayıt ve kurtarma akışlarını, kurgu ve dışa aktarma testlerini de çalıştırır. Betik ayrıca farkı ölçülen 2.520 kesim kombinasyonunu, dört medya deneyini, kısa ekran kaydını ve yerel Windows Shorts testini çalıştırır. Sürüm iş akışı paket açılışı, ses, Whisper, kurulum, güncelleme ve kaldırmayı sınar.

Ücretli bulut üretimi, fiziksel kamera ve mikrofon kalitesi ve farklı sürücülerin davranışı bu denetimin kapsamı dışındadır.
