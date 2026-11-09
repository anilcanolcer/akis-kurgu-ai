# Akış Kurgu AI

Windows için Türkçe, yerel video düzenleme uygulaması. Video dosyaları bilgisayarda işlenir;
yalnızca kullanıcı **AI Kurgu** veya **Altyazı** işlevini başlattığında seçilen kareler/ses
OpenAI API'ye gönderilir.

## Özellikler

- MP4, MOV, MKV, WebM ve AVI içe aktarma
- Kare hassasiyetinde başlangıç/bitiş aralığı ve canlı önizleme
- 9:16, 16:9, 1:1, 4:5 ve kaynak oranında dışa aktarma
- Parlaklık, kontrast, doygunluk ve başlık katmanı
- Hız, sinematik/siyah-beyaz/yumuşak görünüm ve giriş-çıkış geçişi
- Reels, TikTok, YouTube ve 4K dışa aktarma profilleri
- Gürültü azaltma ve -14 LUFS ses normalizasyonu
- OpenAI Responses API ile görsel analizden otomatik kurgu planı
- `gpt-transcribe` ile Türkçe konuşma metni/altyazı taslağı
- Windows Kimlik Bilgileri Yöneticisi'nde isteğe bağlı API anahtarı saklama
- FFmpeg ile H.264/AAC, filigransız MP4 dışa aktarma
- İnsan-okunur `.akis.json` proje dosyası, otomatik kayıt ve sürüm anlık görüntüleri
- Türkçe/İngilizce arayüz geçişi

## Bu paketin kapsamı

Bu teslimat çalışan bir **Core Edition**'dır. Tek ana video parçası üzerinde kararlı kurgu ve
dışa aktarma sunar. Tam çok izli NLE, keyframe eğrileri, yerel ses klonlama, motion tracking,
HDR renk yönetimi, proxy/multicam ve eklenti SDK'sı henüz bu pakette yoktur. Kaynak yapı bu
özelliklerin eklenebilmesi için açık tutulmuştur; mevcut olmayan özellikler arayüzde çalışıyormuş
gibi gösterilmez.

OpenAI özellikleri isteğe bağlıdır ve kullanım hesabınızda ücret oluşturabilir. Resmî OpenAI
önerisine uygun olarak anahtar kaynak koda gömülmez; “güvenli sakla” seçilirse Windows Kimlik
Bilgileri Yöneticisi kullanılır.

## Geliştirici çalıştırması

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Paketleme

```powershell
pyinstaller AkisKurguAI.spec --noconfirm --clean
```

