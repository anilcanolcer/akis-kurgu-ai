<p align="center"><img src="logo.svg" width="120" alt="Akış Kurgu AI logosu"></p>

<h1 align="center">Akış Kurgu AI</h1>
<p align="center">Windows için yerel öncelikli, Türkçe ve İngilizce video düzenleme denemesi</p>

## Windows'ta çalıştırma

[Windows için deneysel paketi indir](https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/v0.2.1-experimental/AkisKurguAI-Windows.zip)

1. ZIP dosyasını indirin ve tamamını bir klasöre çıkarın.
2. Çıkarılan klasördeki **AkisKurguAI.exe** dosyasını açın. `_internal` klasörü EXE'nin yanında kalmalıdır.
3. **Video ekle** ile bir video seçin. İnternet ve API anahtarı temel yerel düzenleme için gerekli değildir.

Paket taşınabilir klasör dağıtımıdır; bir Windows kurulum sihirbazı değildir. Windows 10/11 64-bit hedeflenir. GitHub Actions derlemesinde testler, otomatik açılış ve ses arka ucu kontrolü çalışır. Uygulama Windows medya arka ucunu tercih eder. Ses aygıtı bulunmayan ortamlarda gerçek oynatma testi atlanır; farklı cihazlarda ses/görüntü eşzamanlaması henüz doğrulanmamıştır.

## Uygulama görünümü

![Deneysel sürümde örnek video ve zaman çizelgesi](https://raw.githubusercontent.com/anilcanolcer/akis-kurgu-ai/experimental/timeline-render/docs/editor-demo.png)

*Deneysel sürümün gerçek arayüzü; görüntülerde FFmpeg tarafından oluşturulan örnek test videosu kullanılmıştır.*

![Deneysel sürümün hız ve renk ayarları](https://raw.githubusercontent.com/anilcanolcer/akis-kurgu-ai/main/docs/editor-adjustments.png)

*Düzenle sekmesindeki tuval oranı, hız ve renk kontrolleri.*

## Kısa kullanım

1. **Video ekle** ile dosya açın. İlk klip Video izinde görünür.
2. İzdeki klibe tıklayın; cetvel üzerinde tıklayarak veya sürükleyerek oynatma konumunu değiştirin.
3. Klip seçiliyken oynatma çizgisini klibin içine getirin ve **Böl** düğmesine basın. Klipleri aynı izde sürükleyebilir veya **Ripple sil** ile seçileni silip sonraki klipleri kaydırabilirsiniz.
4. Boş bir izi seçip **Medya** ile video/ses ekleyin; **İz** düğmeleriyle izleri yönetin. ▶ düğmesi oynatma ve duraklatma içindir.
5. **Düzenle** sekmesinden oran, renk ve hız ayarlayın; **Dışa aktar** ile MP4 oluşturun. Projeyi `.akis.json` olarak kaydedebilirsiniz.

## Neler çalışıyor?

| Alan | Deneysel dalın durumu |
| --- | --- |
| Timeline | Video, ses, metin ve overlay iz modeli; seçim, taşıma, bölme, uçtan kırpma ve ripple silme için temel kontroller |
| Önizleme ve çıktı | Ortak kare planından çok katmanlı FFmpeg kompozisyonu; H.264/AAC MP4, filigransız çıktı ve temel oranlar |
| Renk ve hız | Parlaklık, kontrast, doygunluk ve genel hız önizleme/çıktıya uygulanır; hız değiştirilmiş export ara dosya ve ikinci kodlama kullanır |
| Ses | Tek kaynaklı temel ses önizlemesi ve basit zamanlama düzeltmesi; export tarafında ses izlerinin temel karışımı |
| Proje ve AI | Sürümlü JSON proje; isteğe bağlı OpenAI ile kurgu önerisi ve konuşma metni. API kullanımı internet ve kendi anahtarınızı gerektirir |

### Bilinen sınırlamalar

- Önizleme her kareyi FFmpeg ile üretir; özellikle yüksek çözünürlükte akıcı gerçek zamanlı oynatma beklenmemelidir. Ses önizlemesi tek kaynak seçer, çok izli miksi canlı çalmaz.
- Eski aralık seçici, geçiş, görünüm efekti, başlık alanı ve bazı ses işleme kontrolleri yeni render yoluna bağlı olmadıklarından devre dışıdır. Metin izi model ve render düzeyinde desteklenir; tam bir metin düzenleyicisi yoktur.
- Waveform, keyframe düzenleme, proxy, dışa aktarma kuyruğu, yerel AI/TTS, gelişmiş renk araçları ve kurulum sihirbazı yoktur. Çeviriler eksiksiz değildir.
- Instagram müzik kütüphanesi, hesap eşitleme veya doğrudan yayınlama sunulmaz. Proje Instagram ile bağlantılı değildir.

## Kaynak koddan çalıştırma

Python 3.12, Windows ve PATH üzerinde FFmpeg gerekir:

```powershell
git clone https://github.com/anilcanolcer/akis-kurgu-ai.git
cd akis-kurgu-ai
git switch experimental/timeline-render
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

- `timeline_model.py`: kare tabanlı klip ve izler; `frame_plan.py`: etkin katmanlar.
- `timeline_service.py`, `timeline_audio.py`: düzenleme, oynatma saati ve temel ses konumu eşleme.
- `timeline_render.py`, `render_worker.py`, `preview_controller.py`, `media_service.py`: ortak kompozisyon, önizleme iş sırası ve FFmpeg sınırı.
- `multitrack_widget.py`, `main.py`: zaman çizelgesi arayüzü ve uygulama penceresi. Pencerede hâlâ ayrıştırılabilecek iş akışları vardır.
- `project_service.py`: proje şeması ve kayıt; `logo.svg`, `logo.png`, `app.ico`: logo ve simge varlıkları.
- `AkisKurguAI-Eski-Kaynak-ve-Ornekler.zip`: eski kaynak ve örnek arşivi; güncel uygulama veya logo kaynak paketi değildir.

Hata bildirirken Windows/Python/FFmpeg sürümlerini ve adımları paylaşın; API anahtarlarını veya kişisel medya dosyalarını depoya eklemeyin. Değişikliklerde mevcut proje dosyalarıyla uyumluluğu koruyun ve testleri çalıştırın.

## Yol haritası

1. **Phase 1:** Timeline ve önizleme/çıktı tutarlılığı, ses ve düzenleme kararlılığı.
2. **Phase 2:** İsteğe bağlı yerel transkripsiyon ve ses araçları.
3. **Phase 3:** Proxy, dışa aktarma ilerlemesi/kuyruğu ve ek görüntü araçları.
4. **Phase 4:** Daha kapsamlı çeviriler, çalışma alanları ve güvenilirlik.

Yol haritası hedefleri mevcut özellik değildir.
