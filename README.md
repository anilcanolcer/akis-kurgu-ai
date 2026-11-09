<p align="center"><img src="logo.svg" width="128" alt="Akış Kurgu AI logosu"></p>

# Akış Kurgu AI

Windows için yerel öncelikli, Türkçe ve İngilizce video düzenleyici. Proje erken geliştirme aşamasındadır; üretim kullanımı için hazır değildir. Instagram Edits ile bağlantılı değildir. Müzik kütüphanesi, hesap eşitleme veya doğrudan Instagram yayını sağlamaz.

## Mevcut durum

Çalışan veya temel düzeyde uygulanan parçalar:

- Yerel video açma ve temel düzenleme arayüzü; klip/iz modeli, klip bölme, taşıma ve ripple silme için ilk kontroller.
- FFmpeg ile kare ve ses çıkarma; H.264/AAC ile filigransız dışa aktarma altyapısı.
- JSON proje kaydetme, şema sürümü 2'ye geçiş ve sürüm anlık görüntüleri.
- İsteğe bağlı OpenAI API ile örnek kare analizi ve konuşma metni oluşturma. API kullanımı internet bağlantısı ve kullanıcıya ait ücretlendirmeyi gerektirir. Anahtar isteğe bağlı olarak Windows Kimlik Bilgileri Yöneticisi'nde saklanır.
- Türkçe/İngilizce arayüz için kısmi çeviri; otomatik testlerin başlangıcı.

Sınırlamalar:

- Çok izli önizleme ve dışa aktarma henüz tamamlanmadı. Çok izli projelerin dışa aktarılması eksik sonuçları önlemek için engellenir; önizleme ana video kaynağıyla sınırlıdır.
- Çok izli zaman çizelgesi tüm düzenleme senaryolarında doğrulanmış değildir. Waveform, keyframe düzenleme, opacity/transform ve ses zarfı yoktur.
- Yerel AI/TTS, ses klonlama, proxy, export kuyruğu, iptal ve güvenilir ilerleme göstergesi yoktur.
- LUT/scopes, hareket takibi, green screen, iç içe sekanslar, multicam ve eklenti sistemi yoktur.
- Çeviriler ve otomatik kurtarma kapsamlı biçimde test edilmemiştir. `MainWindow` hâlâ çok fazla sorumluluk taşır.

## Kurulum ve çalıştırma

Windows 10/11 64-bit, Python 3.12 ve PATH üzerinde FFmpeg gerekir. `sample/` klasörü kaynak paketinde bulunur.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Testler (gerçek medya testleri FFmpeg gerektirir):

```powershell
python -m unittest test_timeline_model test_project_service test_media_service -v
```

Windows klasör dağıtımı oluşturmak için `C:\Windows\System32\ffmpeg.exe` konumunda FFmpeg bulunduğundan emin olun ve:

```powershell
python -m PyInstaller AkisKurguAI.spec --noconfirm --clean
```

Çıktı `dist/AkisKurguAI/` içindedir. EXE bu klasördeki `_internal` ile birlikte dağıtılmalıdır. Paket FFmpeg'i içerir; dağıtım öncesinde kullanılan FFmpeg derlemesinin lisans koşullarını ayrıca değerlendirin.

## Mimari

- `main.py`: PySide6 penceresi ve henüz ayrıştırılmamış uygulama akışları.
- `timeline_model.py`: kare tabanlı `Timeline`, `Track`, `Clip` modelleri.
- `multitrack_widget.py`: deneysel zaman çizelgesi görünümü.
- `media_service.py`: FFmpeg süreç sınırı; test için süreç çalıştırıcısı enjekte edilebilir.
- `project_service.py`: sürümlü JSON okuma, taşıma ve atomik kayıt.
- `logo.svg`, `app.ico`: özgün logo ve uygulama simgesi.

## Yol haritası

1. **Phase 1 — Timeline:** Önizleme ve export'u tek timeline modeline güvenilir biçimde bağlamak; çok iz, sesli oynatma, waveform ve düzenleme testleri.
2. **Phase 2 — AI ve ses:** İsteğe bağlı yerel transkripsiyon, AI düzenleme akışı ve ses araçları.
3. **Phase 3 — Görüntü ve teslim:** Renk araçları, proxy, ilerleme/iptal, export kuyruğu ve çoklu çıktılar.
4. **Phase 4 — Kullanılabilirlik:** Tam çift dil, düzenlenebilir çalışma alanları, medya organizasyonu ve kararlılık.

Bu maddeler hedeftir; kullanılabilir özellik taahhüdü değildir.

## Katkı ve geliştirme

Hata raporunda Windows/Python/FFmpeg sürümlerini, yeniden üretme adımlarını ve mümkünse kişisel veri içermeyen örnek projeyi paylaşın. Değişikliklerde mevcut `.akis.json` dosyaları için geçişi koruyun, kaynak medyayı değiştirmeyin ve ilgili birim/entegrasyon testlerini çalıştırın. API anahtarlarını veya kişisel medyayı depoya eklemeyin. Logo varlıkları `python generate_icons.py` ile yeniden üretilebilir.
